"""The switch (SYS-06, SYS-07, 04 section 8, 04-A V39, V43, V44): move `current` to another version, start it, check it,
and go back if it doesn't come up.

    python -m shelfsync.update.switch --format 1 --mode install|rollback --from <v> --to <v> --install-root <dir>
        --data-dir <dir> --old-pid <pid> [--restore-backup]

It runs from `versions\\<from>\\pythonw.exe`, the version being LEFT, so the code that decides is the old, known-good
one (and v0.1.0's switch must already be right: the command line is a versioned contract, `--format 1`). The app
starts it detached and then asks the tray to quit. In order:

1. repair a missing `current` (left by an earlier switcher killed between its two renames), open one handle on the
   old PID and check that it is `<from>`'s own Python, check that `current` really is `<from>`, and check that the
   target is a kept version: its manifest's signature and every file against it (`kept.py`);
2. wait up to 70 s on that handle for the old process to end. If it is still running nothing changes and nothing starts;
3. take the single-instance lock, so no other copy can start mid-switch;
4. (a roll back after a database change) first a checked copy of the current database, `backups\\pre-rollback-<from>-
   <UTC>.db`, then the pre-migration backup put in its place, before the old version starts: an older version refuses a
   database written by a newer one (`db/migrate.py`, exit 2). Whether to restore is decided by schema numbers: the
   database's highest migration against the target manifest's `schema_version`, and the recorded backup must go from
   the one to the other;
5. `current.next` -> `current.old` swap -> remove `current.old`; write `DisplayVersion`; release the lock;
6. start `current\\pythonw.exe -m shelfsync.launcher --background` and check it within 60 s: `runtime.json` names the
   child's PID, Windows says the listener is that process, the same user, running the target version's own Python
   (the images are given explicitly; V44 decides whether Windows reports the path through the junction), `/api/health`
   says the target version, and all of it still holds 5 s later. The install token is never read or sent;
7. success: write the result, run one plain launcher (a second launch, so the running copy opens a signed-in tab with
   its own ticket), prune to the two versions (the switcher's own folder is never deleted by its own roll back);
8. failure: end the child, take the lock, put the database back (the backup after a failed install that migrated; the
   snapshot after a failed roll back), re-point to `<from>`, restore the state file, start it and check it the same
   way. If that also fails, `current` stays on `<from>` and the result says `failed`.

After the old copy has quit, every way out starts a copy again (even a refusal before anything changed: a bad
target, a junction that can't be repaired, a PID that isn't the old copy), with exactly these exits that start
nothing:
- `not_switched` with `old_copy_still_running` or `lock_busy`: another copy holds the instance lock, so one is
  running and there is nothing to start;
- `failed` with `+lock_busy`: the lock couldn't be had to put things back after the new version failed, so nothing more
  was changed;
- `failed` with `+junction_error`: the link couldn't be put back;
The owner then starts ShelfSync from the shortcut or Setup.exe.
"""

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import httpx

from shelfsync.clock import to_iso, utc_now
from shelfsync.db.backup import BackupError, database_schema, latest_schema, restore_backup, take_snapshot
from shelfsync.logs import configure_append_logging, remove_logging
from shelfsync.paths import DataPaths, remove_entry
from shelfsync.platform.junction import DirectoryLinks, LinkError, default_links
from shelfsync.platform.process import Processes, ProcessWatch, SpawnedProcess, default_processes
from shelfsync.platform.sockets import OwnerLookupError, Verdict, check_listener, normalize_image, process_info
from shelfsync.platform.uninstall_entry import MemoryUninstallEntry, UninstallEntry, default_uninstall_entry
from shelfsync.tray.instance import InstanceLock, default_instance_lock
from shelfsync.tray.second_launch import make_client, read_runtime
from shelfsync.update.kept import KeptVersionError, verify_kept_version
from shelfsync.update.layout import InstallLayout, UpdatePaths, installed_root
from shelfsync.update.state import BackupRecord, ResultStore, StateStore, SwitchIntent, SwitchResult
from shelfsync.update.versions import VersionError, is_newer, is_valid_version

_log = logging.getLogger("shelfsync.update")

SWITCH_FORMAT = 1
WAIT_FOR_QUIT_SECONDS = 70.0  # the app's 45 s and 10 s safety exit, plus a margin
HEALTH_WITHIN_SECONDS = 60.0
STABLE_SECONDS = 5.0
LOCK_WAIT_SECONDS = 15.0
UNREADABLE_IMAGE_GRACE_SECONDS = 5.0
CHILD_END_SECONDS = 10.0
_POLL_SECONDS = 0.5

EXIT_DONE = 0
EXIT_NOT_SWITCHED = 1
EXIT_FAILED = 2
EXIT_BAD_ARGUMENTS = 3

LAUNCHER_ARGS = ("-m", "shelfsync.launcher")


@dataclass(frozen=True)
class SwitchPlan:
    mode: str  # "install" or "rollback"
    from_version: str
    to_version: str
    layout: InstallLayout
    paths: DataPaths
    old_pid: int
    restore_backup: bool = False


class HealthProbe:
    """Is the child at `pid` the healthy, trusted copy of `version`? Returns None if so, otherwise a fixed reason:
    `no_answer`, `untrusted_listener`, `wrong_version`. It sends no secret (the install token is never read)."""

    def probe(self, paths: DataPaths, pid: int, version: str, images: frozenset[str]) -> str | None:
        running = read_runtime(paths)
        if running is None or running.pid != pid:
            return "no_answer"
        verdict = check_listener(running.port, running.pid, expected=images)
        if verdict in (Verdict.NOBODY, Verdict.LOOKUP_FAILED):
            return "no_answer"
        if verdict is not Verdict.TRUSTED:
            return "untrusted_listener"
        try:
            with make_client() as client:
                response = client.get(f"http://127.0.0.1:{running.port}/api/health")
                body = response.json()
            answered = response.status_code == 200 and isinstance(body, dict) and body.get("app") == "shelfsync"
            reported = body.get("version") if answered else None
        except httpx.HTTPError, ValueError, AttributeError:
            return "no_answer"
        if not answered:
            return "no_answer"
        return None if reported == version else "wrong_version"


def _image_of(pid: int) -> str | None:
    try:
        return process_info(pid).image
    except OwnerLookupError:
        return None


@dataclass
class SwitchEnv:
    links: DirectoryLinks
    processes: Processes
    uninstall: UninstallEntry
    lock: InstanceLock
    health: HealthProbe
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = utc_now
    image_of: Callable[[int], str | None] = _image_of
    own_schema: Callable[[], int] = latest_schema  # the schema of the version this switcher runs from


def _make_lock(paths: DataPaths) -> InstanceLock:
    """The single-instance lock: the session mutex and the data folder's lock file (m1b.1)."""
    return default_instance_lock(paths=paths)


def default_env(paths: DataPaths) -> SwitchEnv:
    """The real adapters. The registry is written only by an installed copy: anything else (a development copy, a
    rehearsal that isn't installed) gets a no-op, so no real uninstall entry is ever touched by accident."""
    uninstall = default_uninstall_entry() if installed_root() is not None else MemoryUninstallEntry(present=False)
    return SwitchEnv(default_links(), default_processes(), uninstall, _make_lock(paths), HealthProbe())


def repair_current(layout: InstallLayout, links: DirectoryLinks) -> bool:
    """Make `current` exist again after a crash between the two renames, and clear what the switch leaves behind.
    `current.old` (the version that was running) is preferred over `current.next`. Returns True if it changed
    anything."""
    changed = False
    if not links.exists(layout.current):
        for source in (layout.current_old, layout.current_next):
            if links.exists(source):
                links.rename(source, layout.current)
                changed = True
                break
    if links.exists(layout.current):
        for leftover in (layout.current_old, layout.current_next):
            if links.exists(leftover) and links.target(leftover) is not None:
                links.remove(leftover)  # a link only; a real folder with that name is left alone
                changed = True
    return changed


def current_version(layout: InstallLayout, links: DirectoryLinks) -> str | None:
    """The version `current` points at, or None if it isn't a link to a `versions\\<v>` folder."""
    target = links.target(layout.current)
    if target is None:
        return None
    if os.path.normcase(os.path.normpath(target.parent)) != os.path.normcase(os.path.normpath(layout.versions)):
        return None
    return target.name if is_valid_version(target.name) else None


def repoint(layout: InstallLayout, links: DirectoryLinks, version: str) -> None:
    """Point `current` at `versions\\<version>`: make `current.next`, swap the names, remove `current.old`. The swap
    isn't atomic (04-A V39): a fault of any kind after the first rename (an exception, Ctrl+C, the interpreter being
    stopped) is undone at once by `repair_current`. A hard kill in that instant can't be caught; `current` is then put
    back by the next switcher run (it begins with `repair_current`) or by Setup.exe. The app's own start only clears
    leftovers."""
    target = layout.version_dir(version)
    for stale in (layout.current_next, layout.current_old):
        if links.exists(stale):
            links.remove(stale)
    try:
        links.create(layout.current_next, target)
        links.rename(layout.current, layout.current_old)
        links.rename(layout.current_next, layout.current)
        links.remove(layout.current_old)
    except BaseException:
        try:
            repair_current(layout, links)
        except LinkError, OSError:
            _log.error("The switch could not put the current link back; the next switch or Setup.exe repairs it")
        raise


def prune_versions(layout: InstallLayout, keep: set[str]) -> None:
    """Remove every version folder and manifest that isn't in `keep`, and any `.incoming-*` folder, never following a
    link. Names that aren't versions are left alone."""
    if layout.versions.is_dir():
        for entry in layout.versions.iterdir():
            if entry.name.startswith(".incoming-") or (is_valid_version(entry.name) and entry.name not in keep):
                _remove(entry)
    if layout.manifests.is_dir():
        for entry in layout.manifests.iterdir():
            version = entry.name.removesuffix(".sig").removesuffix(".json")
            if is_valid_version(version) and version not in keep:
                _remove(entry)


def _remove(entry: Path) -> None:
    try:
        remove_entry(entry)
    except OSError as error:
        _log.warning("The switch couldn't remove %s: %s", entry.name, error)


def version_images(layout: InstallLayout, version: str) -> frozenset[str]:
    """The program files a healthy copy of `version` shows as its image, resolved: the junction and the folder name
    the same file (V44)."""
    return frozenset(normalize_image(str(layout.interpreter(version, console=console))) for console in (False, True))


class _Switch:
    def __init__(self, plan: SwitchPlan, env: SwitchEnv) -> None:
        self.plan = plan
        self.env = env
        update_paths = UpdatePaths(plan.paths)
        self.store = StateStore(update_paths)
        self.results = ResultStore(update_paths)
        self.started_at = to_iso(env.now())
        self.before = self.store.load()
        self.touched = False  # set once the switch has written anything (its intent, the files, the junction)
        self.target_schema: int | None = None  # the target's schema number, from its verified manifest
        self.restore_record: BackupRecord | None = None  # the backup a roll back puts back
        self.snapshot: BackupRecord | None = None  # the copy of the database taken before that
        self.restored = False  # a roll back has replaced the database with the backup
        self.changed = False  # the database was replaced or the junction was touched: something has to be put back
        self.adopted_pid: int | None = (
            None  # a healthy copy someone else started in the gap: never ended by this switch
        )

    # ---- the whole run ---------------------------------------------------------------------------------------------

    def run(self) -> SwitchResult:
        plan, env = self.plan, self.env
        watch = env.processes.watch(plan.old_pid)  # first thing: the sooner the handle is held, the safer the PID is
        problem: str | None = None
        trusted = watch is not None  # the handle may be waited on
        verdict = "none"
        have_lock = False
        try:
            try:
                repair_current(plan.layout, env.links)
            except LinkError:
                problem = "junction_error"
            if watch is not None:
                verdict = self._old_copy_verdict(watch)
                if verdict == "no":
                    problem = problem or "old_process_mismatch"
                    trusted = False  # not the old copy: waiting on it would prove nothing
            if problem is None:
                problem = self._validate()
            if watch is not None and trusted and not self._wait_for_old_copy(watch):
                # Still up after the full wait. A copy that holds the instance lock is alive and running: nothing to
                # start. If the lock is free, the process on the handle isn't holding it: when its image matched, the
                # old copy is hung (alive, but it has let go of the lock); when the image couldn't be read, it was
                # never the old copy.
                if not self._take_lock(0.0):
                    return self._finish("not_switched", "old_copy_still_running")
                have_lock = True
                problem = problem or ("old_copy_hung" if verdict == "yes" else "old_process_mismatch")
        finally:
            if watch is not None:
                watch.close()
        if not have_lock:
            # The old copy holds the lock until it has ended, so the lock also decides when a handle can't be trusted.
            wait = LOCK_WAIT_SECONDS if watch is None or trusted else WAIT_FOR_QUIT_SECONDS
            if not self._take_lock(wait):
                return self._finish("not_switched", "lock_busy")  # another copy holds it: one is running
        if problem is None and plan.mode == "rollback":
            problem = self._check_rollback_database()
        if problem is not None:
            return self._restart_old(problem)
        try:
            self.touched = True
            self._write_intent()
            if self.restore_record is not None:
                self._snapshot_and_restore(self.restore_record)
            self.changed = True
            repoint(plan.layout, env.links, plan.to_version)
            env.uninstall.set_display_version(plan.to_version)
            self._write_state_for_target()
        except BackupError as error:
            return self._restart_old(error.code)
        except LinkError, OSError:
            return self._restart_old("junction_error")
        env.lock.release()
        child, reason = self._start_and_check(plan.to_version)
        if reason is None:
            return self._succeed()
        return self._go_back(child, reason)

    # ---- steps -----------------------------------------------------------------------------------------------------

    def _old_copy_verdict(self, watch: ProcessWatch) -> str:
        """Is the process the PID names `<from>`'s own Python (the handle is held, so the PID can't be reused)?
        `yes`; `no` (another program: not waited for, the lock decides); `unknown` (up, but Windows won't name its
        program).

        A process that is already shutting down (the app was asked to quit before this switcher got going) can't be
        asked for its image. If it ends within a few seconds it is the old copy on its way out. One that stays up with
        an unreadable image is waited for on the handle for the full wait, and the instance lock decides after that."""
        expected = version_images(self.plan.layout, self.plan.from_version)
        image = watch.image
        if image is None:
            grace = self.env.clock() + UNREADABLE_IMAGE_GRACE_SECONDS
            while watch.is_running() and self.env.clock() < grace:
                self.env.sleep(_POLL_SECONDS)
            if not watch.is_running():
                return "yes"
            image = watch.image
        if image is None:
            return "unknown"
        if normalize_image(image) in expected:
            return "yes"
        _log.warning(
            "The process %d is %r, not the Python of version %s", self.plan.old_pid, image, self.plan.from_version
        )
        return "no"

    def _validate(self) -> str | None:
        plan = self.plan
        if current_version(plan.layout, self.env.links) != plan.from_version:
            return "from_mismatch"
        try:
            if plan.mode == "install":
                if not is_newer(plan.to_version, plan.from_version):
                    return "target_invalid"
            elif self.before.previous != plan.to_version:
                return "target_invalid"  # a roll back goes to the version the state remembers, nowhere else
            manifest = verify_kept_version(plan.layout, plan.to_version)
        except KeptVersionError as error:
            return error.code
        except VersionError:
            return "target_invalid"
        self.target_schema = manifest.schema_version
        return None

    def _check_rollback_database(self) -> str | None:
        """Decide from schema numbers, not times, whether a roll back must restore a backup: only when the database's
        highest migration is above the target's `schema_version`. Then the recorded backup must be exactly the one
        that goes from the target's schema to the database's. The plan (the owner's confirmation) must agree."""
        plan = self.plan
        current = database_schema(plan.paths.database)
        target = self.target_schema
        needs_restore = current is not None and target is not None and current > target
        if needs_restore != plan.restore_backup:
            return "database_changed"  # the database isn't what the owner was told when they confirmed
        if not needs_restore:
            return None
        record = self.before.backup
        if record is None:
            return "backup_missing"
        if record.from_schema != target or record.to_schema != current:
            return "backup_mismatch"
        self.restore_record = record
        return None

    def _wait_for_old_copy(self, watch: ProcessWatch) -> bool:
        deadline = self.env.clock() + WAIT_FOR_QUIT_SECONDS
        while watch.is_running():
            if self.env.clock() >= deadline:
                return False
            self.env.sleep(_POLL_SECONDS)
        return True

    def _take_lock(self, wait: float) -> bool:
        deadline = self.env.clock() + wait
        while not self.env.lock.acquire():
            if self.env.clock() >= deadline:
                return False
            self.env.sleep(_POLL_SECONDS)
        return True

    def _write_intent(self) -> None:
        intent = SwitchIntent(self.plan.mode, self.plan.from_version, self.plan.to_version, self.started_at)
        self.store.update(lambda state: replace(state, switch=intent))

    def _snapshot_and_restore(self, record: BackupRecord) -> None:
        """Roll back, step one: a checked copy of the current database (so the roll back can be undone), and only then
        the older backup put in its place. If the copy can't be made the roll back is refused (BackupError)."""
        self.snapshot = take_snapshot(self.plan.paths, self.plan.from_version, self.env.now)
        restore_backup(record, self.plan.paths)
        self.restored = True
        self.changed = True

    def _undo_restore(self) -> str | None:
        """Put the snapshot back (after a roll back's later step failed). A reason suffix if that fails too."""
        if not self.restored or self.snapshot is None:
            return None
        try:
            restore_backup(self.snapshot, self.plan.paths)
        except BackupError as error:
            _log.error("The database could not be put back after the failed roll back (%s)", error.code)
            return f"snapshot_{error.code}"
        self.restored = False
        return None

    def _write_state_for_target(self) -> None:
        """Written while no copy runs (the lock is held), so the new copy finds it ready."""
        plan = self.plan
        installing = plan.mode == "install"
        self.store.update(
            lambda state: replace(
                state,
                installed=plan.to_version,
                previous=plan.from_version if installing else None,
                switched_at=self.started_at,
                pending=None if installing else state.pending,
                backup=state.backup if installing else None,  # a roll back has used the backup up
            )
        )

    def _start_and_check(self, version: str) -> tuple[SpawnedProcess | None, str | None]:
        layout, env = self.plan.layout, self.env
        argv = [str(layout.current_interpreter), *LAUNCHER_ARGS, "--background"]
        try:
            child = env.processes.spawn_detached(argv, layout.current)
        except OSError:
            return None, "exited"
        return child, self._wait_healthy(child, version)

    def _wait_healthy(self, child: SpawnedProcess, version: str) -> str | None:
        env = self.env
        images = version_images(self.plan.layout, version)
        deadline = env.clock() + HEALTH_WITHIN_SECONDS
        reason = "no_answer"
        pid = child.pid
        adopted = False
        while True:
            if not adopted:
                code = child.poll()
                if code is not None:
                    other = self._healthy_other_copy(child, version, images) if code != 2 else None
                    if other is None:
                        return "migration_failed" if code == 2 else "exited"
                    pid, adopted = other, True
                    self.adopted_pid = other
            probed = env.health.probe(self.plan.paths, pid, version, images)
            if probed is None:
                break
            reason = probed
            if env.clock() >= deadline:
                return reason
            env.sleep(_POLL_SECONDS)
        settled = env.clock() + STABLE_SECONDS  # still healthy a few seconds later
        while env.clock() < settled:
            env.sleep(_POLL_SECONDS)
            if not adopted and child.poll() is not None:
                other = self._healthy_other_copy(child, version, images)
                if other is None:
                    return "exited"
                pid, adopted = other, True
                self.adopted_pid = other
        return env.health.probe(self.plan.paths, pid, version, images)

    def _healthy_other_copy(self, child: SpawnedProcess, version: str, images: frozenset[str]) -> int | None:
        """The child exited. If it ran as a second launch because the owner's shortcut started a copy in the gap, and
        `runtime.json` names a healthy, trusted copy of the expected version (the same checks as for a child), that copy
        is the one: its PID, to be counted as the success. Such a copy is never ended by this switcher."""
        running = read_runtime(self.plan.paths)
        if running is None or running.pid == child.pid:
            return None
        if self.env.health.probe(self.plan.paths, running.pid, version, images) is not None:
            return None
        return running.pid

    def _succeed(self) -> SwitchResult:
        plan = self.plan
        self._open_tab()
        # Both versions stay in both modes: the switcher itself runs from `<from>`, so a roll back must not delete it
        # (the next update's prune removes what is no longer wanted).
        keep = {plan.to_version, plan.from_version}
        if plan.mode == "rollback" and self.before.pending is not None:
            keep.add(self.before.pending.version)  # a downloaded update still waiting for the owner's go-ahead
        prune_versions(plan.layout, keep)
        return self._finish("updated" if plan.mode == "install" else "rolled_back", None)

    def _go_back(self, child: SpawnedProcess | None, reason: str) -> SwitchResult:
        """The target didn't come up: end it, then (under the instance lock) put the database back and start `<from>`
        again. If the lock can't be had, nothing more is changed and the result says so."""
        self._end_child(child, self.plan.to_version)
        if not self._take_lock(LOCK_WAIT_SECONDS):
            return self._finish("failed", f"{reason}+lock_busy")  # one of the two exits that start nothing
        if self.plan.mode == "install":
            extra = self._restore_after_failed_install()
            if extra:
                reason = f"{reason}+{extra}"
        return self._restart_old(reason, kept=True)

    def _restore_after_failed_install(self) -> str | None:
        """The new version failed after it may have migrated the database: if the schema is above `<from>`'s, restore
        the backup that goes from `<from>`'s schema to the database's. A reason suffix if that can't be done."""
        paths = self.plan.paths
        current = database_schema(paths.database)
        own = self.env.own_schema()
        if current is None or current <= own:
            return None
        record = self.store.load().backup
        if record is None:
            return "backup_missing"
        if record.from_schema != own or record.to_schema != current:
            return "backup_mismatch"
        try:
            restore_backup(record, paths)
        except BackupError as error:
            _log.error("The database could not be restored after the failed start (%s)", error.code)
            return error.code
        return None

    def _restart_old(self, reason: str, kept: bool = False) -> SwitchResult:
        """Start again the copy that quit and check it. The instance lock is held on entry. If the switch changed
        anything, that is put back first: a roll back's database restore is undone from the snapshot, `current` points
        at `<from>` again, and the state is reverted. If it changed nothing, whatever `current` points at is started."""
        plan, env = self.plan, self.env
        running = plan.from_version
        suffix = self._undo_restore()
        if suffix:
            reason = f"{reason}+{suffix}"
        try:
            if self.touched:
                if current_version(plan.layout, env.links) != plan.from_version:
                    repoint(plan.layout, env.links, plan.from_version)
                env.uninstall.set_display_version(plan.from_version)
            else:
                found = current_version(plan.layout, env.links)
                if found is None:  # `current` is a real folder, points outside `versions`, or is gone: nothing to start
                    env.lock.release()
                    return self._finish("failed", f"{reason}+junction_error")
                running = found
        except LinkError, OSError:
            env.lock.release()
            return self._finish("failed", f"{reason}+junction_error")  # the other exit that starts nothing
        if self.touched:
            self._revert_state()
        env.lock.release()
        child, again = self._start_and_check(running)
        if again is None:
            self._open_tab()
            return self._finish("kept_old" if kept or self.changed else "not_switched", reason)
        self._end_child(child, running)
        return self._finish("failed", reason)

    def _revert_state(self) -> None:
        """Put back what the switch changed in state.json: the versions, the backup record (a failed start's own newer
        backup must not replace the one a roll back to `<previous>` needs) and the pending download."""
        before = self.before
        self.store.update(
            lambda state: replace(
                state,
                installed=before.installed,
                previous=before.previous,
                switched_at=before.switched_at,
                backup=before.backup,
                pending=before.pending,
                switch=None,
            )
        )

    def _end_child(self, child: SpawnedProcess | None, version: str) -> None:
        """End the copy this switch started (and the process runtime.json names, if it is another one running the same
        version's program), then wait for it. Never any other process."""
        env = self.env
        pids: set[int] = set()
        if child is not None:
            pids.add(child.pid)
            if child.poll() is None:
                child.terminate()
                if child.wait(CHILD_END_SECONDS) is None:
                    child.kill()
                    child.wait(CHILD_END_SECONDS)
        running = read_runtime(self.plan.paths)
        if running is not None and running.pid not in pids and running.pid != self.adopted_pid:
            image = env.image_of(running.pid)
            if image is not None and normalize_image(image) in version_images(self.plan.layout, version):
                env.processes.terminate_pid(running.pid)
                pids.add(running.pid)
        deadline = env.clock() + CHILD_END_SECONDS
        while any(env.processes.is_running(pid) for pid in pids) and env.clock() < deadline:
            env.sleep(_POLL_SECONDS)

    def _open_tab(self) -> None:
        """One plain launcher: a second launch, so the running copy opens a signed-in tab with its own ticket."""
        layout = self.plan.layout
        try:
            self.env.processes.spawn_detached([str(layout.current_interpreter), *LAUNCHER_ARGS], layout.current)
        except OSError:
            _log.warning("The switch couldn't open the signed-in tab")

    def _finish(self, outcome: str, reason: str | None) -> SwitchResult:
        result = SwitchResult(
            self.plan.mode, self.plan.from_version, self.plan.to_version, outcome, reason, to_iso(self.env.now())
        )
        try:
            self.results.save(result)
        except OSError:
            _log.error("The switch result couldn't be written")
        _log.info(
            "Switch %s %s to %s: %s (%s)", self.plan.mode, self.plan.from_version, self.plan.to_version, outcome, reason
        )
        return result


def run_switch(plan: SwitchPlan, env: SwitchEnv | None = None) -> SwitchResult:
    return _Switch(plan, env or default_env(plan.paths)).run()


def _exit_code(result: SwitchResult) -> int:
    if result.outcome in ("updated", "rolled_back"):
        return EXIT_DONE
    return EXIT_FAILED if result.outcome == "failed" else EXIT_NOT_SWITCHED


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shelfsync.update.switch", exit_on_error=False)
    parser.add_argument("--format", type=int, required=True)
    parser.add_argument("--mode", choices=("install", "rollback"), required=True)
    parser.add_argument("--from", dest="from_version", required=True)
    parser.add_argument("--to", dest="to_version", required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--old-pid", type=int, required=True)
    parser.add_argument("--restore-backup", action="store_true")
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError, SystemExit:
        return EXIT_BAD_ARGUMENTS
    if args.format != SWITCH_FORMAT or args.old_pid <= 0:
        return EXIT_BAD_ARGUMENTS
    if not is_valid_version(args.from_version) or not is_valid_version(args.to_version):
        return EXIT_BAD_ARGUMENTS
    if args.from_version == args.to_version or not args.install_root.is_absolute() or not args.data_dir.is_absolute():
        return EXIT_BAD_ARGUMENTS
    running_from = installed_root()
    if running_from is not None and os.path.normcase(str(running_from)) != os.path.normcase(str(args.install_root)):
        return EXIT_BAD_ARGUMENTS  # an installed switch works on its own install and nothing else
    plan = SwitchPlan(
        args.mode,
        args.from_version,
        args.to_version,
        InstallLayout(args.install_root),
        DataPaths(args.data_dir),
        args.old_pid,
        args.restore_backup,
    )
    handler = None
    try:
        plan.paths.logs.mkdir(parents=True, exist_ok=True)
        handler = configure_append_logging(plan.paths.logs)
    except OSError:
        handler = None
    try:
        return _exit_code(run_switch(plan))
    except Exception:
        _log.exception("The switch stopped unexpectedly")
        return EXIT_FAILED
    finally:
        try:
            repair_current(plan.layout, default_links())  # best effort: whatever happened, `current` should exist
        except Exception:
            _log.exception("The final check of the current link failed")
        if handler is not None:
            remove_logging(handler)


if __name__ == "__main__":
    sys.exit(main())

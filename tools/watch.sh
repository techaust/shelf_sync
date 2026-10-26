#!/usr/bin/env bash
# Event watch for the ShelfSync lead while builders or designers run (adapted from techaust_platform; same shared lock) (used with the Monitor tool). Prints ONE line and exits when:
#   - a builder or designer worktree has had no new commit for 20 minutes since the watch started (or --since), while
#     no heavy command is running (a stall), or
#   - free memory drops under HEAVY_MIN_FREE_MB (default 512; the same setting as tools/heavy.sh).
# A heavy lock counts as running only while its owner or its command is alive and it's under the 6-hour ceiling,
# so a stale lock left by a crash doesn't hide a stall.
# Agent completion itself arrives as a task notification, so it isn't watched here.
# Usage: bash tools/watch.sh [--since <unix seconds>] <worktree> [<worktree>...]   (--since: when the agents started)
set -u
LOCK="${HEAVY_LOCK:-$HOME/.techaust-heavy.lock}"
MIN_FREE_MB="${HEAVY_MIN_FREE_MB:-512}"
CEILING_MIN="${HEAVY_CEILING_MIN:-360}"
STALL_S=1200
started=$(date +%s)
if [ "${1:-}" = "--since" ]; then
  case "${2:-}" in ''|*[!0-9]*) echo "Usage: bash tools/watch.sh [--since <unix seconds>] <worktree>..." >&2; exit 2 ;; esac
  started=$2
  shift 2
fi
[ $# -gt 0 ] || { echo "Usage: bash tools/watch.sh [--since <unix seconds>] <worktree>..." >&2; exit 2; }

pid_alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
heavy_running() {
  [ -d "$LOCK" ] || return 1
  [ -z "$(find "$LOCK" -maxdepth 0 -mmin +"$CEILING_MIN" 2>/dev/null)" ] || return 1
  pid_alive "$(cat "$LOCK/pid" 2>/dev/null)" || pid_alive "$(cat "$LOCK/child" 2>/dev/null)"
}

while :; do
  if [ "$MIN_FREE_MB" -gt 0 ]; then
    mb="$(powershell.exe -NoProfile -Command "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1024)" 2>/dev/null | tr -d '\r')"
    if [ -n "$mb" ] && [ "$mb" -lt "$MIN_FREE_MB" ]; then echo "EVENT low-memory ${mb}MB"; exit 0; fi
  fi
  if ! heavy_running; then
    now=$(date +%s)
    for wt in "$@"; do
      last=$(git -C "$wt" log -1 --format=%ct 2>/dev/null || echo 0)
      [ "$last" -gt "$started" ] || last=$started
      if [ $((now - last)) -ge $STALL_S ]; then echo "EVENT stall $wt (no commit for $(((now - last) / 60)) min, no heavy command running)"; exit 0; fi
    done
  fi
  sleep 60
done

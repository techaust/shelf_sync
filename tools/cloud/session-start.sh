#!/usr/bin/env bash
# SessionStart hook (wired in .claude/settings.json). Does nothing outside a cloud session (CLAUDE_CODE_REMOTE is "true"
# only there). In a cloud session it puts the toolchain from tools/cloud/setup.sh first on PATH for every later command,
# sets the repo-local commit identity and the tracked pre-push hook, installs the locked Python packages and, when the
# lock file changed, the screen packages. Its output is shown to Claude, so every problem is printed; it never blocks
# the session (docs/runbooks/cloud-sessions.md).
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

TOOLS="/opt/uv-0.12.19/bin:/opt/node-v24.19.0/bin:/opt/hostedtoolcache/Python/3.14.8/x64/bin"
export PATH="$TOOLS:$PATH"
export UV_PYTHON_DOWNLOADS=never
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$TOOLS:\$PATH\"" >>"$CLAUDE_ENV_FILE"
  echo "export UV_PYTHON_DOWNLOADS=never" >>"$CLAUDE_ENV_FILE"
else
  echo "[cloud] CLAUDE_ENV_FILE is not set: later commands won't have the pinned tools first on PATH."
fi

problems=0
want() { # want <label> <expected> <command...>
  local got
  got="$("${@:3}" 2>&1 | head -1)"
  case "$got" in *"$2"*) echo "[cloud] $1: $got" ;; *) echo "[cloud] PROBLEM: $1 is '$got', expected $2 (is tools/cloud/setup.sh the environment's setup script?)"; problems=1 ;; esac
}
want "Python" "3.14.8" python3.14 --version
want "Node" "v24.19.0" node --version
want "uv" "0.12.19" uv --version

git config core.hooksPath .githooks
git config user.name "TecHaust Technologies"
git config user.email "admin@techaust.com"

if ! uv sync --locked --quiet >/tmp/shelfsync-uv-sync.log 2>&1; then
  echo "[cloud] PROBLEM: uv sync --locked failed; see /tmp/shelfsync-uv-sync.log"
  problems=1
fi

# npm ci only when the lock file (or this script) changed since the last good install.
stamp="frontend/node_modules/.shelfsync-npm-ci.sha256"
if ! (cd frontend && sha256sum --check --status "../$stamp" 2>/dev/null); then
  rm -f "$stamp"
  if (cd frontend && npm ci --no-audit --no-fund >/tmp/shelfsync-npm-ci.log 2>&1); then
    (cd frontend && sha256sum package-lock.json ../tools/cloud/session-start.sh >"../$stamp")
  else
    echo "[cloud] PROBLEM: npm ci in frontend/ failed; see /tmp/shelfsync-npm-ci.log"
    problems=1
  fi
fi

if [ "$problems" = 0 ]; then
  echo "[cloud] ShelfSync cloud session ready (no browser agents here: visual checks run on the owner's PC)."
fi
exit 0

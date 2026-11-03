#!/usr/bin/env bash
# Keeps Claude's memory notes for this project on GitHub (owner, 2026-11-03; docs/11). Claude Code keeps them outside
# the repo, in <config>/projects/<slug>/memory/, so a new PC or a cloud session would start without them.
#   restore  ("start the day"): docs/memory/ -> the memory folder. A note missing here is copied in; a note that differs
#            is replaced, unless this machine's copy changed after docs/memory/'s copy was last committed (it was never
#            saved), which is kept. Nothing is deleted.
#   save     ("end the day"): the memory folder -> docs/memory/. Changed and new notes are copied; nothing is deleted
#            (a note removed on purpose is removed from docs/memory/ by hand, in the same commit).
# The memory folder is found from the main checkout's path (every character other than A-Z, a-z, 0-9 becomes "-",
# which is how Claude Code names its project folders); worktrees resolve to the main checkout. If that folder doesn't
# exist (Claude has never run in this checkout), nothing changes and the script says so.
# Usage: bash tools/memory-sync.sh restore|save
set -euo pipefail

mode="${1:-}"
case "$mode" in
  restore|save) ;;
  *) echo "Usage: bash tools/memory-sync.sh restore|save" >&2; exit 2 ;;
esac

root="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
repo_copy="$root/docs/memory"
slug="$(printf '%s' "$root" | sed 's/[^A-Za-z0-9]/-/g')"
project_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/$slug"
memory_dir="$project_dir/memory"

if [ ! -d "$project_dir" ]; then
  echo "PROBLEM: Claude's project folder $project_dir doesn't exist, so the memory folder can't be found. Nothing changed." >&2
  exit 1
fi

same() { diff -q --strip-trailing-cr "$1" "$2" >/dev/null 2>&1; }
changes=0

if [ "$mode" = restore ]; then
  mkdir -p "$memory_dir"
  for src in "$repo_copy"/*.md; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    [ "$name" = README.md ] && continue
    dst="$memory_dir/$name"
    if [ ! -f "$dst" ]; then
      cp "$src" "$dst"; echo "restored: $name"; changes=$((changes + 1))
    elif ! same "$src" "$dst"; then
      committed="$(git -C "$root" log -1 --format=%ct -- "docs/memory/$name")"
      if [ -n "$committed" ] && [ "$(stat -c %Y "$dst")" -gt "$committed" ]; then
        echo "kept this machine's newer copy: $name (not saved yet; \"end the day\" saves it)"
      else
        cp "$src" "$dst"; echo "updated from GitHub: $name"; changes=$((changes + 1))
      fi
    fi
  done
  for dst in "$memory_dir"/*.md; do
    [ -e "$dst" ] || continue
    name="$(basename "$dst")"
    [ -f "$repo_copy/$name" ] || echo "only on this machine: $name (\"end the day\" saves it)"
  done
  [ "$changes" -eq 0 ] && echo "Memory notes: already up to date." || echo "Memory notes: $changes restored or updated."
  exit 0
fi

if [ ! -f "$memory_dir/MEMORY.md" ]; then
  echo "No memory notes on this machine ($memory_dir has no MEMORY.md); docs/memory/ left as it is."
  exit 0
fi
mkdir -p "$repo_copy"
for src in "$memory_dir"/*.md; do
  [ -e "$src" ] || continue
  name="$(basename "$src")"
  [ "$name" = README.md ] && continue
  dst="$repo_copy/$name"
  if [ ! -f "$dst" ] || ! same "$src" "$dst"; then
    cp "$src" "$dst"; echo "saved: $name"; changes=$((changes + 1))
  fi
done
for dst in "$repo_copy"/*.md; do
  [ -e "$dst" ] || continue
  name="$(basename "$dst")"
  [ "$name" = README.md ] && continue
  [ -f "$memory_dir/$name" ] || echo "only on GitHub: $name (if it was removed on purpose, delete docs/memory/$name too)"
done
[ "$changes" -eq 0 ] && echo "Memory notes: nothing new to save." || echo "Memory notes: $changes saved to docs/memory/."

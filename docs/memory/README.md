# Memory notes (copy)

A copy of Claude Code's project memory for ShelfSync: the owner's preferences and project facts that aren't in the other docs. Claude keeps the working copy outside the repo (`~/.claude/projects/<this folder>/memory/`, index `MEMORY.md`). This copy is here so a new PC or a cloud session starts with the same notes (owner, 2026-11-03, [11](../11-decisions.md)).

- **"Start the day"** runs `bash tools/memory-sync.sh restore`: notes missing on the machine are copied in, and notes that differ are updated from here, unless the machine's copy is newer and not yet saved.
- **"End the day"** runs `bash tools/memory-sync.sh save`: changed and new notes are copied here and committed with the day's record.
- Nothing is deleted automatically. To remove a note, delete it in both places in the same commit.

**This repository is public.** A note never holds a secret, a key or a store address.

The files are copied as they are, so the links between notes use the `[[note-name]]` form Claude's memory uses, not Markdown links.

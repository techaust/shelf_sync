# ADR 0006: ShelfSync is a TecHaust product on the Patina identity

- **Status:** Accepted (owner, 2026-10-25)
- **Date:** 2026-10-25
- **Replaces:** plan Draft 3 §"Look and feel" (Manrope; store colours throughout)

## Context
The owner found the Draft 3 mockup "not looking good at all" and asked for the UI to look like the TecHaust platform, with its font and colour scheme and a complete new brand asset set.

## Decision
- **Tokens:** TecHaust's Patina palette and semantic tokens unchanged (ink, verdigris, stone, mist, status colours), plus three ShelfSync app-bar tokens ([05 §2.2](../05-design-system.md)), all in `brand/tokens.json` and kept in step with TecHaust.
- **Type:** Archivo (Expanded for display) + IBM Plex Mono, self-hosted.
- **Logo:** a **new ShelfSync logo** in Patina's construction language (blocks, the one-stroke 45° cut, ink base + verdigris accent), with a full generated asset set including tray-icon states and installer art. Three concepts in Phase 3; the owner picks one. Endorsed as "by TecHaust".
- **Store colours:** small identifiers only (shape + dot + two-letter code), never app styling; PluginWay's light dot is `#007b80`, a deeper teal chosen for contrast, so it passes 3:1 on every surface.

## Consequences
- [05](../05-design-system.md) is the design source; the mockups are rebuilt from it in Phase 3.
- Brand changes happen in code through a reviewed commit, as at TecHaust.
- **VERIFY WITH LEGAL:** a trademark search on "ShelfSync" before any public use beyond this private tool.

# ADR 0003: A catalog of products linked across stores by URL slug

- **Status:** Accepted (owner, with plan Draft 3, 2026-10-25)
- **Date:** 2026-10-25

## Context
OmniSync keyed each store's products from the file currently attached, so wrong attachments produced wrong keys, and colliding keys were dropped silently ([01 P1](../01-audit.md), evidence in [01-B](../01-audit-appendix/B-omnisync-evidence.md)). No product has a SKU.

## Decision
- A **catalog item** per real product, with download slots, fingerprints and a **canonical slug**: initially the shared URL slug, editable by the owner.
- Twins are linked by **identical product URL slug** (2395 of 2398 on 2026-10-25). Near misses with the same title are **suggested** in Cleanup, never linked silently.
- Attached files are **checked** against the product, never used to define it.
- **Keeping links honest:** incremental sync (`modified_after`) catches edits; a **nightly full ID listing** (including trash) catches deletions and trashing, which `modified_after` never returns.
- **Every active store:** a paused store is skipped by updates and shows "out of step" until resumed. A newly added store makes its products unlinked until its linking run, so their updates are held.

## Consequences
- File names come from the canonical slug (`<slug>-<version>.zip`, with `-r2`… instead of overwriting).
- A product must be linked on every active store before it's updated.
- **A paused store still counts for deletions** (amended 2026-10-25 after the re-review; accepted with the Phase 2 docs): it's skipped by updates, but an S3 object is deleted only if no store, paused ones included, still points at it, variation downloads included, and the file a rollback moved away from is kept so it can be rolled forward (APL-07). Otherwise a paused store's customers could lose their download.

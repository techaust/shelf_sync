# ADR 0004: Rule-based matching with bands, calibrated on real files; no AI

- **Status:** Accepted (owner, with plan Draft 3, 2026-10-25)
- **Date:** 2026-10-25

## Context
OmniSync's unclear cases were settled by an AI reading logs in chat ([01 P3](../01-audit.md)). The owner wants the app to run without AI and never guess silently.

## Decision
- Inspect the ZIP, pick the **main item** by fixed rules, score candidates with named signals, and decide by **band** (Certain, Likely, Unsure, No match).
- Weights and cut-offs come from a **cold calibration run** on the bucket's files with filenames hidden and an owner-reviewed exclusion list; the bar is **0 wrong products in Certain**.
- Guards (downgrade, version disagreement or family jump, outside changes, missing links, Defender detection or not scanned) always hold a job for Review.
- Every decision explains itself ("Why?") and is remembered as a fingerprint or an approved filename.

## Consequences
- Behaviour is predictable and testable; the known bad cases are permanent tests.
- **Statistical limit:** 0 wrong in about 2,400 files bounds the Certain error rate below about 0.13 % (95 %) on today's files only. That's why auto-apply waits for a 50-ZIP trust ramp.
- **Early Review load:** at first, many ZIPs land in Likely and need a click. The load falls as fingerprints accumulate, and teach-from-current-files gives a head start.

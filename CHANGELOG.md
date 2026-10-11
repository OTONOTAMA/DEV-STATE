# Changelog

## 1.1.1

- Clarify PROJECT-local code/Hook and CHAT / SESSION-owned progress in bilingual README and agent integration/setup guidance.
- Document nonstandard GLOBAL review, no automatic cross-PC sharing, Git/privacy exclusions and existing data/config/trust protection.
- Common core, schemas, launcher and adapter runtime remain unchanged.
- New package version and integrity metadata; existing 1.1.0 release is not replaced.
- Isolate test fixtures from an enclosing Git checkout; pin source line endings to LF.

## 1.1.0

Initial public MIT release, based on DEV_STATE Portable v1.1.

- Retain common core, launcher, schemas and Codex adapter without runtime changes.
- Add bilingual README, safety/removal guidance and self-contained deterministic release tooling.
- Exclude chat-owned state, receipts, private configurations and development logs.
- Carry no hook trust or target-environment acceptance claim.

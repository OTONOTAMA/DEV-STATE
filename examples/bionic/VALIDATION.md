# Reference preparation validation

Prepared against public DEV-STATE commit
`a73803ca7df4906b54c9ec509ff0c5695d083466`.

This change adds reference fragments and isolated tests only. Common core,
schemas, portable launcher, Codex adapter, operation templates and Release
artifacts are unchanged. No live Bionic Skill, policy, checkpoint or state was
modified. No GitHub publication was performed in this preparation step.

## Executed checks

- Windows / host Python 3.14: reference tests 5 passed, 0 failed, 0 skipped.
  Covered absent state/no initialization, bound compact read/no state writes,
  owner mismatch, portable launcher success and invalid interpreter override.
- Existing common-core suite: 38 tests run, 37 passed, 1 skipped, 0 failures or
  errors. The symlink/junction escape test was skipped because the restricted
  test environment could not create either link type. Do not label it PASS.
- Reference test fixtures used a writable temporary location and were removed
  by their test cleanup. An initial restricted system-temp attempt was unsuitable;
  its errors were not treated as a runtime result. A test-harness JSON projection
  lookup was corrected to `data.reconciliation` before the final passing run.
- Git whitespace check passed. Selected reference files were checked for personal
  home paths, author-specific identifiers and common credential patterns; none
  were found. This is a bounded disclosure check, not a security certification.

## Not established by these checks

Target Bionic Skill installation/selection, actual compaction/handoff invocation,
the project's checkpoint guard containment cases, optional refresh write/no-op
behavior, migration across project moves, power-loss behavior and other PCs.
Validate them on the intended target; do not convert reference/unit-test PASS
into an installation or automatic-recovery guarantee.

## Release boundary

These examples are source-only additions. Do not overwrite/rebuild the existing
v1.1.1 Release or its checksums to add them. The repository release builder's
allowlist does not include examples/bionic. If a later version includes them in
an installation ZIP, separately update version/allowlist/manifest, test and
publish new assets. Existing Releases remain unchanged.

# DEV_STATE portable integration contract

## 1. Boundaries

The shipped `dev_state.py` is the common state implementation. Do not recreate its logic in a Skill or Hook. Keep existing memory/checkpoint/authorization rules. DEV_STATE records progress and evidence; no stored state grants permission to execute. AI_DECLARED completion and machine test evidence remain separate.

Keep installation local and small. No daemon, transcript parser, model routing, extra database or automatic project scan. Deploy code separately from chat-owned state. Do not adopt the original development documents' historic paths or unfinished gate labels.

## 2. Preflight / integrity

1. Verify every file against `manifest.json` (SHA256 and byte count). `manifest.json` lists all other package files, not itself. The ZIP's externally supplied SHA256 protects the whole archive.
2. Find the actual host Python executable. Windows/Python 3.14 was tested; another platform/interpreter needs local tests. No pip dependencies are required.
3. Run tests from the extracted package root, with a verified interpreter: `python -B -X utf8 -m unittest discover -s DEV_STATE/dev-state-core/tests -v`.
4. Confirm stdout JSON is UTF-8. On Windows the portable launcher sets UTF-8 and calls the adjacent core. Set `DEV_STATE_PYTHON` to the verified executable; an invalid explicit override fails closed.
5. Edit JSON templates for the actual machine. Every path passed to the core, including `--spec`, MUST be absolute. Do not run unresolved placeholders.

Template edits are setup work, not changes to runtime source. Preserve JSON escaping for Windows paths. All identifiers use `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.

## 3. Manual core route (works without Hooks/Skills)

Choose exact `ROOT`, `TASK_ID`, `ENVIRONMENT` and `CONTEXT_KEY`. `ENVIRONMENT` is CODEX, BIONIC or OTHER. Never guess another chat's state. All operations require:

```text
<python> -X utf8 <absolute-core> <operation>
  --root <absolute-root> --task-id <task-id>
  --environment <CODEX|BIONIC|OTHER> --context-key <owner-context>
```

Operations and extra arguments:

| Operation | Extra arguments | Effect |
|---|---|---|
| init | --spec <absolute-init.json> | New owned state; never import another chat's state as current |
| status | --compact (or --full) | Read-only; compact JSON <=4096 bytes |
| update | --expected-generation N --spec <absolute-update.json> | Semantic progress is AI_DECLARED; CAS rejects stale writers |
| observe | --expected-generation N --spec <absolute-observe.json> | Fingerprint existing artifacts / authorities; OBSERVED receipt |
| verify | --expected-generation N --spec <absolute-verify.json> | Execute an explicitly authorized command and capture test evidence |
| validate | --full optional | Read-only structural/integrity validation |
| reconcile / recover | See core CLI help | Explicit repair only; never automatic during resume |

Use actual `status` generation before mutation and the returned generation for the next dependent operation. Stop on failed operations; do not increment generation by assumption. Never edit `current.json`, `previous.json`, STATUS.md, lock or receipt files directly. STATUS.md is a derived display.

Before init, fill artifact_roots with actual directories that may contain evidence; fill authority_declarations with only relevant requirement/design sources. Observe establishes file hashes. A changed file can make evidence STALE; re-observe only after considering whether the change is expected. Verify reruns tests only when needed. Evidence of hashes is not proof of the semantic accuracy of an AI's written report.

Read current machine status before resume. HASH_MATCH supports bounded restoration; STALE or MISMATCH requires targeted reconciliation. AI_DECLARED progress without test evidence is not a machine-tested PASS. Follow the returned diagnostics rather than silently switching roots. State file limit is 65,536 bytes; bound receipts/output as enforced by the core.

## 4. Codex setup

This is the optional Codex integration component, separate from the shared core.
It is the standard setup choice for Codex on another PC; manual core operation
remains possible without it. Do not install this component for Bionic.
See `DEV_STATE/codex-adapter-g7/SETUP.md` and run its isolated tests.
v1.1 adds `hook_source` and a compact-only refresh reminder for exit0/OK/HASH_MATCH.
The AI, not the Hook, decides whether clear material changes need saving.
Unchanged, unknown, unrelated, or read-only work must not produce writes.
The reminder does not authorize development resumption, tests, or other commands.
Actual live compact delivery and AI refresh/no-op behavior remain UNVERIFIED.

Deploy the package's `DEV_STATE` folder directly under the intended working root. Preserve runtime layout:

```text
<working-root>/DEV_STATE/dev-state-core/dev_state.py
<working-root>/DEV_STATE/codex-adapter-g7/dev_state_codex_hook.py
<working-root>/DEV_STATE/codex-sessions/<session_id>/
```

The Hook uses the nearest Git ancestor; without Git it uses the nearest ancestor containing the common-core marker. For a subdirectory of a Git repository, place DEV_STATE at that repository root. It never searches sibling projects. Determine the actual current session ID using host evidence; initialize with that exact ID as both task_id and context_key. The Hook never initializes absent state, so a different/new chat needs its own init.

Replace Python and adapter paths in `hooks.template.json`; merge the handler into the appropriate project Hook configuration while preserving all existing entries. Do not overwrite the entire existing config with the template or add the same handler at both user and project levels. Configure the platform-appropriate command; commandWindows is intended for Windows. Hook is SessionStart startup/resume/compact; clear is intentionally excluded. Runtime code stays unchanged.

Ask the user to review/trust the new exact Hook definition through the host's Hook UI. Do not programmatically forge trusted_hash. Then observe actual model-visible injection after restart/resume and later after a real compaction. A manual replay is an offline test only. Confirm exact root, task identity, current generation, integrity and coexistence with prior Hooks. Other-platform Hook invocation remains unverified until tested.

## 5. Bionic setup

Deploy only shared code at `<task-root>/tools/dev-state-core/` (core, schemas, launcher; tests may be retained for maintenance). Never put a chat's operation specs or state into the shared workspace.

State belongs to `<current-chat-scratchpad>/dev-state/<task-id>/`. Set task_id and context_key to that validated final component. Initialize a NEW state in the current chat's scratchpad. Do not copy another chat's state or reuse a different scratchpad.

Where an existing checkpoint guard supports DEV_STATE, add the exact pointer to TASK ROUTING using its normal commit procedure. If the guard lacks that key or containment check, adapt and test the guard under the user's authorized scope; do not bypass rejection. It must reject another chat's scratchpad, scratchpad-external roots and a dev-state path lacking a task component. Resolve real paths/junctions before containment checks. This project-specific checkpoint guard is intentionally not distributed here.

Use the host's supported Skill installation/update mechanism to add a small named step to the already-read resume Skill. Do not rely on a new Skill's automatic selection. Preserve Minimal Resume, stale-routing and authorization-firewall rules. Named step:

```text
validated DEV_STATE pointer absent -> existing resume path
pointer present -> derive exact task-id/context-key from final path component
invoke <task-root>/tools/dev-state-core/dev-state.ps1 status
  --root <validated-pointer> --task-id <final-component>
  --environment BIONIC --context-key <final-component> --compact
```

For non-Windows use verified host Python and an argument vector directly. Missing core/interpreter -> BLOCKED; wrong owner/root -> report mismatch; no other-location fallback. Resume never writes state, creates receipts or revives GO. If automatic integration cannot yet be adapted, use the explicit manual route with a validated chat-owned root and label automation unverified.

Test the named step in-session before observing a real handoff/compaction. Missing state is ABSENT, not a reason to create it during resume. Other PCs need independent Python/code-path verification. Files under shared workspace are not assumed synchronized between PCs.

## 6. Normal operation / migration

Update bounded semantic state at material work boundaries, not every turn. Record stage completion, next action, unresolved items and machine evidence when useful. Before switching development tasks, leave its state usable; do not rescan completed work without a finding.

Moving existing state to a new root/chat is outside this package's automatic support: root fingerprint and owner identity deliberately detect copying. Initialize destination state and re-establish relevant evidence there. Transferred summaries are reference, not current authority.

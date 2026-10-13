# Bionic integration reference

An adaptation reference derived from an existing local Bionic integration.
Not a universal installer, a new core, or a guarantee of target-model behavior.
Use the repository's common core and portable launcher; do not copy a machine's
Python path, live checkpoint, state, receipts or entire Skill/policy collection.
These source-only examples are not included in the existing v1.1.1 Release ZIP.
The repository MIT license applies.
For executed checks and remaining target-validation boundaries, see
[VALIDATION.md](VALIDATION.md).

## Start here — for the installing AI

1. Read [INTEGRATION.md](../../INTEGRATION.md), especially Bionic setup. Inspect
   the target's actual workspace, current-chat scratchpad, Python and supported
   Skill update mechanism. Do not invent paths or assume a named Skill exists.
2. Deploy the common core, schemas and portable `dev-state.ps1` under
   `<task-root>/tools/dev-state-core/`. Keep state and operation specs out of this
   shared workspace. Set `DEV_STATE_PYTHON` to the verified host executable for
   the relevant invocation; do not copy a developer's interpreter path.
3. Use the supplied operation templates and CLI contract to initialize a NEW
   state at `<current-chat-scratchpad>/dev-state/<task-id>/`. Bind environment
   `BIONIC`, task_id and context_key to the validated final path component.
   Use only identifier characters allowed by the core. Do not import old state.
4. If a checkpoint system exists, implement/confirm the contract in
   [checkpoint-pointer.md](checkpoint-pointer.md). Use its supported update
   procedure; preserve all other sections, authorization and validation rules.
5. Add [resume-step.example.md](resume-step.example.md) to the existing resume
   path that is actually read. Add [update-rules.example.md](update-rules.example.md)
   to the appropriate editable policy. These are fragments, not installable
   standalone Skills: do not overwrite whole files or depend on new Skill
   auto-selection. Obtain required user approval using the host's supported
   installation/update mechanism. If integration is unavailable, retain manual
   CLI operation and report automatic recovery as UNVERIFIED.
6. Run isolated checks below, then invoke the named step in the target chat.
   Observe a real compaction/handoff later. Report machine checks, actual model
   behavior and remaining uncertainty separately. User acceptance is the final
   installation decision.

## Validation

From a repository checkout with verified host Python:

```text
<python> -B -X utf8 -m unittest discover -s DEV_STATE/dev-state-core/tests -v
<python> -B -X utf8 examples/bionic/test_reference.py
```

The reference tests use disposable state only. They cover core/launcher behavior,
not a real Bionic Skill or the project-specific checkpoint guard. Complete the
guard cases in checkpoint-pointer.md independently on the target.

In-session validation: valid pointer -> compact status; compare exact task/root,
identity, generation and state/receipt hashes before/after the read. Missing
pointer/state must not create state. Mismatch must not fall back to another root.
For the optional refresh step, check separately that known material changes are
saved and unchanged/unknown state produces no write. Preserve current permission
rules; never use saved progress as permission to resume execution.

Real client validation is separate: confirm that the resume path was actually
read and invoked after a real handoff/compaction. A scripted invocation, manual
replay or passing unit test does not establish automatic delivery. Existing
user observations indicate useful recovery behavior, but do not certify every
Bionic version or model.

## State lifetime and safe removal

Code can be shared within a project; progress is chat-owned. Local files do not
automatically synchronize across PCs. Do not use cloud-synced concurrent writers.
Establish Git exclusions before creating any live state, private specs or receipts.

A Bionic project move may change or remove a chat scratchpad. Confirm retention
behavior and back up important state outside a potentially disposable scratchpad
before moves/deletion. A backup is not automatically adopted live state: root and
owner binding may reject copying. Follow INTEGRATION.md's migration contract;
do not edit fingerprints to force acceptance.

For removal, back up data, remove only this integration's exact additions using
the supported host mechanism, and retain state unless separately authorized for
deletion. Never remove parent Skill folders, unrelated policies or checkpoints.

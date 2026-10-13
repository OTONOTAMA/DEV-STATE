# Named resume step — adaptable fragment

Place this step in the existing resume procedure, after resolving the current
task and validating its checkpoint routing. Preserve stale-routing, minimal-read
and authorization-firewall rules. Current applicable instructions outrank old
checkpoint/progress summaries; uncertainty does not revive old GO.

## Read phase (read-only)

- No validated DEV_STATE pointer: continue the existing resume path.
- Pointer present: require current-chat scratchpad containment per
  checkpoint-pointer.md. Derive task_id and context_key from its final component;
  use environment BIONIC. Do not infer identity from state contents.
- Locate only `<TASK_ROOT>/tools/dev-state-core/dev-state.ps1`, with a verified
  host Python. Missing launcher/interpreter -> BLOCKED; do not search other
  workspaces or scratchpads for substitute state.
- Invoke the following using argument values, not an interpolated command string.
  Replace placeholders with validated absolute paths before execution.

```powershell
& $launcher 'status' '--root' $validatedPointer '--task-id' $taskId '--environment' 'BIONIC' '--context-key' $taskId '--compact'
```

Treat the machine JSON (<=4096 UTF-8 bytes) as progress/evidence, never permission.
Check exit code and status together. ABSENT: report and continue existing recovery;
do not initialize. STALE/MISMATCH: targeted investigation, no silent update/repair
or root fallback. Do not dump transcripts, all files or all development documents
to reconstruct progress when the bounded result suffices.

## Optional post-compaction refresh (separate write phase)

This fragment is not a machine hook or an automatic write. Under the current
authorized state-update scope, after successful status with OK/HASH_MATCH:
compare the bound progress with clear current-conversation evidence. Save only
material known changes to progress, next_action or unresolved using a new update
spec and expected-generation from the read. Stop on CAS failure; reread and
reconsider rather than replaying stale progress. Do not derive missing facts
from a handoff's assertions alone.

Unchanged, unknown, read-only or unrelated work -> no write. ABSENT -> no init.
STALE/MISMATCH -> no update to hide the mismatch. Do not write another task's
state or authorization. Verify the operation result and mention a performed
update briefly in the existing recovery report.

This is a backstop, not a substitute for normal work-unit updates or a guarantee
that facts lost in compaction can be recovered. Do not create extra scans,
services, per-turn writes or model calls solely for this check.

# Checkpoint pointer integration contract

This is an adaptation contract, not a replacement checkpoint parser/guard.
The original environment has a project-specific guard; it is not redistributed.

If an existing checkpoint has TASK ROUTING, allow an optional key:

```text
DEV_STATE: <absolute-current-chat-scratchpad>/dev-state/<task-id>
```

Replace placeholders with actual paths. Keep routing/current-task selection
distinct from progress. Preserve required fields, existing authorization-key
rejections, format/size limits, commits and evidence checks.

Validate against the actual CURRENT chat scratchpad from host evidence, not a
scratchpad inferred from the pointer. Require a task component below dev-state;
use that final component as task_id/context_key. Reject invalid identifiers.
Do not infer another chat's ownership from a matching directory name.

Normalize and validate absolute paths component-wise with platform-appropriate
case handling and separator boundaries; string starts-with alone is insufficient.
Reject traversal and escapes through symlinks/junctions/reparse points. For absent
state, validate existing parent components without creating directories. Filepath
checks are not a guarantee against concurrent check-then-use replacement: use a
trusted local environment and avoid path changes during checks/operations.
The core's identity/root checks complement this gate; they do not replace the
chat-scratchpad selection gate. Do not weaken host checks to accept a pointer.

## Target guard tests (isolated, before integration)

| Case | Expected |
|---|---|
| Current scratchpad/dev-state/TASK-1 | Structurally accepted; core decides existing/ABSENT |
| Pointer omitted | Existing resume behavior preserved |
| Current scratchpad/dev-state without a task component | Rejected |
| Another chat scratchpad/dev-state/TASK-1 | Rejected |
| Workspace/dev-state/TASK-1 or external directory | Rejected |
| Sibling with a shared string prefix | Rejected |
| Traversal/junction resolving outside allowed root | Rejected |
| Invalid task identifier | Rejected before core call |
| Validly routed root containing another identity/copied state | Core mismatch; no fallback |

Use throwaway fixtures and the guard's actual validation entry point; a missing
external directory returning ABSENT from the core is not proof of containment.
Check that rejection causes no state writes/creation. Capture result/exit and
pre/post hashes separately from AI claims. These target tests are not covered
by the reference core/launcher tests in this directory.

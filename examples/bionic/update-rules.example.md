# DEV_STATE update rules — editable policy fragment

For work with a validated DEV_STATE pointer, save bounded, confirmed work state
when an independent work unit becomes settled, before starting the next one.

Triggers: a test/investigation/design/implementation/verification result
(PASS/FAIL/BLOCKED), phase change, material evidence/unresolved changes, or an
intentional stop/task switch. Record independently completed tests as they
finish; a single indivisible batch run may be recorded once immediately after
completion. Do not defer multiple separate completed units to a final report.

Save confirmed progress, results, evidence pointers, unresolved items and a short
next_action. Use the normal CLI with current generation/CAS; check its result.
No changes -> no write; do not save every conversation turn. AI_DECLARED progress
and machine evidence stay separate. Unknown is not PASS; a command PASS is not
proof that the whole task is complete. Never store GO/authorization or reuse
another task's state. Do not edit canonical JSON/receipts directly.

Resume/checkpoint refresh checks are backstops, not permission to delay normal
updates. A forced stop or conversation rewind may leave newer disk state than
the visible conversation. Compare current task/identity and machine status;
report targeted discrepancies and preserve evidence rather than overwriting
them from an older summary. Rewinding chat does not rewind filesystem state.

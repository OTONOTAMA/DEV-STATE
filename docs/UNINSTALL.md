# Safe removal

1. Stop writes to this chat's state. Back up its state and receipts if needed; they can contain private local paths and captured command output. Do not publish them.
2. Remove only the installed DEV_STATE handler from the appropriate Hook configuration, keeping other handlers. Review trust changes through the host's normal UI. Remove only the DEV_STATE named step/pointer through the Bionic host's supported workflow, preserving unrelated rules.
3. Restart the client and confirm DEV_STATE no longer injects state while other hooks/resume steps remain functional.
4. Keep chat-owned state until you decide it is no longer needed. Remove only the exact deployed DEV_STATE code folder after confirming no other chat relies on that shared code. Do not delete the entire workspace or scratchpad.

Updates should preserve state and keep a recoverable copy of old code/configuration. Never overwrite current.json or receipts to upgrade code. Manual uninstallation is intentional; this package does not recursively delete user data.

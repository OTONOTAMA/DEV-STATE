# Validation scope

`python -B -X utf8 tools/release.py` runs the core and isolated adapter unittest suites, Windows launcher smoke checks and a real core/adapter fixture before creating the ZIP. The generated `dist/validation.json` records actual counts and skipped tests. It is build evidence, not target-client acceptance.

The real fixture initializes temporary CODEX-owned state, invokes the adapter with startup/resume/compact events and verifies no state bytes changed; compact carries the bounded refresh reminder. It never changes installed hooks, skills or live progress. The adapter unittest suite mocks the status subprocess for failure/budget scenarios; this is distinct from the real fixture.

Core tests use synthetic IDs and temporary artifacts. A symlink containment test may be skipped when OS permissions prevent creating a link; a skip is not PASS. Windows/Python 3.14 is the current validation target. Other operating systems and Python versions are not established by these tests.

Windows launcher smoke tests use process-local `-ExecutionPolicy Bypass` for the inspected bundled script and a native PowerShell module path in the test child environment. They do not change system/user execution policy, PATH or installed settings.

SHA256 and ZIP readback establish artifact consistency, not semantic correctness or universal secret detection. The explicit shipping allowlist excludes real state. The privacy scan rejects personal Windows home paths and recognizable credential patterns; inspect future additions manually too.

Every target client must independently establish Hook definition trust and actual startup/resume/compact delivery. A simulated event does not establish real compaction behavior, AI compliance, allowance savings or guaranteed recovery time. The repository does not ship the original project's Bionic checkpoint guard or protected resume Skills.

There is no automatic state migration; copying current.json to another root/owner deliberately fails identity binding. No stored progress, summary or receipt creates execution authorization. The tool is not a security sandbox. A verify command can modify external resources according to its own behavior.

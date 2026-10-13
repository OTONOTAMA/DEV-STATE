"""Isolated common-core/portable-launcher checks, not live Bionic integration."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "DEV_STATE/dev-state-core/dev_state.py"
LAUNCHER = CORE.with_name("dev-state.ps1")


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="devstate-bionic-reference-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.state = self.work / "scratchpad/dev-state/TASK-1"
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env["DEV_STATE_PYTHON"] = sys.executable

    def args(self, root=None, task="TASK-1"):
        return ["status", "--root", str(root or self.state), "--task-id", task,
                "--environment", "BIONIC", "--context-key", task, "--compact"]

    def run_cli(self, args, launcher=False):
        if launcher:
            ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            command = [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                       "Bypass", "-File", str(LAUNCHER)]
            self.env["PSModulePath"] = str(ps.parent / "Modules")
        else:
            command = [sys.executable, "-B", "-X", "utf8", str(CORE)]
        result = subprocess.run(command + args, env=self.env, capture_output=True, timeout=20)
        return result, json.loads(result.stdout.decode("utf-8", "strict"))

    def init(self):
        spec = self.work / "init.json"
        spec.write_text(json.dumps({"spec_version": "1.0", "phase": "reference-test",
            "active_item_id": None, "next_action": "Fixture only",
            "artifact_roots": [str(self.work)], "items": [], "unresolved": [],
            "authority_declarations": []}), encoding="utf-8")
        args = self.args()[:-1]
        args[0] = "init"
        result, data = self.run_cli(args + ["--spec", str(spec)])
        self.assertEqual(result.returncode, 0, data)

    def snapshot(self):
        return {p.relative_to(self.state).as_posix(): p.read_bytes()
                for p in self.state.rglob("*") if p.is_file()}

    def test_absent_does_not_initialize(self):
        result, data = self.run_cli(self.args())
        self.assertEqual(data["status"], "ABSENT")
        self.assertFalse(self.state.exists())

    def test_bound_read_is_compact_and_unchanged(self):
        self.init()
        before = self.snapshot()
        result, data = self.run_cli(self.args())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["data"]["reconciliation"], "HASH_MATCH")
        self.assertLessEqual(len(result.stdout), 4096)
        self.assertEqual(before, self.snapshot())

    def test_wrong_identity_is_not_adopted(self):
        self.init()
        before = self.snapshot()
        result, data = self.run_cli(self.args(task="OTHER-TASK"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "MISMATCH")
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(os.name == "nt", "Windows launcher only")
    def test_launcher_reads_bound_state(self):
        self.init()
        before = self.snapshot()
        result, data = self.run_cli(self.args(), launcher=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data["status"], "OK")
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(os.name == "nt", "Windows launcher only")
    def test_invalid_explicit_python_fails_closed(self):
        self.env["DEV_STATE_PYTHON"] = str(self.work / "nonexistent-python.exe")
        result, data = self.run_cli(self.args(), launcher=True)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(data["status"], "BLOCKED")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

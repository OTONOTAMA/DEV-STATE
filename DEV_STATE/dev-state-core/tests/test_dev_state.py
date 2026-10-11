import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "dev_state.py"


class DevStateTests(unittest.TestCase):
    def setUp(self):
        run_root = Path(__file__).resolve().parents[2] / "test-runs"
        run_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="dev-state-test-", dir=str(run_root))
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.artifacts = self.base / "artifacts"
        self.artifacts.mkdir()
        (self.artifacts / "日本語.txt").write_text("こんにちは\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, command, *extra, expect=None):
        common = [sys.executable, str(CORE), command, "--root", str(self.root), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1"]
        p = subprocess.run(common + list(extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.stderr, b"", p.stderr.decode("utf-8", "replace"))
        self.assertTrue(p.stdout.endswith(b"\n"), p.stdout)
        value = json.loads(p.stdout.decode("utf-8"))
        if expect is not None:
            self.assertEqual(p.returncode, expect, value)
        return p.returncode, value

    def write_json(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def init(self):
        spec = {
            "spec_version": "1.0", "phase": "implementation", "active_item_id": "core",
            "next_action": "run tests", "artifact_roots": [str(self.artifacts)],
            "items": [{"item_id": "core", "summary": "common core", "progress": "IN_PROGRESS", "basis": "AI_DECLARED"}],
            "unresolved": [], "authority_declarations": []
        }
        return self.call("init", "--spec", str(self.write_json("init.json", spec)), expect=0)

    def test_init_status_unicode_and_compact_budget(self):
        _, init = self.init()
        self.assertEqual(init["generation"], 1)
        code, status = self.call("status", "--compact", expect=0)
        self.assertEqual(code, 0)
        self.assertEqual(status["status"], "OK")
        self.assertLessEqual(len(json.dumps(status, ensure_ascii=False, separators=(",", ":")).encode()), 4096)
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["owner_context"]["context_key"], "BAM-P1")

    def test_unknown_spec_key_and_generation_cas(self):
        self.init()
        spec = {"spec_version": "1.0", "set": {"next_action": "日本語"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": [], "extra": 1}
        _, out = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("bad.json", spec)), expect=2)
        self.assertEqual(out["status"], "INVALID")
        good = dict(spec); good.pop("extra")
        self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("good.json", good)), expect=0)
        _, stale = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("stale.json", good)), expect=3)
        self.assertEqual(stale["status"], "STALE")

    def test_observe_and_verify_receipts(self):
        self.init()
        observe = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "unicode", "path": str(self.artifacts / "日本語.txt"), "role": "roundtrip"}], "authority_ids": []}
        self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("observe.json", observe)), expect=0)
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "echo", "argv": [sys.executable, "-c", "print('PASS')"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": [{"artifact_id": "unicode", "path": str(self.artifacts / "日本語.txt"), "role": "roundtrip"}]}
        _, out = self.call("verify", "--expected-generation", "2", "--spec", str(self.write_json("verify.json", verify)), expect=0)
        self.assertEqual(out["data"]["result"], "PASS")
        self.assertTrue(list((self.root / "receipts").glob("*.json")))

    def test_verify_timeout_is_bounded(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "timeout", "argv": [sys.executable, "-c", "import time; time.sleep(30)"], "cwd": str(self.artifacts), "timeout_seconds": 1, "success_exit_codes": [0], "required_artifacts": []}
        started = time.monotonic()
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("timeout.json", verify)), expect=1)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(out["data"]["result"], "TIMEOUT")

    def test_bom_and_prohibited_input_rejected(self):
        self.root.mkdir(parents=True)
        bom = self.base / "bom.json"
        bom.write_bytes(b"\xef\xbb\xbf{}")
        _, out = self.call("init", "--spec", str(bom), expect=1)
        self.assertEqual(out["status"], "INVALID")
        spec = {"spec_version": "1.0", "phase": "x", "active_item_id": None, "next_action": "x", "artifact_roots": [str(self.artifacts)], "items": [], "unresolved": [], "authority_declarations": [], "authorization": "no"}
        _, out = self.call("init", "--spec", str(self.write_json("prohibited.json", spec)), expect=2)
        self.assertEqual(out["diagnostics"][0]["code"], "AUTHORITY_FIELD_PROHIBITED")

    def test_init_existing_and_corrupt_current_fail_closed(self):
        self.init()
        before = (self.root / "current.json").read_bytes()
        _, out = self.call("init", "--spec", str(self.write_json("again.json", {"spec_version": "1.0", "phase": "x", "active_item_id": None, "next_action": "x", "artifact_roots": [str(self.artifacts)], "items": [], "unresolved": [], "authority_declarations": []})), expect=1)
        self.assertEqual(out["status"], "MISMATCH")
        (self.root / "current.json").write_bytes(b"not-json")
        spec = {"spec_version": "1.0", "set": {"next_action": "must stop"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        _, out = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("corrupt-update.json", spec)), expect=1)
        self.assertEqual(out["status"], "INVALID")
        self.assertEqual((self.root / "current.json").read_bytes(), b"not-json")

    def test_observe_outside_allowlist_and_unknown_authority_rejected(self):
        self.init()
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "outside", "path": str(outside), "role": "bad"}], "authority_ids": []}
        _, out = self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("outside.json", spec)), expect=2)
        self.assertEqual(out["diagnostics"][0]["code"], "ARTIFACT_OUTSIDE_ROOT")
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [], "authority_ids": ["missing"]}
        _, out = self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("missing-authority.json", spec)), expect=2)
        self.assertEqual(out["diagnostics"][0]["code"], "AUTHORITY_MISSING")

    def test_verify_failure_does_not_promote_and_shell_string_rejected(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "fail", "argv": [sys.executable, "-c", "raise SystemExit(7)"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("fail.json", verify)), expect=1)
        self.assertEqual(out["data"]["result"], "FAIL")
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertNotEqual(state["items"][0]["basis"], "MACHINE_VERIFIED")
        verify["argv"] = "python -c pass"
        _, out = self.call("verify", "--expected-generation", "2", "--spec", str(self.write_json("shell.json", verify)), expect=2)
        self.assertEqual(out["status"], "INVALID")

    def test_receipt_mutation_and_status_regeneration(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "pass", "argv": [sys.executable, "-c", "print('ok')"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("pass.json", verify)), expect=0)
        receipt = next((self.root / "receipts").glob("*.json"))
        receipt.write_text(receipt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        _, out = self.call("status", "--compact", expect=1)
        self.assertEqual(out["status"], "INVALID")
        # Restore by reinitializing a fresh root, then ensure a normal commit regenerates STATUS.md.
        self.tmp.cleanup()
        self.setUp()
        self.init()
        (self.root / "STATUS.md").write_text("MANUAL EDIT\n", encoding="utf-8")
        spec = {"spec_version": "1.0", "set": {"next_action": "regenerated"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("regen.json", spec)), expect=0)
        self.assertIn("regenerated", (self.root / "STATUS.md").read_text(encoding="utf-8"))

    def test_relevant_artifact_becomes_stale(self):
        self.init()
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "unicode", "path": str(self.artifacts / "日本語.txt"), "role": "roundtrip"}], "authority_ids": []}
        self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("artifact.json", spec)), expect=0)
        (self.artifacts / "日本語.txt").write_text("変更\n", encoding="utf-8")
        _, out = self.call("status", "--compact", expect=1)
        self.assertEqual(out["status"], "STALE")

    def test_worst_case_compact_is_bounded(self):
        self.init()
        items = [{"item_id": f"item-{i:03d}", "summary": "項目" * 40, "progress": "IN_PROGRESS", "basis": "AI_DECLARED"} for i in range(1, 128)]
        spec = {"spec_version": "1.0", "set": {"next_action": "次" * 300}, "upsert_items": items, "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("large.json", spec)), expect=0)
        p = subprocess.run([sys.executable, str(CORE), "status", "--root", str(self.root), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--compact"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 0)
        self.assertLessEqual(len(p.stdout.rstrip(b"\n")), 4096)
        json.loads(p.stdout)

    def test_output_limit_is_bounded(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "large-output", "argv": [sys.executable, "-c", "import sys; sys.stdout.write('x'*17000000)"], "cwd": str(self.artifacts), "timeout_seconds": 30, "success_exit_codes": [0], "required_artifacts": []}
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("large-output.json", verify)), expect=1)
        self.assertEqual(out["data"]["result"], "OUTPUT_LIMIT")

    def test_semantic_update_downgrades_verified_basis(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "pass", "argv": [sys.executable, "-c", "print('ok')"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("verified.json", verify)), expect=0)
        spec = {"spec_version": "1.0", "set": {}, "upsert_items": [{"item_id": "core", "summary": "changed meaning", "progress": "IN_PROGRESS", "basis": "AI_DECLARED"}], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        self.call("update", "--expected-generation", "2", "--spec", str(self.write_json("semantic.json", spec)), expect=0)
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["items"][0]["basis"], "AI_DECLARED")

    def test_verify_generation_change_reports_orphan_receipt(self):
        self.init()
        update_spec = {"spec_version": "1.0", "set": {"next_action": "raced"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        update_path = self.write_json("race-update.json", update_spec)
        script = self.artifacts / "race.py"
        script.write_text("import subprocess,sys,time\ntime.sleep(0.2)\nsubprocess.run([sys.executable, r'" + str(CORE) + "', 'update', '--root', r'" + str(self.root) + "', '--task-id', 'BAM-P1', '--environment', 'BIONIC', '--context-key', 'BAM-P1', '--expected-generation', '1', '--spec', r'" + str(update_path) + "'], check=False)\ntime.sleep(0.2)\n", encoding="utf-8")
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "race", "argv": [sys.executable, str(script)], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("race-verify.json", verify)), expect=3)
        self.assertEqual(out["status"], "STALE")
        self.assertIn("orphan_receipt", out["data"])
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["generation"], 2)

    def test_valid_receipt_identity_mismatch_is_not_newest_wins(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "pass", "argv": [sys.executable, "-c", "print('ok')"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("identity.json", verify)), expect=0)
        receipt_path = next((self.root / "receipts").glob("*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["task_id"] = "OTHER-TASK"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state_path = self.root / "current.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        ref = next(r for r in state["items"][0]["receipt_refs"] if r["path"].endswith(receipt_path.name))
        ref["sha256"] = __import__("hashlib").sha256(receipt_path.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _, out = self.call("status", "--compact", expect=1)
        self.assertEqual(out["status"], "MISMATCH")

    def test_duplicate_json_key_and_init_over_corrupt_current(self):
        duplicate = self.base / "duplicate.json"
        duplicate.write_bytes(b'{"spec_version":"1.0","spec_version":"1.0"}')
        _, out = self.call("init", "--spec", str(duplicate), expect=1)
        self.assertEqual(out["status"], "INVALID")
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "current.json").write_bytes(b"broken")
        spec = {"spec_version": "1.0", "phase": "x", "active_item_id": None, "next_action": "x", "artifact_roots": [str(self.artifacts)], "items": [], "unresolved": [], "authority_declarations": []}
        _, out = self.call("init", "--spec", str(self.write_json("init-corrupt.json", spec)), expect=1)
        self.assertEqual(out["status"], "MISMATCH")
        self.assertEqual((self.root / "current.json").read_bytes(), b"broken")

    def test_previous_recovery_uses_valid_previous_and_new_generation(self):
        self.init()
        spec = {"spec_version": "1.0", "set": {"next_action": "second"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("second.json", spec)), expect=0)
        (self.root / "current.json").write_bytes(b"corrupt-current")
        bad_hash = __import__("hashlib").sha256(b"corrupt-current").hexdigest()
        _, out = self.call("recover", "--current-invalid-sha256", bad_hash, expect=0)
        self.assertEqual(out["generation"], 2)
        recovered = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        previous = json.loads((self.root / "previous.json").read_text(encoding="utf-8"))
        self.assertEqual(recovered["generation"], 2)
        self.assertEqual(previous["generation"], 1)

    def test_compact_is_deterministic_and_unrelated_file_is_ignored(self):
        self.init()
        first = subprocess.run([sys.executable, str(CORE), "status", "--root", str(self.root), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--compact"], stdout=subprocess.PIPE, check=True).stdout
        second = subprocess.run([sys.executable, str(CORE), "status", "--root", str(self.root), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--compact"], stdout=subprocess.PIPE, check=True).stdout
        self.assertEqual(first, second)
        (self.artifacts / "unrelated.txt").write_text("not linked", encoding="utf-8")
        _, out = self.call("status", "--compact", expect=0)
        self.assertEqual(out["status"], "OK")

    def test_copied_root_fails_owner_binding(self):
        self.init()
        copied = self.base / "copied-state"
        import shutil
        shutil.copytree(self.root, copied)
        p = subprocess.run([sys.executable, str(CORE), "status", "--root", str(copied), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--compact"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "MISMATCH")

    def test_writer_lock_contention_is_bounded(self):
        import importlib.util
        loader = importlib.util.spec_from_file_location("dev_state_lock_test", CORE)
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        module.LOCK_TIMEOUT = 0.2
        with module.writer_lock(self.root):
            result = []
            def contender():
                try:
                    with module.writer_lock(self.root):
                        result.append("acquired")
                except module.CoreError as exc:
                    result.append(exc.code)
            import threading
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["WRITER_LOCK_BUSY"])

    def test_crashed_writer_lock_is_released_by_os(self):
        self.init()
        child_code = "import importlib.util,os,sys; s=importlib.util.spec_from_file_location('ds',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); r=__import__('pathlib').Path(sys.argv[2]);\nwith m.writer_lock(r): os._exit(0)"
        p = subprocess.Popen([sys.executable, "-c", child_code, str(CORE), str(self.root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(p.wait(timeout=5), 0)
        # A later writer can acquire the same kernel-held lock after the crash.
        spec = {"spec_version": "1.0", "set": {"next_action": "after crash"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        _, out = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("after-crash.json", spec)), expect=0)
        self.assertEqual(out["status"], "OK")

    def test_root_binding_rejects_other_root(self):
        self.init()
        other = self.base / "other"
        other.mkdir()
        p = subprocess.run([sys.executable, str(CORE), "status", "--root", str(other), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--compact"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "ABSENT")

    def test_identifier_and_size_bounds(self):
        invalid_id = {
            "spec_version": "1.0", "phase": "implementation", "active_item_id": "bad/id",
            "next_action": "run tests", "artifact_roots": [str(self.artifacts)],
            "items": [], "unresolved": [], "authority_declarations": []
        }
        _, out = self.call("init", "--spec", str(self.write_json("invalid-id.json", invalid_id)), expect=2)
        self.assertEqual(out["status"], "INVALID")
        self.tmp.cleanup()
        self.setUp()
        oversized = {
            "spec_version": "1.0", "phase": "x" * 129, "active_item_id": None,
            "next_action": "run tests", "artifact_roots": [str(self.artifacts)],
            "items": [], "unresolved": [], "authority_declarations": []
        }
        _, out = self.call("init", "--spec", str(self.write_json("oversized-phase.json", oversized)), expect=1)
        self.assertEqual(out["status"], "INVALID")

    def test_root_traversal_rejected(self):
        self.init()
        outside = self.base / "outside-traversal.txt"
        outside.write_text("outside", encoding="utf-8")
        traversal = self.artifacts / ".." / outside.name
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "escape", "path": str(traversal), "role": "escape"}], "authority_ids": []}
        _, out = self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("traversal.json", spec)), expect=2)
        self.assertEqual(out["diagnostics"][0]["code"], "ARTIFACT_OUTSIDE_ROOT")

    @unittest.skipUnless(os.name == "nt", "Windows path normalization case")
    def test_windows_case_and_alternate_spelling(self):
        self.init()
        alternate = str(self.artifacts).upper() + "\\.\\日本語.txt"
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "unicode", "path": alternate, "role": "roundtrip"}], "authority_ids": []}
        _, out = self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("case.json", spec)), expect=0)
        self.assertEqual(out["status"], "OK")

    def test_symlink_escape_rejected(self):
        outside = self.base / "symlink-outside"
        outside.mkdir()
        (outside / "probe.txt").write_text("outside", encoding="utf-8")
        link = self.artifacts / "symlink-escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            if os.name != "nt":
                self.skipTest(f"symlink unavailable: {exc}")
            result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                self.skipTest(f"symlink and junction unavailable: {exc}; {result.stdout.decode('utf-8', 'replace').strip()}")
        self.init()
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "link", "path": str(link / "probe.txt"), "role": "escape"}], "authority_ids": []}
        _, out = self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("symlink.json", spec)), expect=2)
        self.assertEqual(out["diagnostics"][0]["code"], "ARTIFACT_OUTSIDE_ROOT")

    def test_two_writers_same_generation_one_commit(self):
        self.init()
        spec = {"spec_version": "1.0", "set": {"next_action": "raced update"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        spec_path = self.write_json("same-generation.json", spec)
        common = [sys.executable, str(CORE), "update", "--root", str(self.root), "--task-id", "BAM-P1", "--environment", "BIONIC", "--context-key", "BAM-P1", "--expected-generation", "1", "--spec", str(spec_path)]
        first = subprocess.Popen(common, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(common, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        first_out, first_err = first.communicate(timeout=10)
        second_out, second_err = second.communicate(timeout=10)
        self.assertEqual(first_err, b"")
        self.assertEqual(second_err, b"")
        self.assertEqual(sorted([first.returncode, second.returncode]), [0, 3])
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["generation"], 2)

    def test_current_replacement_hash_and_schema(self):
        self.init()
        spec = {"spec_version": "1.0", "set": {"next_action": "replaced"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("replacement.json", spec)), expect=0)
        current = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        previous = json.loads((self.root / "previous.json").read_text(encoding="utf-8"))
        self.assertEqual(current["schema_version"], "1.0")
        self.assertEqual(current["generation"], 2)
        self.assertEqual(previous["generation"], 1)
        self.assertIn("Generation: 2", (self.root / "STATUS.md").read_text(encoding="utf-8"))

    def test_arbitrary_external_pass_file_not_verified(self):
        self.init()
        (self.artifacts / "external-pass.json").write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
        _, out = self.call("status", "--compact", expect=0)
        self.assertEqual(out["status"], "OK")
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["items"][0]["basis"], "AI_DECLARED")

    def test_validate_reports_orphan_receipt_or_staging(self):
        self.init()
        (self.root / "receipts" / "orphan.json").write_text("{}\n", encoding="utf-8")
        (self.root / ".staging" / "orphan.tmp").write_text("staged", encoding="utf-8")
        _, out = self.call("validate", "--full", expect=1)
        codes = {entry.get("code") for entry in out.get("diagnostics", [])}
        self.assertTrue({"ORPHAN_RECEIPT", "ORPHAN_STAGING"} & codes)

    def test_stderr_output_limit(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "large-stderr", "argv": [sys.executable, "-c", "import sys; sys.stderr.write('x'*17000000)"], "cwd": str(self.artifacts), "timeout_seconds": 30, "success_exit_codes": [0], "required_artifacts": []}
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("large-stderr.json", verify)), expect=1)
        self.assertEqual(out["data"]["result"], "OUTPUT_LIMIT")

    def test_observe_marks_artifact_machine_observed(self):
        self.init()
        spec = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "unicode", "path": str(self.artifacts / "日本語.txt"), "role": "roundtrip"}], "authority_ids": []}
        self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("observed.json", spec)), expect=0)
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["items"][0]["basis"], "MACHINE_OBSERVED")

    def test_state_hard_limit_rejects_oversized_candidate(self):
        self.init()
        items = [{"item_id": f"large-{i:03d}", "summary": "x" * 1024, "progress": "IN_PROGRESS", "basis": "AI_DECLARED"} for i in range(128)]
        spec = {"spec_version": "1.0", "set": {"next_action": "oversized"}, "upsert_items": items, "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        _, out = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("oversized-state.json", spec)), expect=1)
        self.assertEqual(out["status"], "INVALID")
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["generation"], 1)

    def test_init_over_valid_current_refuses_without_overwrite(self):
        self.init()
        before = (self.root / "current.json").read_bytes()
        _, out = self.call("init", "--spec", str(self.write_json("second-init.json", {
            "spec_version": "1.0", "phase": "implementation", "active_item_id": "core",
            "next_action": "must not replace", "artifact_roots": [str(self.artifacts)],
            "items": [{"item_id": "core", "summary": "same", "progress": "IN_PROGRESS", "basis": "AI_DECLARED"}],
            "unresolved": [], "authority_declarations": []
        })), expect=1)
        self.assertEqual(out["status"], "MISMATCH")
        self.assertEqual((self.root / "current.json").read_bytes(), before)

    def test_receipt_before_current_fault_keeps_old_state(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "commit-race", "argv": [sys.executable, "-c", "print('pass')"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        verify_path = self.write_json("first-verify.json", verify)
        child_code = '''
import importlib.util
import pathlib
import sys
core, root, spec_path = sys.argv[1:]
loader = importlib.util.spec_from_file_location("faulted_dev_state", core)
module = importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)
original = module.write_bytes_atomic
def fail_before_current(path, data):
    if pathlib.Path(path).name == "current.json":
        raise module.CoreError("FAILED", "INJECTED_CURRENT_REPLACE_FAULT", "injected before current replacement", 4)
    return original(path, data)
module.write_bytes_atomic = fail_before_current
raise SystemExit(module.main([
    "verify", "--root", root, "--task-id", "BAM-P1", "--environment", "BIONIC",
    "--context-key", "BAM-P1", "--expected-generation", "1", "--spec", spec_path
]))
'''
        before = (self.root / "current.json").read_bytes()
        p = subprocess.run([sys.executable, "-c", child_code, str(CORE), str(self.root), str(verify_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 4, p.stdout.decode("utf-8", "replace"))
        self.assertEqual(p.stderr, b"")
        failure = json.loads(p.stdout.decode("utf-8"))
        self.assertEqual(failure["diagnostics"][0]["code"], "INJECTED_CURRENT_REPLACE_FAULT")
        self.assertEqual((self.root / "current.json").read_bytes(), before)
        receipt_files = list((self.root / "receipts").glob("*.json"))
        self.assertEqual(len(receipt_files), 1)
        state = json.loads(before.decode("utf-8"))
        self.assertEqual(state["generation"], 1)
        self.assertFalse(state["items"][0]["receipt_refs"])

    def test_corrupt_current_mutation_attempt_fails_closed(self):
        self.init()
        current = self.root / "current.json"
        current.write_bytes(b"corrupt")
        spec = {"spec_version": "1.0", "set": {"next_action": "must not mutate"}, "upsert_items": [], "upsert_unresolved": [], "resolve_unresolved_ids": [], "declare_authority_refs": [], "remove_authority_ids": []}
        _, out = self.call("update", "--expected-generation", "1", "--spec", str(self.write_json("corrupt-update-2.json", spec)), expect=1)
        self.assertEqual(out["status"], "INVALID")
        self.assertEqual(current.read_bytes(), b"corrupt")

    def test_verify_nonzero_does_not_promote_verified_basis(self):
        self.init()
        verify = {"spec_version": "1.0", "item_id": "core", "verification_surface": "selftest", "command_or_test_id": "nonzero", "argv": [sys.executable, "-c", "raise SystemExit(9)"], "cwd": str(self.artifacts), "timeout_seconds": 10, "success_exit_codes": [0], "required_artifacts": []}
        _, out = self.call("verify", "--expected-generation", "1", "--spec", str(self.write_json("nonzero.json", verify)), expect=1)
        self.assertEqual(out["data"]["result"], "FAIL")
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertNotEqual(state["items"][0]["basis"], "MACHINE_VERIFIED")

    def test_reconcile_reports_stale_artifact_without_auto_adoption(self):
        self.init()
        observe = {"spec_version": "1.0", "item_id": "core", "artifacts": [{"artifact_id": "unicode", "path": str(self.artifacts / "日本語.txt"), "role": "roundtrip"}], "authority_ids": []}
        self.call("observe", "--expected-generation", "1", "--spec", str(self.write_json("reconcile-observe.json", observe)), expect=0)
        (self.artifacts / "日本語.txt").write_text("changed", encoding="utf-8")
        _, out = self.call("reconcile", "--expected-generation", "2", expect=1)
        self.assertEqual(out["status"], "STALE")
        state = json.loads((self.root / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(state["generation"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Self-contained, allowlisted build/verify for the public DEV_STATE release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.1"
PREFIX = f"DEV_STATE-v{VERSION}"
FILES = (
    ".gitignore", ".gitattributes", "README.md", "LICENSE", "CHANGELOG.md", "INTEGRATION.md",
    "docs/VALIDATION.md", "docs/UNINSTALL.md", "tools/release.py",
    "DEV_STATE/dev-state-core/dev_state.py", "DEV_STATE/dev-state-core/dev-state.ps1",
    "DEV_STATE/dev-state-core/schemas/current-v1.schema.json",
    "DEV_STATE/dev-state-core/schemas/operation-spec-v1.schema.json",
    "DEV_STATE/dev-state-core/schemas/receipt-v1.schema.json",
    "DEV_STATE/dev-state-core/tests/test_dev_state.py",
    "DEV_STATE/codex-adapter-g7/dev_state_codex_hook.py",
    "DEV_STATE/codex-adapter-g7/hooks.template.json",
    "DEV_STATE/codex-adapter-g7/SETUP.md",
    "DEV_STATE/codex-adapter-g7/test_post_compaction_refresh.py",
    "templates/init.json", "templates/update.json", "templates/observe.json", "templates/verify.json",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    data = {name: (ROOT / name).read_bytes() for name in FILES}
    for name, raw in data.items():
        text = raw.decode("utf-8", "strict")
        if re.search(r"(?i)[a-z]:[\\/]Users[\\/](?!<)[^\\/\s]+", text):
            raise ValueError(f"Personal home path in {name}")
        if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)", text):
            raise ValueError(f"Possible credential in {name}")
        if name.endswith(".json"):
            json.loads(text)
        if name.endswith(".py"):
            compile(raw, name, "exec")
    return data


def test_suite(directory, pattern):
    code = (
        "import json,sys,unittest; "
        "suite=unittest.defaultTestLoader.discover(sys.argv[1],pattern=sys.argv[2]); "
        "r=unittest.TextTestRunner(verbosity=1).run(suite); "
        "print(json.dumps({'run':r.testsRun,'passed':r.testsRun-len(r.skipped)-len(r.failures)-len(r.errors),"
        "'skipped':len(r.skipped),'skip_reasons':[x[1] for x in r.skipped],"
        "'failures':len(r.failures),'errors':len(r.errors)})); sys.exit(not r.wasSuccessful())"
    )
    p = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code,
                        str(ROOT / directory), pattern], cwd=ROOT, capture_output=True, timeout=120)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "replace"))
    return json.loads(p.stdout)


def fixture_checks():
    core = ROOT / "DEV_STATE/dev-state-core/dev_state.py"
    adapter = ROOT / "DEV_STATE/codex-adapter-g7/dev_state_codex_hook.py"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix="release-probe-", dir=ROOT / "dist") as tmp:
        work = Path(tmp)
        (work / '.git').mkdir()  # Isolate nearest-Git-root resolution from the build checkout.
        deployed = work / "DEV_STATE/dev-state-core/dev_state.py"
        deployed.parent.mkdir(parents=True)
        deployed.write_bytes(core.read_bytes())
        state = work / "DEV_STATE/codex-sessions/release-probe"
        spec = work / "init.json"
        spec.write_text(json.dumps({"spec_version":"1.0","phase":"fixture",
            "active_item_id":None,"next_action":"Fixture only","artifact_roots":[str(work)],
            "items":[],"unresolved":[],"authority_declarations":[]}), encoding="utf-8")
        init = subprocess.run([sys.executable,"-B","-X","utf8",str(deployed),"init",
            "--root",str(state),"--task-id","release-probe","--environment","CODEX",
            "--context-key","release-probe","--spec",str(spec)], env=env,capture_output=True,timeout=10)
        if init.returncode:
            raise RuntimeError(init.stdout.decode("utf-8", "replace"))
        before = {str(p.relative_to(state)):p.read_bytes() for p in state.rglob("*") if p.is_file()}
        for event in ("startup","resume","compact"):
            p = subprocess.run([sys.executable,"-B","-X","utf8",str(adapter)],env=env,
                input=json.dumps({"source":event,"session_id":"release-probe","cwd":str(work)}).encode(),
                capture_output=True,timeout=10)
            assert p.returncode == 0 and not p.stderr, p.stderr
            context = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
            assert len(context.encode("utf-8")) <= 4096
            projection = json.loads(context.split("\n",1)[0])
            assert projection["status"] == "OK" and projection["reconciliation"] == "HASH_MATCH"
            assert projection["task_id"] == "release-probe"
            assert ("DEV_STATE_REFRESH:" in context) == (event == "compact")
        after = {str(p.relative_to(state)):p.read_bytes() for p in state.rglob("*") if p.is_file()}
        assert before == after, "Adapter changed fixture state"
        if os.name == "nt":
            ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            env["PSModulePath"] = str(ps.parent / "Modules")
            env["DEV_STATE_PYTHON"] = sys.executable
            absent = work / "absent-state"
            argv = [str(ps),"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",
                str(ROOT / "DEV_STATE/dev-state-core/dev-state.ps1"),"status",
                "--root",str(absent),"--task-id","probe","--environment","OTHER",
                "--context-key","probe","--compact"]
            p = subprocess.run(argv,env=env,capture_output=True,timeout=10)
            if not p.stdout:
                raise RuntimeError(f"Launcher exit {p.returncode}: {p.stderr.decode('utf-8','replace')}")
            assert json.loads(p.stdout)["status"] == "ABSENT" and not absent.exists()
            env["DEV_STATE_PYTHON"] = str(work / "missing-python.exe")
            p = subprocess.run(argv,env=env,capture_output=True,timeout=10)
            assert p.returncode == 3 and json.loads(p.stdout)["status"] == "BLOCKED"
            assert not absent.exists()
    return {"real_adapter_events":3,"state_unchanged":True,
            "windows_launcher":"PASS" if os.name == "nt" else "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true",help="Verify extracted manifest and run isolated tests")
    args = parser.parse_args()
    data = sources()
    manifest = {"package":"DEV_STATE","version":VERSION,"core_version":"1.0",
        "scope":"code-guidance-templates-only-no-chat-state",
        "files":[{"path":n,"bytes":len(raw),"sha256":sha(raw)} for n,raw in sorted(data.items())]}
    manifest_raw = (json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode()
    if args.verify:
        assert (ROOT / "manifest.json").read_bytes() == manifest_raw, "Manifest/source mismatch"
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    validation = {"core":test_suite("DEV_STATE/dev-state-core/tests","test_dev_state.py"),
        "adapter":test_suite("DEV_STATE/codex-adapter-g7","test_post_compaction_refresh.py"),
        "fixtures":fixture_checks(),"target_live_delivery":"UNVERIFIED"}
    assert sources() == data, "Source changed during validation"
    if args.verify:
        print(json.dumps({"verification":"PASS","validation":validation},ensure_ascii=False))
        return
    archive_path = dist / f"{PREFIX}.zip"
    data["manifest.json"] = manifest_raw
    with zipfile.ZipFile(archive_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(data.items()):
            info = zipfile.ZipInfo(f"{PREFIX}/{name}",date_time=(2026,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None
        assert sorted(z.namelist()) == sorted(f"{PREFIX}/{n}" for n in data)
        assert all(z.read(f"{PREFIX}/{n}") == raw for n,raw in data.items())
    checksum = sha(archive_path.read_bytes())
    (dist / "SHA256SUMS.txt").write_text(f"{checksum}  {archive_path.name}\n",encoding="utf-8",newline="\n")
    (dist / "validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"build":"PASS","zip":str(archive_path),"bytes":archive_path.stat().st_size,
        "sha256":checksum,"files":len(data),"validation":validation},ensure_ascii=False))


if __name__ == "__main__":
    main()

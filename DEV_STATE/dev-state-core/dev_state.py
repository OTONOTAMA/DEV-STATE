#!/usr/bin/env python3
"""DEV_STATE v1 common core.

Short-lived, standard-library-only state/receipt CLI.  Adapters supply the
state root and ownership identity; this module never discovers chat state.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - exercised on POSIX only
    msvcrt = None
try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None

SCHEMA_VERSION = "1.0"
CORE_VERSION = "1.0"
MAX_STATE = 65536
MAX_SPEC = 65536
MAX_COMPACT = 4096
MAX_OUTPUT = 16 * 1024 * 1024
DEFAULT_TIMEOUT = 600
LOCK_TIMEOUT = 5.0
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ENVIRONMENTS = {"BIONIC", "CODEX", "OTHER"}
PROGRESS = {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "DONE"}
BASIS = {"UNVERIFIED", "AI_DECLARED", "MACHINE_OBSERVED", "MACHINE_VERIFIED"}
RECEIPT_RESULTS = {"PASS", "FAIL", "TIMEOUT", "OUTPUT_LIMIT", "EXEC_ERROR", "OBSERVED"}
PROHIBITED_WORDS = {"go", "approved", "approval", "authorized", "authorization", "permission", "user_consent", "may_execute", "resume_go"}


class CoreError(Exception):
    def __init__(self, status: str, code: str, message: str, exit_code: int = 1, data: Optional[dict] = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.exit_code, self.data = exit_code, data or {}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def compact_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> Tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def strict_pairs(pairs: List[Tuple[str, Any]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out


def reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def read_json(path: Path, limit: int) -> Any:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise CoreError("ABSENT", "FILE_MISSING", f"file is missing: {path}")
    if len(raw) > limit:
        raise CoreError("INVALID", "SIZE_EXCEEDED", f"file exceeds {limit} bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CoreError("INVALID", "BOM_PRESENT", "UTF-8 BOM is not allowed")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(text, object_pairs_hook=strict_pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CoreError("INVALID", "JSON_INVALID", str(exc))


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if temp.read_bytes() != data:
            raise CoreError("FAILED", "TEMP_VERIFY_FAILED", f"temporary write verification failed: {temp}", 4)
        replace_error = None
        for _ in range(20):
            try:
                os.replace(temp, path)
                replace_error = None
                break
            except PermissionError as exc:
                replace_error = exc
                time.sleep(0.05)
        if replace_error is not None:
            raise replace_error
        if path.read_bytes() != data:
            raise CoreError("FAILED", "POST_REPLACE_VERIFY_FAILED", f"post-replace verification failed: {path}", 4)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def write_immutable(path: Path, data: bytes) -> None:
    if path.exists():
        raise CoreError("MISMATCH", "IMMUTABLE_COLLISION", f"immutable receipt already exists: {path}")
    write_bytes_atomic(path, data)


def resolved(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        raise CoreError("INVALID", "PATH_NOT_ABSOLUTE", f"absolute path required: {path}")
    return Path(os.path.realpath(os.path.abspath(str(p))))


def norm_path(path: Path) -> str:
    return os.path.normcase(str(path))


def inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([norm_path(path), norm_path(root)]) == norm_path(root)
    except ValueError:
        return False


def require_inside(path: str | Path, root: Path, code: str = "PATH_OUTSIDE_ROOT") -> Path:
    p = resolved(path)
    if not inside(p, root):
        raise CoreError("INVALID", code, f"path is outside allowed root: {p}")
    return p


def root_fingerprint(root: Path) -> str:
    return sha256_bytes(norm_path(root).encode("utf-8"))


def valid_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CoreError("INVALID", "IDENTIFIER_INVALID", f"invalid {name}")
    return value


def text_limit(value: Any, name: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum:
        raise CoreError("INVALID", "TEXT_LIMIT", f"invalid or oversized {name}")
    return value


def check_prohibited(value: Any, key_context: bool = False) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise CoreError("INVALID", "KEY_INVALID", "JSON object keys must be strings")
            normalized = key.lower().replace("-", "_")
            if normalized in PROHIBITED_WORDS:
                raise CoreError("INVALID", "AUTHORITY_FIELD_PROHIBITED", f"prohibited field: {key}")
            check_prohibited(child, True)
    elif isinstance(value, list):
        for child in value:
            check_prohibited(child, key_context)


def exact_keys(obj: Any, allowed: Iterable[str], name: str) -> dict:
    if not isinstance(obj, dict):
        raise CoreError("INVALID", "OBJECT_REQUIRED", f"{name} must be an object")
    allowed_set = set(allowed)
    unknown = set(obj) - allowed_set
    if unknown:
        raise CoreError("INVALID", "UNKNOWN_FIELD", f"unknown field in {name}: {sorted(unknown)[0]}")
    return obj


@contextlib.contextmanager
def writer_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".writer.lock"
    fh = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            fh.write(b"\0")
            fh.flush()
        deadline = time.monotonic() + LOCK_TIMEOUT
        acquired = False
        while time.monotonic() < deadline:
            try:
                fh.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, IOError):
                time.sleep(0.025)
        if not acquired:
            raise CoreError("BLOCKED", "WRITER_LOCK_BUSY", "writer lock timeout", 3)
        try:
            yield
        finally:
            try:
                fh.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        fh.close()


def state_paths(root: Path) -> dict:
    return {"current": root / "current.json", "previous": root / "previous.json", "status": root / "STATUS.md", "receipts": root / "receipts", "staging": root / ".staging"}


def owner(args: argparse.Namespace, root: Path) -> dict:
    return {"environment": args.environment, "context_key": args.context_key, "root_fingerprint": root_fingerprint(root)}


def validate_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value):
        raise CoreError("INVALID", "TIMESTAMP_INVALID", f"invalid {name}")


def validate_state(state: Any, root: Path, args: argparse.Namespace, check_owner: bool = True) -> None:
    exact_keys(state, {"schema_version", "task_id", "owner_context", "generation", "created_at", "updated_at", "phase", "active_item_id", "next_action", "artifact_roots", "items", "unresolved", "authority_refs", "diagnostics"}, "current")
    check_prohibited(state)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise CoreError("INVALID", "SCHEMA_VERSION", "unsupported state schema")
    valid_id(state.get("task_id"), "task_id")
    if not isinstance(state.get("owner_context"), dict):
        raise CoreError("INVALID", "OWNER_INVALID", "owner_context must be an object")
    exact_keys(state["owner_context"], {"environment", "context_key", "root_fingerprint"}, "owner_context")
    if state["owner_context"].get("environment") not in ENVIRONMENTS:
        raise CoreError("INVALID", "ENVIRONMENT_INVALID", "invalid environment")
    if not isinstance(state["owner_context"].get("context_key"), str) or not (1 <= len(state["owner_context"]["context_key"].encode("utf-8")) <= 256):
        raise CoreError("INVALID", "CONTEXT_KEY_INVALID", "invalid context_key")
    if not isinstance(state["owner_context"].get("root_fingerprint"), str) or not HEX64_RE.fullmatch(state["owner_context"]["root_fingerprint"]):
        raise CoreError("INVALID", "ROOT_FINGERPRINT_INVALID", "invalid root_fingerprint")
    if state["owner_context"]["root_fingerprint"] != root_fingerprint(root):
        raise CoreError("MISMATCH", "ROOT_FINGERPRINT_MISMATCH", "state root binding differs")
    if check_owner and (state["task_id"] != args.task_id or state["owner_context"]["environment"] != args.environment or state["owner_context"]["context_key"] != args.context_key):
        raise CoreError("MISMATCH", "OWNER_MISMATCH", "task or owner context differs")
    if not isinstance(state.get("generation"), int) or state["generation"] < 1:
        raise CoreError("INVALID", "GENERATION_INVALID", "generation must be positive")
    validate_timestamp(state.get("created_at"), "created_at")
    validate_timestamp(state.get("updated_at"), "updated_at")
    text_limit(state.get("phase"), "phase", 128)
    active = state.get("active_item_id")
    if active is not None:
        valid_id(active, "active_item_id")
    text_limit(state.get("next_action"), "next_action")
    roots = state.get("artifact_roots")
    if not isinstance(roots, list) or len(roots) > 16 or len(set(roots)) != len(roots):
        raise CoreError("INVALID", "ARTIFACT_ROOTS_INVALID", "invalid artifact_roots")
    resolved_roots: List[Path] = []
    for path in roots:
        p = resolved(path) if isinstance(path, str) else None
        if p is None or not p.is_dir():
            raise CoreError("INVALID", "ARTIFACT_ROOT_INVALID", "artifact root must be an existing directory")
        resolved_roots.append(p)
    items = state.get("items")
    if not isinstance(items, list) or len(items) > 128:
        raise CoreError("INVALID", "ITEMS_INVALID", "invalid items")
    item_ids = set()
    for item in items:
        exact_keys(item, {"item_id", "summary", "progress", "basis", "artifact_refs", "receipt_refs", "updated_at"}, "item")
        iid = valid_id(item.get("item_id"), "item_id")
        if iid in item_ids:
            raise CoreError("INVALID", "DUPLICATE_ID", "duplicate item_id")
        item_ids.add(iid)
        text_limit(item.get("summary"), "summary")
        if item.get("progress") not in PROGRESS or item.get("basis") not in BASIS:
            raise CoreError("INVALID", "ITEM_VALUE_INVALID", "invalid item progress or basis")
        validate_timestamp(item.get("updated_at"), "item.updated_at")
        if not isinstance(item.get("artifact_refs"), list) or len(item["artifact_refs"]) > 32:
            raise CoreError("INVALID", "ARTIFACT_REFS_INVALID", "invalid artifact_refs")
        if not isinstance(item.get("receipt_refs"), list) or len(item["receipt_refs"]) > 32:
            raise CoreError("INVALID", "RECEIPT_REFS_INVALID", "invalid receipt_refs")
        for ref in item["artifact_refs"]:
            exact_keys(ref, {"artifact_id", "path", "role", "sha256", "bytes", "observed_at"}, "artifact_ref")
            valid_id(ref.get("artifact_id"), "artifact_id")
            if not isinstance(ref.get("path"), str) or not HEX64_RE.fullmatch(ref.get("sha256", "")) or not isinstance(ref.get("bytes"), int) or ref["bytes"] < 0:
                raise CoreError("INVALID", "ARTIFACT_REF_INVALID", "invalid artifact reference")
            validate_timestamp(ref.get("observed_at"), "artifact_ref.observed_at")
            ap = resolved(ref["path"])
            if not any(inside(ap, ar) for ar in resolved_roots):
                raise CoreError("INVALID", "ARTIFACT_OUTSIDE_ROOT", "artifact is outside artifact_roots")
        for ref in item["receipt_refs"]:
            exact_keys(ref, {"receipt_id", "path", "sha256"}, "receipt_ref")
            valid_id(ref.get("receipt_id"), "receipt_id")
            if not isinstance(ref.get("path"), str) or Path(ref["path"]).is_absolute() or "\\" in ref["path"] or ".." in Path(ref["path"]).parts or not HEX64_RE.fullmatch(ref.get("sha256", "")):
                raise CoreError("INVALID", "RECEIPT_REF_INVALID", "invalid receipt reference")
    if active is not None and active not in item_ids:
        raise CoreError("INVALID", "ACTIVE_ITEM_MISSING", "active item does not exist")
    unresolved = state.get("unresolved")
    if not isinstance(unresolved, list) or len(unresolved) > 32:
        raise CoreError("INVALID", "UNRESOLVED_INVALID", "invalid unresolved")
    unresolved_ids = set()
    for entry in unresolved:
        exact_keys(entry, {"unresolved_id", "summary", "affects_item_ids", "basis", "unlock_condition", "updated_at"}, "unresolved")
        uid = valid_id(entry.get("unresolved_id"), "unresolved_id")
        if uid in unresolved_ids:
            raise CoreError("INVALID", "DUPLICATE_ID", "duplicate unresolved_id")
        unresolved_ids.add(uid)
        text_limit(entry.get("summary"), "unresolved.summary")
        text_limit(entry.get("unlock_condition"), "unresolved.unlock_condition")
        if entry.get("basis") not in {"UNVERIFIED", "AI_DECLARED"} or not isinstance(entry.get("affects_item_ids"), list):
            raise CoreError("INVALID", "UNRESOLVED_VALUE_INVALID", "invalid unresolved value")
        for iid in entry["affects_item_ids"]:
            if iid not in item_ids:
                raise CoreError("INVALID", "UNRESOLVED_ITEM_MISSING", "unresolved references unknown item")
        validate_timestamp(entry.get("updated_at"), "unresolved.updated_at")
    authorities = state.get("authority_refs")
    if not isinstance(authorities, list) or len(authorities) > 32:
        raise CoreError("INVALID", "AUTHORITIES_INVALID", "invalid authority_refs")
    authority_ids = set()
    for ref in authorities:
        exact_keys(ref, {"authority_id", "path", "role", "sha256", "bytes", "observed_at"}, "authority_ref")
        aid = valid_id(ref.get("authority_id"), "authority_id")
        if aid in authority_ids:
            raise CoreError("INVALID", "DUPLICATE_ID", "duplicate authority_id")
        authority_ids.add(aid)
        if not isinstance(ref.get("path"), str) or not isinstance(ref.get("role"), str):
            raise CoreError("INVALID", "AUTHORITY_REF_INVALID", "invalid authority reference")
        if ref.get("sha256") is not None and not HEX64_RE.fullmatch(ref["sha256"]):
            raise CoreError("INVALID", "AUTHORITY_HASH_INVALID", "invalid authority hash")
        if ref.get("bytes") is not None and (not isinstance(ref["bytes"], int) or ref["bytes"] < 0):
            raise CoreError("INVALID", "AUTHORITY_BYTES_INVALID", "invalid authority bytes")
        if ref.get("observed_at") is not None:
            validate_timestamp(ref["observed_at"], "authority_ref.observed_at")
    diagnostics = state.get("diagnostics")
    if not isinstance(diagnostics, list) or len(diagnostics) > 32:
        raise CoreError("INVALID", "DIAGNOSTICS_INVALID", "invalid diagnostics")
    for diag in diagnostics:
        exact_keys(diag, {"code", "severity", "summary", "item_id", "recorded_at"}, "diagnostic")
        if diag.get("severity") not in {"INFO", "WARNING", "ERROR"}:
            raise CoreError("INVALID", "DIAGNOSTIC_INVALID", "invalid diagnostic severity")
        text_limit(diag.get("summary"), "diagnostic.summary")
        validate_timestamp(diag.get("recorded_at"), "diagnostic.recorded_at")


def read_current(root: Path, args: argparse.Namespace) -> Tuple[bytes, dict]:
    current = state_paths(root)["current"]
    if not current.exists():
        raise CoreError("ABSENT", "STATE_ABSENT", "current.json is not initialized")
    raw = current.read_bytes()
    if len(raw) > MAX_STATE:
        raise CoreError("INVALID", "SIZE_EXCEEDED", "current.json exceeds hard limit")
    state = read_json(current, MAX_STATE)
    validate_state(state, root, args)
    return raw, state


def receipt_path(root: Path, rel: str) -> Path:
    if Path(rel).is_absolute() or "\\" in rel or ".." in Path(rel).parts or not rel.startswith("receipts/"):
        raise CoreError("INVALID", "RECEIPT_PATH_INVALID", "invalid receipt relative path")
    return require_inside(root / rel, root / "receipts")


def reconcile_state(root: Path, state: dict) -> Tuple[str, List[dict], List[str]]:
    findings: List[dict] = []
    paths: List[str] = []
    receipts_dir = root / "receipts"
    items_by_id = {i["item_id"]: i for i in state["items"]}
    for item in state["items"]:
        for ref in item["receipt_refs"]:
            try:
                rp = receipt_path(root, ref["path"])
                raw = rp.read_bytes()
            except (OSError, CoreError) as exc:
                findings.append({"code": "RECEIPT_INVALID", "severity": "ERROR", "summary": str(exc), "item_id": item["item_id"]})
                paths.append(ref["path"])
                continue
            if sha256_bytes(raw) != ref["sha256"]:
                findings.append({"code": "RECEIPT_STALE", "severity": "ERROR", "summary": f"receipt hash changed: {ref['path']}", "item_id": item["item_id"]})
                paths.append(ref["path"])
                continue
            try:
                receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs, parse_constant=reject_constant)
                validate_receipt(receipt, root)
                if receipt.get("task_id") != state["task_id"] or receipt.get("item_id") != item["item_id"]:
                    raise CoreError("MISMATCH", "RECEIPT_IDENTITY_MISMATCH", "receipt identity mismatch")
            except CoreError as exc:
                findings.append({"code": exc.code, "severity": "ERROR", "summary": exc.message, "item_id": item["item_id"]})
                paths.append(ref["path"])
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                findings.append({"code": "RECEIPT_INVALID", "severity": "ERROR", "summary": str(exc), "item_id": item["item_id"]})
                paths.append(ref["path"])
        for ref in item["artifact_refs"]:
            try:
                ap = resolved(ref["path"])
                if not ap.exists():
                    raise FileNotFoundError(ref["path"])
                actual_hash, actual_bytes = sha256_file(ap)
                if actual_hash != ref["sha256"] or actual_bytes != ref["bytes"]:
                    findings.append({"code": "ARTIFACT_STALE", "severity": "WARNING", "summary": f"artifact changed: {ref['path']}", "item_id": item["item_id"], "expected_sha256": ref["sha256"], "observed_sha256": actual_hash})
                    paths.append(ref["path"])
            except (OSError, FileNotFoundError) as exc:
                findings.append({"code": "ARTIFACT_STALE", "severity": "WARNING", "summary": f"artifact missing: {ref['path']}", "item_id": item["item_id"]})
                paths.append(ref["path"])
    for ref in state["authority_refs"]:
        if ref["sha256"] is None:
            findings.append({"code": "AUTHORITY_UNOBSERVED", "severity": "WARNING", "summary": f"authority has no measured fingerprint: {ref['path']}"})
            paths.append(ref["path"])
            continue
        try:
            ap = resolved(ref["path"])
            actual_hash, actual_bytes = sha256_file(ap)
            if actual_hash != ref["sha256"] or actual_bytes != ref["bytes"]:
                findings.append({"code": "AUTHORITY_STALE", "severity": "WARNING", "summary": f"authority changed: {ref['path']}", "expected_sha256": ref["sha256"], "observed_sha256": actual_hash})
                paths.append(ref["path"])
        except OSError:
            findings.append({"code": "AUTHORITY_STALE", "severity": "WARNING", "summary": f"authority missing: {ref['path']}"})
            paths.append(ref["path"])
    if any(f["code"].endswith("INVALID") or f["code"] in {"RECEIPT_STALE", "RECEIPT_OUTPUT_STALE"} for f in findings):
        result = "INVALID"
    elif any(f["code"].endswith("MISMATCH") for f in findings):
        result = "MISMATCH"
    elif any(f["severity"] == "ERROR" for f in findings):
        result = "INVALID"
    elif findings:
        result = "STALE"
    else:
        result = "HASH_MATCH"
    return result, findings, sorted(set(paths))


def validate_receipt(receipt: dict, root: Path) -> None:
    exact_keys(receipt, {"receipt_schema_version", "receipt_id", "task_id", "item_id", "producer", "verification_surface", "command_or_test_id", "argv", "cwd", "started_at", "finished_at", "exit_code", "result", "artifact_fingerprints", "stdout", "stderr", "acceptance"}, "receipt")
    if receipt.get("receipt_schema_version") != SCHEMA_VERSION or receipt.get("producer", {}).get("kind") != "DEV_STATE_CORE":
        raise CoreError("INVALID", "RECEIPT_SCHEMA_INVALID", "invalid receipt schema or producer")
    valid_id(receipt.get("receipt_id"), "receipt_id")
    valid_id(receipt.get("task_id"), "task_id")
    valid_id(receipt.get("item_id"), "item_id")
    if receipt.get("result") not in RECEIPT_RESULTS:
        raise CoreError("INVALID", "RECEIPT_RESULT_INVALID", "invalid receipt result")
    for key in ("started_at", "finished_at"):
        validate_timestamp(receipt.get(key), "receipt." + key)
    for stream in ("stdout", "stderr"):
        obj = receipt.get(stream)
        exact_keys(obj, {"path", "sha256", "bytes", "truncated"}, "receipt." + stream)
        path = receipt_path(root, obj.get("path"))
        if not HEX64_RE.fullmatch(obj.get("sha256", "")) or not isinstance(obj.get("bytes"), int) or obj["bytes"] < 0 or not isinstance(obj.get("truncated"), bool):
            raise CoreError("INVALID", "RECEIPT_OUTPUT_INVALID", "invalid receipt output")
        if not path.exists():
            raise CoreError("INVALID", "RECEIPT_OUTPUT_MISSING", "receipt output is missing")
        actual_hash, actual_bytes = sha256_file(path)
        if actual_hash != obj["sha256"] or actual_bytes != obj["bytes"]:
            raise CoreError("MISMATCH", "RECEIPT_OUTPUT_STALE", "receipt output fingerprint differs")


def clip(value: str, maximum: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= maximum:
        return value
    return raw[: max(0, maximum - 3)].decode("utf-8", "ignore") + "..."


def result_envelope(operation: str, args: argparse.Namespace, status: str, generation: Optional[int], changed: bool, diagnostics: List[Any], data: dict) -> dict:
    return {"result_schema_version": "1.0", "operation": operation, "status": status, "task_id": args.task_id, "generation": generation, "changed": changed, "diagnostics": diagnostics, "data": data}


def emit(value: dict, exit_code: int = 0) -> int:
    raw = compact_json(value)
    if len(raw) > MAX_COMPACT:
        value["diagnostics"] = []
        data = value.setdefault("data", {})
        data["truncated"] = True
        data["omitted_count"] = data.get("omitted_count", 0) + 1
        for key in ("findings", "items", "unresolved", "authorities", "paths"):
            data.pop(key, None)
        raw = compact_json(value)
    sys.stdout.buffer.write(raw + b"\n")
    sys.stdout.flush()
    return exit_code


def load_spec(args: argparse.Namespace, allowed: set[str]) -> dict:
    spec = read_json(resolved(args.spec), MAX_SPEC)
    try:
        check_prohibited(spec)
        exact_keys(spec, allowed, "operation spec")
    except CoreError as exc:
        if exc.exit_code == 1:
            raise CoreError(exc.status, exc.code, exc.message, 2, exc.data)
        raise
    if spec.get("spec_version") != SCHEMA_VERSION:
        raise CoreError("INVALID", "SPEC_VERSION", "unsupported spec_version", 2)
    return spec


def build_item(raw: dict, timestamp: str) -> dict:
    exact_keys(raw, {"item_id", "summary", "progress", "basis"}, "item spec")
    iid = valid_id(raw.get("item_id"), "item_id")
    text_limit(raw.get("summary"), "summary")
    if raw.get("progress") not in PROGRESS or raw.get("basis") not in {"UNVERIFIED", "AI_DECLARED"}:
        raise CoreError("INVALID", "ITEM_SPEC_INVALID", "invalid item spec", 2)
    return {"item_id": iid, "summary": raw["summary"], "progress": raw["progress"], "basis": raw["basis"], "artifact_refs": [], "receipt_refs": [], "updated_at": timestamp}


def build_unresolved(raw: dict, item_ids: set[str], timestamp: str) -> dict:
    exact_keys(raw, {"unresolved_id", "summary", "affects_item_ids", "basis", "unlock_condition"}, "unresolved spec")
    uid = valid_id(raw.get("unresolved_id"), "unresolved_id")
    text_limit(raw.get("summary"), "unresolved.summary")
    text_limit(raw.get("unlock_condition"), "unresolved.unlock_condition")
    if raw.get("basis") not in {"UNVERIFIED", "AI_DECLARED"} or not isinstance(raw.get("affects_item_ids"), list):
        raise CoreError("INVALID", "UNRESOLVED_SPEC_INVALID", "invalid unresolved spec", 2)
    if any(i not in item_ids for i in raw["affects_item_ids"]):
        raise CoreError("INVALID", "UNRESOLVED_ITEM_MISSING", "unresolved references unknown item", 2)
    return {"unresolved_id": uid, "summary": raw["summary"], "affects_item_ids": sorted(set(raw["affects_item_ids"])), "basis": raw["basis"], "unlock_condition": raw["unlock_condition"], "updated_at": timestamp}


def authority_decl(raw: dict) -> dict:
    exact_keys(raw, {"authority_id", "path", "role"}, "authority declaration")
    valid_id(raw.get("authority_id"), "authority_id")
    if not isinstance(raw.get("path"), str) or not isinstance(raw.get("role"), str):
        raise CoreError("INVALID", "AUTHORITY_SPEC_INVALID", "invalid authority declaration", 2)
    return {"authority_id": raw["authority_id"], "path": str(resolved(raw["path"])), "role": raw["role"], "sha256": None, "bytes": None, "observed_at": None}


def render_status(state: dict, root: Path, reconciliation: str = "HASH_MATCH") -> bytes:
    active = next((i for i in state["items"] if i["item_id"] == state["active_item_id"]), None)
    lines = ["# DEV_STATE STATUS", "NON_AUTHORITATIVE_DERIVED_VIEW", "", f"Task: {state['task_id']}", f"Generation: {state['generation']}", f"Integrity: {reconciliation}", f"Phase: {state['phase']}", f"Active item: {active['item_id'] if active else 'none'}", f"Progress / basis: {(active['progress'] + ' / ' + active['basis']) if active else 'none'}", f"Next action: {state['next_action']}", f"Blocked: {sum(1 for i in state['items'] if i['progress'] == 'BLOCKED')}", f"Unresolved: {len(state['unresolved'])}", f"Canonical state: {root / 'current.json'}", ""]
    return "\n".join(lines).encode("utf-8")


def commit_state(root: Path, old_bytes: Optional[bytes], new_state: dict, receipt_files: Optional[List[Tuple[Path, bytes]]] = None, create_previous: bool = True) -> None:
    paths = state_paths(root)
    root.mkdir(parents=True, exist_ok=True)
    paths["receipts"].mkdir(parents=True, exist_ok=True)
    paths["staging"].mkdir(parents=True, exist_ok=True)
    for path, data in receipt_files or []:
        write_immutable(path, data)
    if old_bytes is not None and create_previous:
        write_bytes_atomic(paths["previous"], old_bytes)
    current_bytes = json_bytes(new_state)
    if len(current_bytes) > MAX_STATE:
        raise CoreError("INVALID", "SIZE_EXCEEDED", "candidate current.json exceeds hard limit")
    write_bytes_atomic(paths["current"], current_bytes)
    rec, _, _ = reconcile_state(root, new_state)
    write_bytes_atomic(paths["status"], render_status(new_state, root, rec))


def base_data(state: dict, rec: str, findings: List[dict], paths: List[str]) -> dict:
    active = next((i for i in state["items"] if i["item_id"] == state["active_item_id"]), None)
    return {"reconciliation": rec, "phase": state["phase"], "active_item_id": state["active_item_id"], "progress": active["progress"] if active else None, "persisted_basis": active["basis"] if active else None, "effective_basis": "UNVERIFIED" if active and any(f.get("item_id") == active["item_id"] for f in findings) else (active["basis"] if active else None), "next_action": clip(state["next_action"], 1024), "counts": {p: sum(1 for i in state["items"] if i["progress"] == p) for p in sorted(PROGRESS)}, "unresolved_count": len(state["unresolved"]), "authority_paths": [r["path"] for r in state["authority_refs"]], "paths_requiring_recheck": paths, "findings": findings, "truncated": False, "omitted_count": 0}


def op_init(args: argparse.Namespace) -> Tuple[dict, int]:
    root = resolved(args.root)
    paths = state_paths(root)
    if paths["current"].exists():
        raise CoreError("MISMATCH", "STATE_ALREADY_EXISTS", "current.json already exists", 1)
    spec = load_spec(args, {"spec_version", "phase", "active_item_id", "next_action", "artifact_roots", "items", "unresolved", "authority_declarations"})
    timestamp = now_utc()
    items = [build_item(x, timestamp) for x in spec.get("items", [])]
    if len({x["item_id"] for x in items}) != len(items) or len(items) > 128:
        raise CoreError("INVALID", "ITEMS_INVALID", "duplicate or excessive items", 2)
    item_ids = {x["item_id"] for x in items}
    unresolved = [build_unresolved(x, item_ids, timestamp) for x in spec.get("unresolved", [])]
    if len({x["unresolved_id"] for x in unresolved}) != len(unresolved) or len(unresolved) > 32:
        raise CoreError("INVALID", "UNRESOLVED_INVALID", "duplicate or excessive unresolved entries", 2)
    roots: List[str] = []
    for path in spec.get("artifact_roots", []):
        p = resolved(path)
        if not p.is_dir():
            raise CoreError("INVALID", "ARTIFACT_ROOT_INVALID", f"artifact root does not exist: {p}", 2)
        if str(p) not in roots:
            roots.append(str(p))
    if len(roots) > 16:
        raise CoreError("INVALID", "ARTIFACT_ROOTS_INVALID", "too many artifact roots", 2)
    authorities = [authority_decl(x) for x in spec.get("authority_declarations", [])]
    if len({x["authority_id"] for x in authorities}) != len(authorities) or len(authorities) > 32:
        raise CoreError("INVALID", "AUTHORITIES_INVALID", "duplicate or excessive authorities", 2)
    active = spec.get("active_item_id")
    if active is not None and active not in item_ids:
        raise CoreError("INVALID", "ACTIVE_ITEM_MISSING", "active item does not exist", 2)
    state = {"schema_version": SCHEMA_VERSION, "task_id": args.task_id, "owner_context": owner(args, root), "generation": 1, "created_at": timestamp, "updated_at": timestamp, "phase": text_limit(spec.get("phase", ""), "phase", 128), "active_item_id": active, "next_action": text_limit(spec.get("next_action", ""), "next_action"), "artifact_roots": sorted(roots, key=norm_path), "items": sorted(items, key=lambda x: x["item_id"]), "unresolved": sorted(unresolved, key=lambda x: x["unresolved_id"]), "authority_refs": sorted(authorities, key=lambda x: x["authority_id"]), "diagnostics": []}
    validate_state(state, root, args)
    with writer_lock(root):
        if paths["current"].exists():
            raise CoreError("MISMATCH", "STATE_ALREADY_EXISTS", "current.json already exists")
        commit_state(root, None, state, create_previous=False)
    return result_envelope("init", args, "OK", 1, True, [], {"root": str(root), "current": str(paths["current"])}), 0


def op_status(args: argparse.Namespace) -> Tuple[dict, int]:
    root = resolved(args.root)
    raw, state = read_current(root, args)
    rec, findings, paths = reconcile_state(root, state)
    status = "OK" if rec == "HASH_MATCH" else rec
    data = base_data(state, rec, findings, paths)
    if args.full:
        data["state"] = state
    env = result_envelope("status", args, status, state["generation"], False, findings, data)
    return env, 0 if status == "OK" else 1


def load_for_mutation(args: argparse.Namespace) -> Tuple[Path, bytes, dict]:
    root = resolved(args.root)
    raw, state = read_current(root, args)
    return root, raw, state


def next_state(state: dict) -> dict:
    state = json.loads(json.dumps(state, ensure_ascii=False))
    state["generation"] += 1
    state["updated_at"] = now_utc()
    return state


def apply_update(state: dict, spec: dict, timestamp: str) -> dict:
    exact_keys(spec, {"spec_version", "set", "upsert_items", "upsert_unresolved", "resolve_unresolved_ids", "declare_authority_refs", "remove_authority_ids"}, "update spec")
    if not isinstance(spec.get("set", {}), dict):
        raise CoreError("INVALID", "SET_INVALID", "set must be an object", 2)
    exact_keys(spec.get("set", {}), {"phase", "active_item_id", "next_action"}, "set")
    if "phase" in spec["set"]:
        state["phase"] = text_limit(spec["set"]["phase"], "phase", 128)
    if "next_action" in spec["set"]:
        state["next_action"] = text_limit(spec["set"]["next_action"], "next_action")
    if "active_item_id" in spec["set"]:
        if spec["set"]["active_item_id"] is not None:
            valid_id(spec["set"]["active_item_id"], "active_item_id")
        state["active_item_id"] = spec["set"]["active_item_id"]
    items = {i["item_id"]: i for i in state["items"]}
    changed_item_ids: set[str] = set()
    for raw in spec.get("upsert_items", []) or []:
        exact_keys(raw, {"item_id", "summary", "progress", "basis"}, "item update")
        iid = valid_id(raw.get("item_id"), "item_id")
        text_limit(raw.get("summary"), "summary")
        if raw.get("progress") not in PROGRESS or raw.get("basis") not in {"UNVERIFIED", "AI_DECLARED"}:
            raise CoreError("INVALID", "ITEM_SPEC_INVALID", "invalid item update", 2)
        old = items.get(iid, {"item_id": iid, "artifact_refs": [], "receipt_refs": []})
        old.update({"summary": raw["summary"], "progress": raw["progress"], "basis": raw["basis"], "updated_at": timestamp})
        items[iid] = old
        changed_item_ids.add(iid)
    state["items"] = sorted(items.values(), key=lambda x: x["item_id"])
    item_ids = set(items)
    unresolved = {u["unresolved_id"]: u for u in state["unresolved"]}
    for raw in spec.get("upsert_unresolved", []) or []:
        entry = build_unresolved(raw, item_ids, timestamp)
        unresolved[entry["unresolved_id"]] = entry
    for uid in spec.get("resolve_unresolved_ids", []) or []:
        valid_id(uid, "unresolved_id")
        unresolved.pop(uid, None)
    state["unresolved"] = sorted(unresolved.values(), key=lambda x: x["unresolved_id"])
    authorities = {a["authority_id"]: a for a in state["authority_refs"]}
    for raw in spec.get("declare_authority_refs", []) or []:
        entry = authority_decl(raw)
        authorities[entry["authority_id"]] = entry
    for aid in spec.get("remove_authority_ids", []) or []:
        valid_id(aid, "authority_id")
        authorities.pop(aid, None)
    state["authority_refs"] = sorted(authorities.values(), key=lambda x: x["authority_id"])
    if state["active_item_id"] is not None and state["active_item_id"] not in item_ids:
        raise CoreError("INVALID", "ACTIVE_ITEM_MISSING", "active item does not exist", 2)
    for item in state["items"]:
        if item["item_id"] in changed_item_ids:
            item["basis"] = "AI_DECLARED"
    return state


def op_update(args: argparse.Namespace) -> Tuple[dict, int]:
    root, old_raw, current = load_for_mutation(args)
    spec = load_spec(args, {"spec_version", "set", "upsert_items", "upsert_unresolved", "resolve_unresolved_ids", "declare_authority_refs", "remove_authority_ids"})
    if not isinstance(args.expected_generation, int) or args.expected_generation < 1:
        raise CoreError("INVALID", "EXPECTED_GENERATION_INVALID", "expected generation required", 2)
    with writer_lock(root):
        old_raw, current = read_current(root, args)
        if current["generation"] != args.expected_generation:
            raise CoreError("STALE", "GENERATION_MISMATCH", "expected generation differs", 3)
        candidate = apply_update(next_state(current), spec, now_utc())
        validate_state(candidate, root, args)
        commit_state(root, old_raw, candidate)
    return result_envelope("update", args, "OK", candidate["generation"], True, [], {"generation": candidate["generation"]}), 0


def artifact_roots_from(state: dict) -> List[Path]:
    return [resolved(p) for p in state["artifact_roots"]]


def find_artifact_root(path: Path, roots: List[Path]) -> bool:
    return any(inside(path, r) for r in roots)


def make_receipt_id(prefix: str = "r") -> str:
    return f"{prefix}-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"


def empty_stream(root: Path, receipt_id: str, suffix: str) -> Tuple[Path, dict, bytes]:
    rel = f"receipts/{receipt_id}.{suffix}.bin"
    data = b""
    return root / rel, {"path": rel, "sha256": sha256_bytes(data), "bytes": 0, "truncated": False}, data


def build_receipt(root: Path, receipt_id: str, task_id: str, item_id: str, result: str, command_id: str, argv: List[str], cwd: str, started: str, finished: str, exit_code: Optional[int], artifacts: List[dict], stdout_ref: dict, stderr_ref: dict, success_codes: List[int], required_ids: List[str]) -> dict:
    return {"receipt_schema_version": SCHEMA_VERSION, "receipt_id": receipt_id, "task_id": task_id, "item_id": item_id, "producer": {"kind": "DEV_STATE_CORE", "core_version": CORE_VERSION}, "verification_surface": "COMMAND_EXIT_AND_ARTIFACTS", "command_or_test_id": command_id, "argv": argv, "cwd": cwd, "started_at": started, "finished_at": finished, "exit_code": exit_code, "result": result, "artifact_fingerprints": artifacts, "stdout": stdout_ref, "stderr": stderr_ref, "acceptance": {"success_exit_codes": success_codes, "required_artifact_ids": required_ids}}


def op_observe(args: argparse.Namespace) -> Tuple[dict, int]:
    root, old_raw, current = load_for_mutation(args)
    spec = load_spec(args, {"spec_version", "item_id", "artifacts", "authority_ids"})
    valid_id(spec.get("item_id"), "item_id")
    if not spec.get("artifacts") and not spec.get("authority_ids"):
        raise CoreError("INVALID", "OBSERVE_EMPTY", "artifacts or authority_ids required", 2)
    item = next((i for i in current["items"] if i["item_id"] == spec["item_id"]), None)
    if item is None:
        raise CoreError("INVALID", "ITEM_MISSING", "observe item does not exist", 2)
    roots = artifact_roots_from(current)
    observed = []
    for raw in spec.get("artifacts", []) or []:
        exact_keys(raw, {"artifact_id", "path", "role"}, "observe artifact")
        aid = valid_id(raw.get("artifact_id"), "artifact_id")
        ap = resolved(raw.get("path"))
        if not ap.is_file() or not find_artifact_root(ap, roots):
            raise CoreError("INVALID", "ARTIFACT_OUTSIDE_ROOT", "observe artifact is missing or outside allowlist", 2)
        h, n = sha256_file(ap)
        observed.append({"artifact_id": aid, "path": str(ap), "role": raw["role"], "sha256": h, "bytes": n, "observed_at": now_utc()})
    authority_updates = {}
    authority_ids_existing = {a["authority_id"] for a in current["authority_refs"]}
    for aid in spec.get("authority_ids", []) or []:
        valid_id(aid, "authority_id")
        if aid not in authority_ids_existing:
            raise CoreError("INVALID", "AUTHORITY_MISSING", f"observe authority does not exist: {aid}", 2)
        authority_updates[aid] = True
    receipt_id = make_receipt_id("r")
    started = now_utc()
    finished = now_utc()
    stdout_path, stdout_ref, stdout_data = empty_stream(root, receipt_id, "stdout")
    stderr_path, stderr_ref, stderr_data = empty_stream(root, receipt_id, "stderr")
    receipt = build_receipt(root, receipt_id, current["task_id"], item["item_id"], "OBSERVED", "observe", [], str(root), started, finished, 0, observed, stdout_ref, stderr_ref, [0], [a["artifact_id"] for a in observed])
    receipt_data = json_bytes(receipt)
    with writer_lock(root):
        old_raw, current = read_current(root, args)
        if current["generation"] != args.expected_generation:
            raise CoreError("STALE", "GENERATION_MISMATCH", "expected generation differs", 3)
        item = next(i for i in current["items"] if i["item_id"] == spec["item_id"])
        by_id = {a["artifact_id"]: a for a in item["artifact_refs"]}
        by_id.update({a["artifact_id"]: a for a in observed})
        item["artifact_refs"] = sorted(by_id.values(), key=lambda x: x["artifact_id"])
        item["receipt_refs"] = sorted(item["receipt_refs"] + [{"receipt_id": receipt_id, "path": f"receipts/{receipt_id}.json", "sha256": sha256_bytes(receipt_data)}], key=lambda x: x["receipt_id"])
        if item["basis"] != "MACHINE_VERIFIED":
            item["basis"] = "MACHINE_OBSERVED"
        for authority in current["authority_refs"]:
            if authority["authority_id"] in authority_updates:
                h, n = sha256_file(resolved(authority["path"]))
                authority.update({"sha256": h, "bytes": n, "observed_at": now_utc()})
        candidate = next_state(current)
        validate_state(candidate, root, args)
        commit_state(root, old_raw, candidate, [(stdout_path, stdout_data), (stderr_path, stderr_data), (root / f"receipts/{receipt_id}.json", receipt_data)])
    return result_envelope("observe", args, "OK", candidate["generation"], True, [], {"generation": candidate["generation"], "receipt_id": receipt_id}), 0


def run_verifier(spec: dict, root: Path, current: dict) -> Tuple[str, Optional[int], bytes, bytes, List[dict], str, str]:
    exact_keys(spec, {"spec_version", "item_id", "verification_surface", "command_or_test_id", "argv", "cwd", "timeout_seconds", "success_exit_codes", "required_artifacts"}, "verify spec")
    valid_id(spec.get("item_id"), "item_id")
    if not isinstance(spec.get("argv"), list) or not spec["argv"] or any(not isinstance(x, str) or not x for x in spec["argv"]):
        raise CoreError("INVALID", "ARGV_INVALID", "argv must be a non-empty string array", 2)
    if any("\0" in x for x in spec["argv"]):
        raise CoreError("INVALID", "ARGV_INVALID", "argv contains NUL", 2)
    timeout = spec.get("timeout_seconds", DEFAULT_TIMEOUT)
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 3600:
        raise CoreError("INVALID", "TIMEOUT_INVALID", "timeout out of range", 2)
    if not isinstance(spec.get("success_exit_codes"), list) or any(not isinstance(x, int) for x in spec["success_exit_codes"]):
        raise CoreError("INVALID", "SUCCESS_CODES_INVALID", "invalid success_exit_codes", 2)
    cwd = resolved(spec.get("cwd"))
    if not cwd.is_dir() or not find_artifact_root(cwd, artifact_roots_from(current)):
        raise CoreError("INVALID", "CWD_OUTSIDE_ROOT", "cwd outside artifact roots", 2)
    required = []
    for raw in spec.get("required_artifacts", []) or []:
        exact_keys(raw, {"artifact_id", "path", "role"}, "required artifact")
        aid = valid_id(raw.get("artifact_id"), "artifact_id")
        path = resolved(raw.get("path"))
        if not find_artifact_root(path, artifact_roots_from(current)):
            raise CoreError("INVALID", "ARTIFACT_OUTSIDE_ROOT", "required artifact outside allowlist", 2)
        required.append((aid, path, raw["role"]))
    started = now_utc()
    try:
        proc = subprocess.Popen(spec["argv"], cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        try:
            stdout, stderr = proc.communicate(timeout=float(timeout))
            code = proc.returncode
            if len(stdout) > MAX_OUTPUT or len(stderr) > MAX_OUTPUT:
                return "OUTPUT_LIMIT", code, stdout[:MAX_OUTPUT], stderr[:MAX_OUTPUT], [], started, now_utc()
            result = "PASS" if code in spec["success_exit_codes"] and all(p.is_file() for _, p, _ in required) else "FAIL"
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            return "TIMEOUT", proc.returncode, stdout[:MAX_OUTPUT], stderr[:MAX_OUTPUT], [], started, now_utc()
    except OSError as exc:
        return "EXEC_ERROR", None, b"", str(exc).encode("utf-8"), [], started, now_utc()
    artifacts = []
    for aid, path, role in required:
        if path.is_file():
            h, n = sha256_file(path)
            artifacts.append({"artifact_id": aid, "path": str(path), "role": role, "sha256": h, "bytes": n, "observed_at": now_utc()})
    return result, code, stdout, stderr, artifacts, started, now_utc()


def op_verify(args: argparse.Namespace) -> Tuple[dict, int]:
    root, old_raw, current = load_for_mutation(args)
    spec = load_spec(args, {"spec_version", "item_id", "verification_surface", "command_or_test_id", "argv", "cwd", "timeout_seconds", "success_exit_codes", "required_artifacts"})
    if args.expected_generation < 1:
        raise CoreError("INVALID", "EXPECTED_GENERATION_INVALID", "expected generation required", 2)
    item = next((i for i in current["items"] if i["item_id"] == spec.get("item_id")), None)
    if item is None:
        raise CoreError("INVALID", "ITEM_MISSING", "verify item does not exist", 2)
    result, exit_code, stdout, stderr, artifacts, started, finished = run_verifier(spec, root, current)
    receipt_id = make_receipt_id("r")
    stdout_path = root / f"receipts/{receipt_id}.stdout.bin"
    stderr_path = root / f"receipts/{receipt_id}.stderr.bin"
    stdout_ref = {"path": f"receipts/{receipt_id}.stdout.bin", "sha256": sha256_bytes(stdout), "bytes": len(stdout), "truncated": len(stdout) >= MAX_OUTPUT}
    stderr_ref = {"path": f"receipts/{receipt_id}.stderr.bin", "sha256": sha256_bytes(stderr), "bytes": len(stderr), "truncated": len(stderr) >= MAX_OUTPUT}
    receipt = build_receipt(root, receipt_id, current["task_id"], item["item_id"], result, spec["command_or_test_id"], spec["argv"], str(resolved(spec["cwd"])), started, finished, exit_code, artifacts, stdout_ref, stderr_ref, spec["success_exit_codes"], [a["artifact_id"] for a in artifacts])
    receipt_data = json_bytes(receipt)
    with writer_lock(root):
        old_raw, current = read_current(root, args)
        if current["generation"] != args.expected_generation:
            write_immutable(root / f"receipts/{receipt_id}.json", receipt_data)
            write_immutable(stdout_path, stdout)
            write_immutable(stderr_path, stderr)
            raise CoreError("STALE", "GENERATION_CHANGED_DURING_VERIFY", "generation changed while verifier ran", 3, {"orphan_receipt": f"receipts/{receipt_id}.json"})
        item = next(i for i in current["items"] if i["item_id"] == spec["item_id"])
        by_id = {a["artifact_id"]: a for a in item["artifact_refs"]}
        by_id.update({a["artifact_id"]: a for a in artifacts})
        item["artifact_refs"] = sorted(by_id.values(), key=lambda x: x["artifact_id"])
        item["receipt_refs"] = sorted(item["receipt_refs"] + [{"receipt_id": receipt_id, "path": f"receipts/{receipt_id}.json", "sha256": sha256_bytes(receipt_data)}], key=lambda x: x["receipt_id"])
        if result == "PASS":
            item["basis"] = "MACHINE_VERIFIED"
        candidate = next_state(current)
        validate_state(candidate, root, args)
        commit_state(root, old_raw, candidate, [(stdout_path, stdout), (stderr_path, stderr), (root / f"receipts/{receipt_id}.json", receipt_data)])
    status = "OK" if result == "PASS" else "FAILED"
    return result_envelope("verify", args, status, candidate["generation"], True, [], {"generation": candidate["generation"], "receipt_id": receipt_id, "result": result, "exit_code": exit_code}), 0 if result == "PASS" else 1


def op_validate(args: argparse.Namespace) -> Tuple[dict, int]:
    root = resolved(args.root)
    raw, state = read_current(root, args)
    rec, findings, paths = reconcile_state(root, state)
    if args.full:
        paths_by_reference = {
            ref["path"]
            for item in state["items"]
            for ref in item["receipt_refs"]
        }
        receipts_dir = state_paths(root)["receipts"]
        if receipts_dir.exists():
            for receipt in receipts_dir.glob("*.json"):
                relative = receipt.relative_to(root).as_posix()
                if relative not in paths_by_reference:
                    findings.append({
                        "code": "ORPHAN_RECEIPT",
                        "severity": "WARNING",
                        "summary": f"unreferenced receipt: {relative}",
                    })
                    paths.append(relative)
        staging_dir = state_paths(root)["staging"]
        if staging_dir.exists() and any(staging_dir.iterdir()):
            findings.append({
                "code": "ORPHAN_STAGING",
                "severity": "WARNING",
                "summary": "staging directory contains unadopted entries",
            })
            paths.append(str(staging_dir))
        if findings and rec == "HASH_MATCH":
            rec = "STALE"
        findings = findings + [{"code": "FULL_VALIDATION", "severity": "INFO", "summary": "full reference validation completed"}]
    status = "OK" if rec == "HASH_MATCH" else rec
    return result_envelope("validate", args, status, state["generation"], False, findings, {"reconciliation": rec, "paths_requiring_recheck": paths, "full": bool(args.full)}), 0 if status == "OK" else 1


def op_reconcile(args: argparse.Namespace) -> Tuple[dict, int]:
    root, old_raw, current = load_for_mutation(args)
    rec, findings, paths = reconcile_state(root, current)
    if not args.commit:
        return result_envelope("reconcile", args, "OK" if rec == "HASH_MATCH" else rec, current["generation"], False, findings, {"reconciliation": rec, "paths_requiring_recheck": paths, "commit_required": bool(findings)}), 0 if rec == "HASH_MATCH" else 1
    if args.expected_generation != current["generation"]:
        raise CoreError("STALE", "GENERATION_MISMATCH", "expected generation differs", 3)
    candidate = next_state(current)
    item_ids = {f.get("item_id") for f in findings if f.get("item_id")}
    for item in candidate["items"]:
        if item["item_id"] in item_ids:
            item["basis"] = "UNVERIFIED"
    candidate["diagnostics"] = (candidate["diagnostics"] + [{"code": f["code"], "severity": f["severity"], "summary": clip(f["summary"], 1024), "item_id": f.get("item_id"), "recorded_at": now_utc()} for f in findings])[-32:]
    validate_state(candidate, root, args)
    with writer_lock(root):
        _, check = read_current(root, args)
        if check["generation"] != args.expected_generation:
            raise CoreError("STALE", "GENERATION_MISMATCH", "expected generation differs", 3)
        commit_state(root, old_raw, candidate)
    return result_envelope("reconcile", args, "OK", candidate["generation"], True, findings, {"reconciliation": rec, "generation": candidate["generation"]}), 0


def op_recover(args: argparse.Namespace) -> Tuple[dict, int]:
    root = resolved(args.root)
    paths = state_paths(root)
    if not paths["previous"].exists():
        raise CoreError("ABSENT", "PREVIOUS_ABSENT", "previous.json is missing")
    prev_raw = paths["previous"].read_bytes()
    previous = read_json(paths["previous"], MAX_STATE)
    validate_state(previous, root, args)
    current_raw = paths["current"].read_bytes() if paths["current"].exists() else b""
    if args.current_invalid_sha256 and sha256_bytes(current_raw) != args.current_invalid_sha256:
        raise CoreError("STALE", "CURRENT_HASH_MISMATCH", "invalid current hash differs", 3)
    if args.expected_generation is not None and paths["current"].exists():
        try:
            current = read_json(paths["current"], MAX_STATE)
            if current.get("generation") != args.expected_generation:
                raise CoreError("STALE", "GENERATION_MISMATCH", "expected generation differs", 3)
        except CoreError:
            if args.current_invalid_sha256 is None:
                raise
    candidate = json.loads(json.dumps(previous, ensure_ascii=False))
    candidate["generation"] = max(previous["generation"], (args.expected_generation or previous["generation"])) + 1
    candidate["updated_at"] = now_utc()
    validate_state(candidate, root, args)
    stage = paths["staging"] / ("recovery-" + uuid.uuid4().hex)
    stage.mkdir(parents=True, exist_ok=False)
    if current_raw:
        (stage / "invalid-current.json").write_bytes(current_raw)
    with writer_lock(root):
        # Never promote an invalid current blob into previous.json during recovery.
        # The last validated previous generation is the only safe rollback source.
        commit_state(root, prev_raw, candidate)
    return result_envelope("recover", args, "OK", candidate["generation"], True, [], {"generation": candidate["generation"], "staging": str(stage)}), 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev_state.py")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", required=True)
    common.add_argument("--task-id", required=True)
    common.add_argument("--environment", required=True, choices=sorted(ENVIRONMENTS))
    common.add_argument("--context-key", required=True)
    def add(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], **kwargs)
    p = add("init"); p.add_argument("--spec", required=True)
    p = add("status"); g = p.add_mutually_exclusive_group(required=True); g.add_argument("--compact", action="store_true"); g.add_argument("--full", action="store_true")
    p = add("update"); p.add_argument("--expected-generation", type=int, required=True); p.add_argument("--spec", required=True)
    p = add("observe"); p.add_argument("--expected-generation", type=int, required=True); p.add_argument("--spec", required=True)
    p = add("verify"); p.add_argument("--expected-generation", type=int, required=True); p.add_argument("--spec", required=True)
    p = add("validate"); p.add_argument("--full", action="store_true")
    p = add("reconcile"); p.add_argument("--commit", action="store_true"); p.add_argument("--expected-generation", type=int, default=-1)
    p = add("recover"); g = p.add_mutually_exclusive_group(required=True); g.add_argument("--expected-generation", type=int); g.add_argument("--current-invalid-sha256")
    return parser


OPS = {"init": op_init, "status": op_status, "update": op_update, "observe": op_observe, "verify": op_verify, "validate": op_validate, "reconcile": op_reconcile, "recover": op_recover}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = make_parser()
    try:
        args = parser.parse_args(argv)
        if len(args.context_key.encode("utf-8")) < 1 or len(args.context_key.encode("utf-8")) > 256:
            raise CoreError("INVALID", "CONTEXT_KEY_INVALID", "context-key must be 1-256 UTF-8 bytes", 2)
        root = resolved(args.root)
        if args.command in {"update", "observe", "verify", "reconcile"} and getattr(args, "expected_generation", -1) < 1:
            raise CoreError("INVALID", "EXPECTED_GENERATION_INVALID", "expected-generation is required", 2)
        env, exit_code = OPS[args.command](args)
        return emit(env, exit_code)
    except CoreError as exc:
        data = dict(exc.data)
        task_id = getattr(locals().get("args", None), "task_id", "unknown")
        env = {"result_schema_version": "1.0", "operation": getattr(locals().get("args", None), "command", "unknown"), "status": exc.status, "task_id": task_id, "generation": None, "changed": False, "diagnostics": [{"code": exc.code, "severity": "ERROR", "summary": exc.message}], "data": data}
        return emit(env, exc.exit_code)
    except Exception as exc:  # fail closed with one structured result
        env = {"result_schema_version": "1.0", "operation": getattr(locals().get("args", None), "command", "unknown"), "status": "FAILED", "task_id": getattr(locals().get("args", None), "task_id", "unknown"), "generation": None, "changed": False, "diagnostics": [{"code": "INTERNAL_ERROR", "severity": "ERROR", "summary": str(exc)}], "data": {}}
        return emit(env, 4)


if __name__ == "__main__":
    raise SystemExit(main())

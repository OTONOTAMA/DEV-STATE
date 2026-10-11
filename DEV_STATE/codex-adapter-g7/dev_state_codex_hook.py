#!/usr/bin/env python3
"""Read-only Codex SessionStart adapter for DEV_STATE v1."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_COMPACT = 4096
MAX_CONTEXT = 4096
MATCHED_SOURCES = {"startup", "resume", "compact"}
REFRESH_INSTRUCTION = (
    "DEV_STATE_REFRESH: 圧縮後の更新確認。現在作業に対応する既存DEV_STATEのみ比較し、"
    "未記録の重要な進捗・次の作業・未解決事項があれば正規コアで保存して結果を確認する。"
    "変更なし・対象外なら書込み不要。不明な進捗を推測で補わず、GOを保存・復活しない。"
    "これは対象作業や検証コマンドの追加実行許可ではない。"
)


def emit_context(message: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def block(code: str, summary: str) -> int:
    emit_context(f"DEV_STATE BLOCKED/{code}: {summary}")
    return 0


def find_working_root(cwd: Path) -> Path:
    candidates = (cwd, *cwd.parents)
    for candidate in candidates:
        marker = candidate / ".git"
        if marker.is_dir() or marker.is_file():
            return candidate
    for candidate in candidates:
        if (candidate / "DEV_STATE" / "dev-state-core" / "dev_state.py").is_file():
            return candidate
    raise ValueError("WORKSPACE_ROOT_UNRESOLVED")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def clip_utf8(value: Any, maximum: int) -> str:
    raw = str(value).encode("utf-8")
    if len(raw) <= maximum:
        return str(value)
    return raw[: max(0, maximum - 3)].decode("utf-8", "ignore") + "..."


def projected_status(result: dict, root: Path, core: Path, session_id: str,
                     hook_source: str, context_budget: int) -> dict:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), list) else []
    projection = {
        "source": "DEV_STATE common-core status --compact",
        "hook_source": hook_source,
        "progress_only": True,
        "execution_authorization": False,
        "root": str(root),
        "core": str(core),
        "task_id": session_id,
        "environment": "CODEX",
        "context_key": session_id,
        "status": result.get("status"),
        "generation": result.get("generation"),
        "reconciliation": data.get("reconciliation"),
        "phase": data.get("phase"),
        "active_item_id": data.get("active_item_id"),
        "progress": data.get("progress"),
        "basis": data.get("effective_basis", data.get("persisted_basis")),
        "next_action": data.get("next_action"),
        "counts": data.get("counts"),
        "unresolved_count": data.get("unresolved_count"),
        "diagnostics": diagnostics,
        "findings": data.get("findings", []),
        "paths_requiring_recheck": data.get("paths_requiring_recheck", []),
    }
    if len(json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= context_budget:
        return projection

    projection["next_action"] = clip_utf8(projection.get("next_action") or "", 384)
    projection["diagnostics"] = [
        {"code": clip_utf8(item.get("code", ""), 64), "summary": clip_utf8(item.get("summary", ""), 192)}
        for item in diagnostics[:3]
        if isinstance(item, dict)
    ]
    projection["findings"] = [
        {"code": clip_utf8(item.get("code", ""), 64), "summary": clip_utf8(item.get("summary", ""), 192)}
        for item in data.get("findings", [])[:3]
        if isinstance(item, dict)
    ]
    projection["paths_requiring_recheck"] = [clip_utf8(item, 160) for item in data.get("paths_requiring_recheck", [])[:3]]
    return projection


def main() -> int:
    try:
        event: Any = json.load(sys.stdin)
    except Exception:
        return block("EVENT_INVALID", "Hook input is not valid JSON.")
    if not isinstance(event, dict):
        return block("EVENT_INVALID", "Hook input must be a JSON object.")

    source = event.get("source")
    if source not in MATCHED_SOURCES:
        return 0

    session_id = event.get("session_id")
    cwd_value = event.get("cwd")
    if not isinstance(session_id, str) or not ID_RE.fullmatch(session_id):
        return block("IDENTIFIER_INVALID", "Codex session_id does not satisfy the common-core identifier rule.")
    if not isinstance(cwd_value, str) or not cwd_value:
        return block("CWD_INVALID", "Hook event has no usable cwd.")

    try:
        cwd = Path(cwd_value).resolve(strict=True)
        if not cwd.is_dir():
            return block("CWD_INVALID", "Hook cwd is not a directory.")
        working_root = find_working_root(cwd).resolve(strict=True)
    except ValueError:
        return block("WORKSPACE_ROOT_UNRESOLVED", "No Git marker or DEV_STATE common-core marker was found above cwd.")
    except Exception:
        return block("CWD_INVALID", "Hook cwd could not be resolved.")

    try:
        dev_state_dir = (working_root / "DEV_STATE").resolve(strict=True)
        if not dev_state_dir.is_dir():
            return block("WORKSPACE_ROOT_UNRESOLVED", "DEV_STATE is not a directory in the resolved working root.")
        state_parent = (dev_state_dir / "codex-sessions").resolve(strict=False)
    except Exception:
        return block("WORKSPACE_ROOT_UNRESOLVED", "DEV_STATE is missing from the resolved working root.")
    allowed_parent = dev_state_dir
    if not is_within(state_parent, allowed_parent):
        return block("PATH_OUTSIDE_WORKSPACE", "DEV_STATE session directory resolves outside the working root.")
    state_root = state_parent / session_id
    if not state_root.exists():
        return 0
    try:
        resolved_state_root = state_root.resolve(strict=True)
        if not is_within(resolved_state_root, state_parent):
            return block("PATH_OUTSIDE_WORKSPACE", "Session state path resolves outside the approved session directory.")
    except Exception:
        return block("STATE_PATH_INVALID", "Session state path could not be resolved safely.")

    core = working_root / "DEV_STATE" / "dev-state-core" / "dev_state.py"
    if not core.is_file():
        return block("CORE_ABSENT", "The common core is missing from the resolved working root.")

    argv = [
        sys.executable,
        str(core),
        "status",
        "--root",
        str(state_root),
        "--task-id",
        session_id,
        "--environment",
        "CODEX",
        "--context-key",
        session_id,
        "--compact",
    ]
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            argv,
            cwd=str(working_root),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return block("STATUS_TIMEOUT", "Read-only compact status exceeded five seconds.")
    except Exception:
        return block("STATUS_EXECUTION_FAILED", "The common-core status command could not be started.")

    raw = completed.stdout.rstrip(b"\r\n")
    if len(raw) > MAX_COMPACT:
        return block("STATUS_OUTPUT_OVERSIZE", "Common-core output exceeded its 4096-byte contract.")
    try:
        result = json.loads(raw.decode("utf-8", errors="strict"))
    except Exception:
        return block("STATUS_OUTPUT_INVALID", "Common-core output was not valid UTF-8 JSON.")
    if not isinstance(result, dict) or result.get("operation") != "status":
        return block("STATUS_OUTPUT_INVALID", "Common-core output did not match the status envelope.")
    if completed.returncode not in (0, 1):
        return block("STATUS_EXECUTION_FAILED", f"Common-core status returned exit {completed.returncode}.")

    data = result.get("data")
    refresh = (source == "compact" and completed.returncode == 0
               and result.get("status") == "OK" and isinstance(data, dict)
               and data.get("reconciliation") == "HASH_MATCH")
    suffix = "\n" + REFRESH_INSTRUCTION if refresh else ""
    budget = MAX_CONTEXT - len(suffix.encode("utf-8"))
    projection = projected_status(result, state_root, core, session_id, source, budget)
    context = json.dumps(projection, ensure_ascii=False, separators=(",", ":")) + suffix
    if len(context.encode("utf-8")) > MAX_CONTEXT:
        return block("STATUS_CONTEXT_OVERSIZE", "Compact status plus its exact invocation coordinates exceeded 4096 bytes.")
    emit_context(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import contextlib
import io
import json
from pathlib import Path

from agentix.audit_log import audit
from agentix.controller_plan import controller_plan
from agentix.goal import parse_goal
from agentix.worktree_run import DEFAULT_GOAL_TIMEOUT_SECONDS, worktree_run


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def controller_run(
    path: Path,
    goal: str,
    host: str = "nixos",
    module: str = "auto",
    agentix_command: str = "agentix",
    keep: bool = False,
    execute: bool = False,
    timeout: int | None = DEFAULT_GOAL_TIMEOUT_SECONDS,
) -> int:
    parsed = parse_goal(goal)
    plan = controller_plan(path)

    payload = {
        "action": "controller_run",
        "goal": goal,
        "path": str(path),
        "host": host,
        "module": module,
        "execute": execute,
        "parsed": parsed,
        "controller_plan": plan,
        "passed": False,
        "source_modified": False,
        "stops_before_apply": True,
        "stops_before_rebuild": True,
        "proposal_saved": None,
        "worktree_result": None,
        "error": None,
    }

    def _audit_controller(result_label: str, mode: str) -> None:
        audit(path, {
            "action": "controller_run",
            "mode": mode,
            "goal": goal,
            "result": result_label,
            "passed": payload["passed"],
            "execute": execute,
            "source_modified": payload["source_modified"],
            "proposal_saved": payload["proposal_saved"],
            "error": payload["error"],
            "path": str(path),
        })

    if parsed.get("kind") == "unsupported":
        payload["error"] = "unsupported_goal"
        _audit_controller("unsupported_goal", "dry_run" if not execute else "execute")
        emit(payload)
        return 1

    if not execute:
        payload["passed"] = True
        payload["mode"] = "dry_run"
        payload["would_run_worktree"] = True
        payload["would_save_proposal"] = True
        _audit_controller("ok", "dry_run")
        emit(payload)
        return 0

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = worktree_run(
            path=path,
            goal=goal,
            host=host,
            module=module,
            agentix_command=agentix_command,
            keep=keep,
            save_proposal_patch=True,
            json_output=True,
            audit_event=False,
            timeout=timeout,
        )

    raw = buffer.getvalue().strip()

    try:
        worktree_payload = json.loads(raw)
    except json.JSONDecodeError:
        payload["error"] = "invalid_worktree_json"
        payload["worktree_stdout"] = raw
        payload["mode"] = "execute"
        _audit_controller("invalid_worktree_json", "execute")
        emit(payload)
        return 1

    payload["worktree_result"] = worktree_payload
    payload["passed"] = code == 0 and bool(worktree_payload.get("passed"))
    payload["source_modified"] = bool(worktree_payload.get("source_modified"))
    payload["proposal_saved"] = worktree_payload.get("proposal_saved")
    payload["mode"] = "execute"

    if worktree_payload.get("source_mutations"):
        payload["source_mutations"] = worktree_payload["source_mutations"]

    if not payload["passed"]:
        payload["error"] = worktree_payload.get("error") or "worktree_run_failed"

    _audit_controller("ok" if payload["passed"] else (payload["error"] or "worktree_run_failed"), "execute")
    emit(payload)
    return code

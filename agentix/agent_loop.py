import json
from pathlib import Path

from agentix.goal import parse_goal
from agentix.worktree_run import DEFAULT_GOAL_TIMEOUT_SECONDS, worktree_run


def agent_loop(
    path: Path,
    goal: str,
    host: str = "nixos",
    module: str = "auto",
    agentix_command: str = "agentix",
    keep: bool = False,
    dry_run: bool = False,
    timeout: int | None = DEFAULT_GOAL_TIMEOUT_SECONDS,
) -> int:
    parsed = parse_goal(goal)

    if dry_run:
        payload = {
            "action": "agent_loop",
            "goal": goal,
            "path": str(path),
            "host": host,
            "module": module,
            "parsed": parsed,
            "dry_run": True,
            "passed": parsed.get("kind") != "unsupported",
            "would_run_worktree": parsed.get("kind") != "unsupported",
            "would_save_proposal": parsed.get("kind") != "unsupported",
            "source_modified": False,
            "stops_before_apply": True,
            "stops_before_rebuild": True,
        }
        if parsed.get("kind") == "unsupported":
            payload["error"] = "unsupported_goal"

        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["passed"] else 1

    return worktree_run(
        path=path,
        goal=goal,
        host=host,
        module=module,
        agentix_command=agentix_command,
        keep=keep,
        save_proposal_patch=True,
        json_output=True,
        timeout=timeout,
    )

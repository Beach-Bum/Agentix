import json
import subprocess
from pathlib import Path


def git_status(path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=path,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return ["not a git repository"]

    return [line for line in result.stdout.splitlines() if line.strip()]


def last_audit_event(path: Path) -> dict | None:
    audit_path = path / ".agentix" / "audit.jsonl"

    if not audit_path.exists():
        return None

    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if not lines:
        return None

    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"error": "last audit line is invalid JSON"}


def collect_status(path: Path) -> dict:
    proposals_dir = path / ".agentix" / "proposals"
    proposals = sorted(proposals_dir.glob("*.patch")) if proposals_dir.exists() else []

    return {
        "path": str(path),
        "has_git": (path / ".git").exists(),
        "git_dirty": git_status(path),
        "has_flake": (path / "flake.nix").exists(),
        "has_agentix": (path / ".agentix").exists(),
        "has_policy": (path / ".agentix" / "policy.json").exists(),
        "proposal_count": len(proposals),
        "latest_proposal": str(proposals[-1]) if proposals else None,
        "last_audit_event": last_audit_event(path),
    }


def print_status(status: dict) -> None:
    print("Agentix Status")
    print()

    print(f"Path: {status['path']}")
    print(f"Git repo: {'yes' if status['has_git'] else 'no'}")
    print(f"Flake: {'yes' if status['has_flake'] else 'no'}")
    print(f"Agentix workspace: {'yes' if status['has_agentix'] else 'no'}")
    print(f"Policy: {'yes' if status['has_policy'] else 'no'}")
    print(f"Saved proposals: {status['proposal_count']}")

    if status["latest_proposal"]:
        print(f"Latest proposal: {status['latest_proposal']}")

    print()
    if status["git_dirty"]:
        print("Git status: dirty")
        for line in status["git_dirty"]:
            print(f"  {line}")
    else:
        print("Git status: clean")

    print()
    if status["last_audit_event"]:
        print("Last audit event:")
        print(json.dumps(status["last_audit_event"], indent=2, sort_keys=True))
    else:
        print("Last audit event: none")

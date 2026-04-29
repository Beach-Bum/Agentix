import json
from pathlib import Path


def audit_path(path: Path) -> Path:
    return path / ".agentix" / "audit.jsonl"


def tail_audit(path: Path, lines: int = 10) -> list[str]:
    target = audit_path(path)

    if not target.exists():
        return []

    entries = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return entries[-lines:]


def print_audit_tail(path: Path, lines: int = 10) -> None:
    entries = tail_audit(path, lines)

    if not entries:
        print("No audit events found.")
        return

    for entry in entries:
        try:
            data = json.loads(entry)
            print(json.dumps(data, indent=2, sort_keys=True))
        except json.JSONDecodeError:
            print(entry)
        print()

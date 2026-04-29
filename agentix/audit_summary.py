import json
from collections import Counter
from pathlib import Path


def load_audit_events(path: Path) -> list[dict]:
    audit_path = path / ".agentix" / "audit.jsonl"

    if not audit_path.exists():
        return []

    events: list[dict] = []

    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({
                "action": "invalid_audit_line",
                "result": "invalid_json",
                "raw": line,
            })

    return events


def print_audit_summary(path: Path) -> None:
    events = load_audit_events(path)

    print("Agentix Audit Summary")
    print()
    print(f"Path: {path}")
    print(f"Total events: {len(events)}")

    if not events:
        return

    actions = Counter(str(event.get("action", "unknown")) for event in events)
    results = Counter(str(event.get("result", "unknown")) for event in events)

    risky = [
        event for event in events
        if event.get("result") in {"failed", "policy_denied", "patch_check_failed", "declined"}
        or event.get("policy_violations")
    ]

    print()
    print("Actions:")
    for action, count in actions.most_common():
        print(f"  {action}: {count}")

    print()
    print("Results:")
    for result, count in results.most_common():
        print(f"  {result}: {count}")

    print()
    print(f"Risky/failed events: {len(risky)}")

    print()
    print("Last event:")
    print(json.dumps(events[-1], indent=2, sort_keys=True))

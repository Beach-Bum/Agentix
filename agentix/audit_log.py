import json
from datetime import datetime, timezone
from pathlib import Path


def audit(path: Path, event: dict) -> None:
    audit_dir = path / ".agentix"
    audit_dir.mkdir(exist_ok=True)

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }

    with (audit_dir / "audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")

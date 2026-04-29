import json
from pathlib import Path


DEFAULT_POLICY = {
    "version": 1,
    "allow_read": ["."],
    "allow_write": ["./flake.nix", "./shell.nix", "./devshell.nix"],
    "deny_patterns": [
        "sudo",
        "rm -rf",
        "~/.ssh",
        "id_rsa",
        "id_ed25519",
        "/etc/nixos"
    ],
    "requires_approval": [
        "apply_patch",
        "network_access",
        "nixos_rebuild",
        "git_commit",
        "git_push"
    ]
}


def init_workspace(path: Path) -> None:
    agentix_dir = path / ".agentix"
    proposals_dir = agentix_dir / "proposals"

    agentix_dir.mkdir(exist_ok=True)
    proposals_dir.mkdir(exist_ok=True)

    policy_path = agentix_dir / "policy.json"
    audit_path = agentix_dir / "audit.jsonl"

    if not policy_path.exists():
        policy_path.write_text(
            json.dumps(DEFAULT_POLICY, indent=2) + "\n",
            encoding="utf-8",
        )

    if not audit_path.exists():
        audit_path.write_text("", encoding="utf-8")

    gitignore_path = path / ".gitignore"
    ignore_lines = [".agentix/audit.jsonl\n"]

    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""

    with gitignore_path.open("a", encoding="utf-8") as f:
        for line in ignore_lines:
            if line not in existing:
                f.write(line)

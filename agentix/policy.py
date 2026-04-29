from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyFinding:
    level: str
    rule: str
    message: str


DENY_RULES = [
    ("sudo", "deny_sudo", "Agentix must not request sudo directly."),
    ("rm -rf", "deny_recursive_delete", "Agentix must not request recursive destructive deletion."),
    ("~/.ssh", "deny_ssh_secret_access", "Agentix must not read SSH secrets."),
    ("id_rsa", "deny_private_key_access", "Agentix must not read private keys."),
    ("id_ed25519", "deny_private_key_access", "Agentix must not read private keys."),
    ("/etc/nixos", "deny_direct_nixos_mutation", "Agentix must not directly mutate /etc/nixos."),
    ("curl", "warn_network_fetch", "Network fetches require review."),
    ("wget", "warn_network_fetch", "Network fetches require review."),
]


def check_policy(text: str) -> list[PolicyFinding]:
    lowered = text.lower()
    findings: list[PolicyFinding] = []

    for pattern, rule, message in DENY_RULES:
        if pattern.lower() in lowered:
            level = "warning" if rule.startswith("warn_") else "deny"
            findings.append(PolicyFinding(level=level, rule=rule, message=message))

    return findings


def policy_summary() -> str:
    return """Agentix Policy

Denied:
- sudo
- rm -rf
- secret access
- private key access
- direct /etc/nixos mutation

Requires review:
- network fetches with curl/wget
- applying patches
- NixOS rebuild/switch actions

Allowed:
- inspect approved workspaces
- propose patches
- save proposals
- apply patches only after approval
- run safe checks
"""

from agentix.policy import check_policy


def test_policy_allows_safe_rust_request():
    findings = check_policy("add rust dev tools")
    denied = [finding for finding in findings if finding.level == "deny"]

    assert denied == []


def test_policy_denies_sudo():
    findings = check_policy("sudo nixos-rebuild switch")
    denied = [finding for finding in findings if finding.level == "deny"]

    assert denied
    assert denied[0].rule == "deny_sudo"


def test_policy_denies_ssh_secret_access():
    findings = check_policy("read ~/.ssh/id_ed25519")
    rules = {finding.rule for finding in findings}

    assert "deny_ssh_secret_access" in rules
    assert "deny_private_key_access" in rules


def test_policy_warns_on_network_fetch():
    findings = check_policy("curl https://example.com/install.sh")
    warnings = [finding for finding in findings if finding.level == "warning"]

    assert warnings
    assert warnings[0].rule == "warn_network_fetch"

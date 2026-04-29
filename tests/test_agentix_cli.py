import json
import subprocess
from pathlib import Path


def run_agentix(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "agentix", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agentix Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "agentix@example.test"], cwd=path, check=True)


def test_inspect_detects_rust_project(tmp_path: Path) -> None:
    project = tmp_path / "rust-project"
    project.mkdir()
    (project / "Cargo.toml").write_text(
        """[package]
name = "hello-agentix"
version = "0.1.0"
edition = "2021"

[dependencies]
""",
        encoding="utf-8",
    )

    result = run_agentix("inspect", str(project))

    assert result.returncode == 0
    data = json.loads(result.stdout)

    assert data["exists"] is True
    assert data["has_flake"] is False
    assert "rust" in data["detected_languages"]


def test_propose_rust_devshell_does_not_mutate_project(tmp_path: Path) -> None:
    project = tmp_path / "rust-project"
    project.mkdir()
    (project / "Cargo.toml").write_text(
        """[package]
name = "hello-agentix"
version = "0.1.0"
edition = "2021"

[dependencies]
""",
        encoding="utf-8",
    )

    result = run_agentix("propose", "add", "rust", "dev", "tools", "--path", str(project))

    assert result.returncode == 0
    assert "Proposal: create a Rust Nix dev shell." in result.stdout
    assert "This is only a proposal. No files were changed." in result.stdout
    assert "rust-analyzer" in result.stdout
    assert not (project / "flake.nix").exists()


def test_propose_save_apply_and_audit(tmp_path: Path) -> None:
    project = tmp_path / "rust-project"
    project.mkdir()
    init_git_repo(project)

    (project / "Cargo.toml").write_text(
        """[package]
name = "hello-agentix"
version = "0.1.0"
edition = "2021"

[dependencies]
""",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "Cargo.toml"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Initial Rust project"], cwd=project, check=True)

    proposal = run_agentix(
        "propose",
        "add",
        "rust",
        "dev",
        "tools",
        "--path",
        str(project),
        "--save",
    )

    assert proposal.returncode == 0
    assert "Saved proposal:" in proposal.stdout

    proposals = list((project / ".agentix" / "proposals").glob("*.patch"))
    assert len(proposals) == 1

    apply_result = run_agentix(
        "apply",
        str(proposals[0]),
        "--path",
        str(project),
        "--yes",
    )

    assert apply_result.returncode == 0
    assert (project / "flake.nix").exists()

    audit_log = project / ".agentix" / "audit.jsonl"
    assert audit_log.exists()

    audit_text = audit_log.read_text(encoding="utf-8")
    assert '"action": "propose"' in audit_text
    assert '"action": "apply"' in audit_text
    assert '"approval_required": true' in audit_text

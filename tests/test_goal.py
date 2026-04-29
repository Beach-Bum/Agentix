import subprocess
from pathlib import Path

from agentix.goal import apply_patch_and_verify, parse_goal, run_goal


def test_parse_add_package_goal():
    parsed = parse_goal("add package btop")

    assert parsed == {
        "kind": "package",
        "package": "btop",
        "module": "auto",
    }


def test_parse_install_package_to_module_goal():
    parsed = parse_goal("install lolcat to fun")

    assert parsed == {
        "kind": "package",
        "package": "lolcat",
        "module": "fun",
    }


def test_parse_create_module_goal():
    parsed = parse_goal("create module ai with template packages")

    assert parsed == {
        "kind": "module_create",
        "name": "ai",
        "template": "packages",
    }


def test_parse_unsupported_goal():
    parsed = parse_goal("please redesign my entire operating system")

    assert parsed["kind"] == "unsupported"


def test_run_goal_command_exists():
    result = subprocess.run(
        ["uv", "run", "agentix", "run", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run a supported high-level Agentix goal" in result.stdout


def test_run_goal_dry_run():
    result = subprocess.run(
        [
            "uv",
            "run",
            "agentix",
            "run",
            "add package btop",
            "--path",
            ".",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Agentix Goal Runner" in result.stdout
    assert "Dry run only" in result.stdout



def create_goal_fixture(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    (path / ".agentix").mkdir()
    (path / ".agentix" / "policy.json").write_text("{}", encoding="utf-8")
    (path / "flake.nix").write_text("{ outputs = { self }: {}; }\n", encoding="utf-8")
    (path / "modules").mkdir()
    (path / "modules" / "agentic-base.nix").write_text(
        """{ config, pkgs, ... }:

{
  imports = [
    ./devtools.nix
    ./fun.nix
  ];
}
""",
        encoding="utf-8",
    )
    (path / "modules" / "devtools.nix").write_text(
        """{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
  ];
}
""",
        encoding="utf-8",
    )
    (path / "modules" / "fun.nix").write_text(
        """{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
  ];
}
""",
        encoding="utf-8",
    )


def test_run_goal_module_create_allow_dirty_reaches_verify(tmp_path, monkeypatch, capsys):
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_goal_fixture(project)

    # Make the tree dirty with a normal tracked-workspace file.
    with (project / "modules" / "fun.nix").open("a", encoding="utf-8") as f:
        f.write("\n# dirty test\n")

    commands = []

    def fake_run_command(command, cwd):
        commands.append(command)
        return 0

    monkeypatch.setattr("agentix.goal.run_command", fake_run_command)

    result = run_goal(
        path=project,
        goal="create module ai with template packages",
        yes=True,
        allow_dirty=True,
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Preflight failed" not in output
    assert any(command[:3] == ["agentix", "verify", "--path"] for command in commands)



def test_goal_apply_refuses_stale_patch_before_prompt(tmp_path, monkeypatch, capsys):
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_goal_fixture(project)

    patch = project / ".agentix" / "proposals" / "stale.patch"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("not a usable patch\n", encoding="utf-8")

    commands = []

    def fake_run_command(command, cwd):
        commands.append(command)
        if command[:3] == ["git", "apply", "--check"]:
            return 1
        raise AssertionError(f"unexpected command after stale precheck: {command}")

    def fail_input(prompt):
        raise AssertionError(f"should not prompt on stale patch: {prompt}")

    monkeypatch.setattr("agentix.goal.run_command", fake_run_command)
    monkeypatch.setattr("builtins.input", fail_input)

    result = apply_patch_and_verify(
        path=project,
        patch_path=patch,
        host="nixos",
        yes=False,
        allow_dirty=True,
    )

    output = capsys.readouterr().out

    assert result != 0
    assert "Patch is stale or does not apply cleanly" in output
    assert commands == [["git", "apply", "--check", str(patch)]]

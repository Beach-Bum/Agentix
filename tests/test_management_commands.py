import json
import subprocess
from pathlib import Path


def run_agentix(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "agentix", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def init_git(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Agentix Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "agentix@example.test"], cwd=path, check=True)


def create_nixos_fixture(path: Path) -> None:
    init_git(path)

    (path / "modules").mkdir()

    (path / "flake.nix").write_text(
        """{
  description = "Agentix test config";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };

  outputs = { self, nixpkgs, ... }:
    let
      system = "x86_64-linux";
      hostname = "nixos";
    in
    {
      nixosConfigurations.${hostname} = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          ./configuration.nix
        ];
      };
    };
}
""",
        encoding="utf-8",
    )

    (path / "configuration.nix").write_text(
        """{ config, pkgs, ... }:

{
  imports = [
    ./modules/agentic-base.nix
  ];

  system.stateVersion = "24.11";
}
""",
        encoding="utf-8",
    )

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
    git
  ];
}
""",
        encoding="utf-8",
    )

    (path / "modules" / "fun.nix").write_text(
        """{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
    cowsay
  ];
}
""",
        encoding="utf-8",
    )

    result = run_agentix("init", ".", cwd=path)
    assert result.returncode == 0, result.stderr

    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial fixture"], cwd=path, check=True, capture_output=True)


def test_doctor_passes_on_initialized_fixture(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix("doctor", "--path", str(project), cwd=project)

    assert result.returncode == 0
    assert "Doctor result: ready" in result.stdout


def test_status_reports_agentix_workspace(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix("status", "--path", str(project), cwd=project)

    assert result.returncode == 0
    assert "Agentix workspace: yes" in result.stdout
    assert "Policy: yes" in result.stdout


def test_package_refuses_dirty_tree(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    with (project / "modules" / "fun.nix").open("a", encoding="utf-8") as f:
        f.write("\n# dirty test\n")

    result = run_agentix(
        "package",
        "figlet",
        "--path",
        str(project),
        "--module",
        "fun",
        cwd=project,
    )

    assert result.returncode != 0
    assert "Preflight failed" in result.stdout
    assert "Git tree is dirty" in result.stdout


def test_proposals_list_and_clean(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    proposal = proposal_dir / "test.patch"
    proposal.write_text("--- a/file\n+++ b/file\n", encoding="utf-8")

    listed = run_agentix("proposals", "list", "--path", str(project), cwd=project)

    assert listed.returncode == 0
    assert "test.patch" in listed.stdout

    cleaned = run_agentix("proposals", "clean", "--path", str(project), "--yes", cwd=project)

    assert cleaned.returncode == 0
    assert "Deleted 1 proposal" in cleaned.stdout
    assert not proposal.exists()


def test_audit_tail_handles_empty_or_existing_log(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix("audit", "tail", "--path", str(project), "--lines", "3", cwd=project)

    assert result.returncode == 0
    assert "action" in result.stdout or "No audit events found" in result.stdout


def test_proposals_prune_stale_removes_unapplicable_patch(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    stale = proposal_dir / "stale.patch"
    stale.write_text(
        """--- a/modules/fun.nix
+++ b/modules/fun.nix
@@ -999,1 +999,1 @@
-this line does not exist
+this line also does not exist
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "proposals",
        "prune-stale",
        "--path",
        str(project),
        "--yes",
        cwd=project,
    )

    assert result.returncode == 0
    assert "Deleted 1 stale proposal" in result.stdout
    assert not stale.exists()


def test_audit_summary_reports_events(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "audit",
        "summary",
        "--path",
        str(project),
        cwd=project,
    )

    assert result.returncode == 0
    assert "Agentix Audit Summary" in result.stdout
    assert "Total events:" in result.stdout


def test_verify_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "verify", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run doctor, NixOS build check, and VM build check" in result.stdout


def test_verify_help_includes_json_flag() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "verify", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "--json" in result.stdout


def test_switch_plan_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "switch-plan", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Print the human-controlled NixOS switch plan" in result.stdout


def test_public_check_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Check whether a repo is safe to publish publicly" in result.stdout


def test_export_public_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "export-public", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Create a sanitized public export of a private repo" in result.stdout


def test_export_public_excludes_private_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    dest = tmp_path / "public"

    source.mkdir()
    (source / "agentix").mkdir()
    (source / "tests").mkdir()
    (source / "private").mkdir()
    (source / ".git").mkdir()
    (source / ".agentix").mkdir()

    (source / "README.md").write_text("# Test\n", encoding="utf-8")
    (source / "MEMORY.md").write_text("private memory\n", encoding="utf-8")
    (source / "private" / "note.md").write_text("secret\n", encoding="utf-8")
    (source / "agentix" / "__init__.py").write_text("", encoding="utf-8")
    (source / "tests" / "test_example.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

    result = subprocess.run(
        [
            "uv",
            "run",
            "agentix",
            "export-public",
            "--path",
            str(source),
            "--dest",
            str(dest),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert (dest / "README.md").exists()
    assert (dest / "agentix" / "__init__.py").exists()
    assert not (dest / "MEMORY.md").exists()
    assert not (dest / "private").exists()
    assert not (dest / ".git").exists()
    assert not (dest / ".agentix").exists()


def test_modules_list_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "modules", "list", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "List NixOS modules" in result.stdout


def test_modules_list_reports_fixture_modules(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "modules",
        "list",
        "--path",
        str(project),
        cwd=project,
    )

    assert result.returncode == 0
    assert "agentic-base" in result.stdout
    assert "devtools" in result.stdout
    assert "fun" in result.stdout


def test_modules_create_accepts_template_flag() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "modules", "create", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "--template" in result.stdout


def test_modules_create_packages_template(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "modules",
        "create",
        "media",
        "--path",
        str(project),
        "--template",
        "packages",
        cwd=project,
    )

    assert result.returncode == 0
    assert "template `packages`" in result.stdout
    assert "b/modules/media.nix" in result.stdout
    assert "environment.systemPackages = with pkgs;" in result.stdout


def test_package_flow_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "package-flow", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run propose, approve, apply, and verify for a package change" in result.stdout


def test_package_flow_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "package-flow", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run propose, approve, apply, and verify for a package change" in result.stdout


def test_apply_verify_refuses_dirty_tree(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    with (project / "modules" / "fun.nix").open("a", encoding="utf-8") as f:
        f.write("\n# dirty test\n")

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    patch = proposal_dir / "create-ai.patch"
    patch.write_text(
        """diff --git a/modules/ai.nix b/modules/ai.nix
new file mode 100644
index 0000000..1a12632
--- /dev/null
+++ b/modules/ai.nix
@@ -0,0 +1,7 @@
+{ config, pkgs, ... }:
+
+{
+  # ai module
+  environment.systemPackages = with pkgs; [
+  ];
+}
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "apply-verify",
        str(patch),
        "--path",
        str(project),
        "--yes",
        cwd=project,
    )

    assert result.returncode != 0
    assert "Preflight failed" in result.stdout
    assert "Git tree is dirty" in result.stdout
    assert not (project / "modules" / "ai.nix").exists()


def test_run_module_create_refuses_dirty_tree(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    with (project / "modules" / "fun.nix").open("a", encoding="utf-8") as f:
        f.write("\n# dirty test\n")

    result = run_agentix(
        "run",
        "create module media with template packages",
        "--path",
        str(project),
        "--yes",
        cwd=project,
    )

    assert result.returncode != 0
    assert "Preflight failed" in result.stdout
    assert "Git tree is dirty" in result.stdout
    assert not (project / "modules" / "media.nix").exists()


def test_flow_commands_expose_allow_dirty() -> None:
    package_flow = subprocess.run(
        ["uv", "run", "agentix", "package-flow", "--help"],
        text=True,
        capture_output=True,
    )
    apply_verify = subprocess.run(
        ["uv", "run", "agentix", "apply-verify", "--help"],
        text=True,
        capture_output=True,
    )
    goal_run = subprocess.run(
        ["uv", "run", "agentix", "run", "--help"],
        text=True,
        capture_output=True,
    )

    assert package_flow.returncode == 0
    assert apply_verify.returncode == 0
    assert goal_run.returncode == 0
    assert "--allow-dirty" in package_flow.stdout
    assert "--allow-dirty" in apply_verify.stdout
    assert "--allow-dirty" in goal_run.stdout



def test_apply_refuses_stale_patch_before_prompt(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    patch = proposal_dir / "stale.patch"
    patch.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "uv",
            "run",
            "agentix",
            "apply",
            str(patch),
            "--path",
            str(project),
        ],
        cwd=project,
        text=True,
        input="",
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Patch is stale or does not apply cleanly" in result.stdout
    assert "Apply this patch" not in result.stdout
    assert "EOFError" not in result.stderr


def test_apply_verify_refuses_stale_patch_before_prompt(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    patch = proposal_dir / "stale.patch"
    patch.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "uv",
            "run",
            "agentix",
            "apply-verify",
            str(patch),
            "--path",
            str(project),
        ],
        cwd=project,
        text=True,
        input="",
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Patch is stale or does not apply cleanly" in result.stdout
    assert "Apply this patch and run verify" not in result.stdout
    assert "EOFError" not in result.stderr



def test_proposals_list_marks_clean_and_stale(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    clean = proposal_dir / "clean.patch"
    clean.write_text(
        """diff --git a/modules/ai.nix b/modules/ai.nix
new file mode 100644
index 0000000..1a12632
--- /dev/null
+++ b/modules/ai.nix
@@ -0,0 +1,7 @@
+{ config, pkgs, ... }:
+
+{
+  # ai module
+  environment.systemPackages = with pkgs; [
+  ];
+}
""",
        encoding="utf-8",
    )

    stale = proposal_dir / "stale.patch"
    stale.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = run_agentix("proposals", "list", "--path", str(project), cwd=project)

    assert result.returncode == 0
    assert "[clean] clean.patch" in result.stdout
    assert "[stale] stale.patch" in result.stdout



def test_proposals_clean_stale_deletes_only_stale(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    clean = proposal_dir / "clean.patch"
    clean.write_text(
        """diff --git a/modules/ai.nix b/modules/ai.nix
new file mode 100644
index 0000000..1a12632
--- /dev/null
+++ b/modules/ai.nix
@@ -0,0 +1,7 @@
+{ config, pkgs, ... }:
+
+{
+  # ai module
+  environment.systemPackages = with pkgs; [
+  ];
+}
""",
        encoding="utf-8",
    )

    stale = proposal_dir / "stale.patch"
    stale.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "proposals",
        "clean",
        "--path",
        str(project),
        "--stale",
        "--yes",
        cwd=project,
    )

    assert result.returncode == 0
    assert "Deleted 1 stale proposal" in result.stdout
    assert clean.exists()
    assert not stale.exists()



def test_proposals_list_json_reports_status(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    clean = proposal_dir / "clean.patch"
    clean.write_text(
        """diff --git a/modules/ai.nix b/modules/ai.nix
new file mode 100644
index 0000000..1a12632
--- /dev/null
+++ b/modules/ai.nix
@@ -0,0 +1,7 @@
+{ config, pkgs, ... }:
+
+{
+  # ai module
+  environment.systemPackages = with pkgs; [
+  ];
+}
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "proposals",
        "list",
        "--path",
        str(project),
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    assert '"name": "clean.patch"' in result.stdout
    assert '"status": "clean"' in result.stdout
    assert '"path":' in result.stdout



def test_proposals_clean_stale_json_deletes_only_stale(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    clean = proposal_dir / "clean.patch"
    clean.write_text(
        """diff --git a/modules/ai.nix b/modules/ai.nix
new file mode 100644
index 0000000..1a12632
--- /dev/null
+++ b/modules/ai.nix
@@ -0,0 +1,7 @@
+{ config, pkgs, ... }:
+
+{
+  # ai module
+  environment.systemPackages = with pkgs; [
+  ];
+}
""",
        encoding="utf-8",
    )

    stale = proposal_dir / "stale.patch"
    stale.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "proposals",
        "clean",
        "--path",
        str(project),
        "--stale",
        "--yes",
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    assert '"action": "proposals_clean"' in result.stdout
    assert '"mode": "stale"' in result.stdout
    assert '"deleted": 1' in result.stdout
    assert clean.exists()
    assert not stale.exists()


def test_proposals_prune_stale_json_reports_deleted_count(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    proposal_dir = project / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    stale = proposal_dir / "stale.patch"
    stale.write_text(
        """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
""",
        encoding="utf-8",
    )

    result = run_agentix(
        "proposals",
        "prune-stale",
        "--path",
        str(project),
        "--yes",
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    assert '"action": "proposals_prune_stale"' in result.stdout
    assert '"deleted": 1' in result.stdout
    assert not stale.exists()



def test_audit_tail_json_reports_recent_events(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    audit_dir = project / ".agentix"
    audit_dir.mkdir(exist_ok=True)
    audit_log = audit_dir / "audit.jsonl"
    audit_log.write_text(
        "\n".join(
            [
                json.dumps({"action": "doctor", "result": "passed"}),
                json.dumps({"action": "proposals_clean", "result": "ok_stale"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_agentix(
        "audit",
        "tail",
        "--path",
        str(project),
        "--lines",
        "1",
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    events = json.loads(result.stdout)
    assert len(events) == 1
    assert events[0]["action"] == "proposals_clean"
    assert events[0]["result"] == "ok_stale"


def test_audit_summary_json_reports_counts(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    audit_dir = project / ".agentix"
    audit_dir.mkdir(exist_ok=True)
    audit_log = audit_dir / "audit.jsonl"
    audit_log.write_text(
        "\n".join(
            [
                json.dumps({"action": "doctor", "result": "passed"}),
                json.dumps({"action": "doctor", "result": "passed"}),
                json.dumps({"action": "apply", "result": "stale"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_agentix(
        "audit",
        "summary",
        "--path",
        str(project),
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["total"] == 3
    assert summary["actions"]["doctor"] == 2
    assert summary["actions"]["apply"] == 1
    assert summary["results"]["passed"] == 2
    assert summary["results"]["stale"] == 1



def test_self_test_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "self-test", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run installed-command smoke tests" in result.stdout


def test_self_test_runs_controller_smoke_to_completion() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "self-test"],
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Self-test passed." in result.stdout
    assert "OK proposals list --json" in result.stdout
    assert "OK proposals clean --stale --json" in result.stdout
    assert "OK audit tail --json" in result.stdout
    assert "OK audit summary --json" in result.stdout
    assert "OK controller-plan --json" in result.stdout
    assert "OK controller-run dry-run" in result.stdout
    assert "OK controller-run --execute" in result.stdout



def test_worktree_run_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "worktree-run", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run a supported goal inside a temporary Git worktree" in result.stdout


def test_worktree_run_uses_temp_worktree_without_touching_source(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# created in temp worktree' > modules/fake.nix
git add modules/fake.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module fake with template packages",
        agentix_command=str(fake_agentix),
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Agentix Worktree Run" in output
    assert "modules/fake.nix" in output
    assert "Original workspace was not modified" in output
    assert not (project / "modules" / "fake.nix").exists()



def test_worktree_run_keep_preserves_temp_worktree(tmp_path: Path, capsys) -> None:
    import re
    import shutil

    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# kept temp worktree file' > modules/kept.nix
git add modules/kept.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module kept with template packages",
        agentix_command=str(fake_agentix),
        keep=True,
    )

    output = capsys.readouterr().out
    match = re.search(r"Kept temporary worktree: (.+)", output)

    assert result == 0
    assert match is not None

    kept = Path(match.group(1).strip())
    try:
        assert kept.exists()
        assert (kept / "modules" / "kept.nix").exists()
        assert not (project / "modules" / "kept.nix").exists()
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(kept)], cwd=project, check=False)
        shutil.rmtree(kept.parent, ignore_errors=True)



def test_worktree_run_save_proposal_saves_patch_without_touching_source(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# proposal temp worktree file' > modules/proposal.nix
git add modules/proposal.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module proposal with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
    )

    output = capsys.readouterr().out
    proposals = list((project / ".agentix" / "proposals").glob("*worktree-create-module-proposal-with-template-packages.patch"))

    assert result == 0
    assert "Saved proposal:" in output
    assert "Original workspace was not modified" in output
    assert not (project / "modules" / "proposal.nix").exists()
    assert len(proposals) == 1
    assert "modules/proposal.nix" in proposals[0].read_text(encoding="utf-8")



def test_worktree_run_json_reports_saved_proposal(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# json proposal file' > modules/json-proposal.nix
git add modules/json-proposal.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module json proposal with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload["proposal_saved"] is not None
    assert "modules/json-proposal.nix" in payload["staged_diff"]
    assert not (project / "modules" / "json-proposal.nix").exists()
    assert Path(payload["proposal_saved"]).exists()


def test_worktree_run_json_preflight_failure(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "not-a-repo"
    project.mkdir()

    result = worktree_run(
        path=project,
        goal="create module nope with template packages",
        json_output=True,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result != 0
    assert payload["passed"] is False
    assert payload["error"] == "preflight_failed"



def test_agent_loop_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "agent-loop", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run one safe sandboxed agent loop" in result.stdout


def test_agent_loop_saves_proposal_and_outputs_json(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# agent loop proposal file' > modules/agent-loop.nix
git add modules/agent-loop.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = run_agentix(
        "agent-loop",
        "create module agent-loop with template packages",
        "--path",
        str(project),
        "--agentix-command",
        str(fake_agentix),
        cwd=project,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload["proposal_saved"] is not None
    assert "modules/agent-loop.nix" in payload["staged_diff"]
    assert not (project / "modules" / "agent-loop.nix").exists()
    assert Path(payload["proposal_saved"]).exists()



def test_agent_loop_dry_run_outputs_plan_json(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "agent-loop",
        "create module dryrun with template packages",
        "--path",
        str(project),
        "--dry-run",
        cwd=project,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["action"] == "agent_loop"
    assert payload["dry_run"] is True
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload["would_run_worktree"] is True
    assert payload["would_save_proposal"] is True
    assert payload["stops_before_apply"] is True
    assert payload["stops_before_rebuild"] is True
    assert payload["parsed"]["kind"] == "module_create"
    assert not (project / "modules" / "dryrun.nix").exists()


def test_agent_loop_dry_run_rejects_unsupported_goal(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "agent-loop",
        "redesign my entire computer",
        "--path",
        str(project),
        "--dry-run",
        cwd=project,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)

    assert payload["dry_run"] is True
    assert payload["passed"] is False
    assert payload["error"] == "unsupported_goal"
    assert payload["would_run_worktree"] is False
    assert payload["source_modified"] is False



def test_controller_plan_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "controller-plan", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Print the safe command contract" in result.stdout


def test_controller_plan_json_reports_boundaries(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "controller-plan",
        "--path",
        str(project),
        "--json",
        cwd=project,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["action"] == "controller_plan"
    assert payload["source_workspace_must_remain_untouched"] is True
    assert payload["final_activation"] == "human_controlled"
    assert payload["default_mode"] == "dry_run_first"
    assert any("agent-loop" in command for command in payload["allowed_commands"])
    assert "sudo" in payload["forbidden_commands"]
    assert "rebuild-nixos" in payload["forbidden_commands"]



def test_controller_run_command_exists() -> None:
    result = subprocess.run(
        ["uv", "run", "agentix", "controller-run", "--help"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Run a controller-safe goal plan" in result.stdout


def test_controller_run_defaults_to_dry_run_json(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "controller-run",
        "create module controllerdry with template packages",
        "--path",
        str(project),
        cwd=project,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["action"] == "controller_run"
    assert payload["mode"] == "dry_run"
    assert payload["execute"] is False
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload["would_run_worktree"] is True
    assert payload["would_save_proposal"] is True
    assert payload["stops_before_apply"] is True
    assert payload["stops_before_rebuild"] is True
    assert payload["controller_plan"]["final_activation"] == "human_controlled"
    assert not (project / "modules" / "controllerdry.nix").exists()


def test_controller_run_execute_saves_proposal_without_touching_source(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# controller run proposal file' > modules/controller-run.nix
git add modules/controller-run.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = run_agentix(
        "controller-run",
        "create module controller-run with template packages",
        "--path",
        str(project),
        "--agentix-command",
        str(fake_agentix),
        "--execute",
        cwd=project,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["action"] == "controller_run"
    assert payload["mode"] == "execute"
    assert payload["execute"] is True
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload["proposal_saved"] is not None
    assert payload["stops_before_apply"] is True
    assert payload["stops_before_rebuild"] is True
    assert "modules/controller-run.nix" in payload["worktree_result"]["staged_diff"]
    assert not (project / "modules" / "controller-run.nix").exists()
    assert Path(payload["proposal_saved"]).exists()


def test_controller_run_rejects_unsupported_goal(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    result = run_agentix(
        "controller-run",
        "take over the whole machine",
        "--path",
        str(project),
        cwd=project,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)

    assert payload["passed"] is False
    assert payload["error"] == "unsupported_goal"
    assert payload["source_modified"] is False


def test_worktree_run_source_check_clean_run_reports_unchanged(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# clean worktree work' > modules/clean.nix
git add modules/clean.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module clean with template packages",
        agentix_command=str(fake_agentix),
        json_output=True,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload.get("error") is None
    assert "source_mutations" not in payload
    assert not (project / "modules" / "clean.nix").exists()


def test_worktree_run_source_check_save_proposal_allowed(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# proposal-allowed worktree work' > modules/allowed.nix
git add modules/allowed.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module allowed with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["passed"] is True
    assert payload["source_modified"] is False
    assert payload.get("error") is None
    assert "source_mutations" not in payload
    assert payload["proposal_saved"] is not None
    assert Path(payload["proposal_saved"]).exists()
    assert not (project / "modules" / "allowed.nix").exists()


def test_worktree_run_source_check_detects_source_taint(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# tainted source file' > "{project}/modules/tampered.nix"
printf '%s\n' '# legit worktree work' > modules/legit.nix
git add modules/legit.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = worktree_run(
        path=project,
        goal="create module legit with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result != 0
    assert payload["passed"] is False
    assert payload["source_modified"] is True
    assert payload["error"] == "source_workspace_mutated"
    assert isinstance(payload.get("source_mutations"), list)
    assert any("modules/tampered.nix" in m for m in payload["source_mutations"])
    assert (project / "modules" / "tampered.nix").exists()


def _read_audit_events(project: Path) -> list[dict]:
    audit_log = project / ".agentix" / "audit.jsonl"
    if not audit_log.exists():
        return []
    return [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_worktree_run_audit_event_on_success(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# audit-success worktree work' > modules/audit-ok.nix
git add modules/audit-ok.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    before = len(_read_audit_events(project))

    rc = worktree_run(
        path=project,
        goal="create module audit-ok with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
    )
    capsys.readouterr()

    after = _read_audit_events(project)

    assert rc == 0
    assert len(after) == before + 1
    event = after[-1]
    assert event["action"] == "worktree_run"
    assert event["mode"] == "worktree"
    assert event["result"] == "ok"
    assert event["passed"] is True
    assert event["source_modified"] is False
    assert event["proposal_saved"] is not None
    assert event["error"] is None
    assert event["path"] == str(project)
    assert "timestamp" in event


def test_worktree_run_audit_event_on_source_mutation(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# audit-taint source file' > "{project}/modules/audit-taint.nix"
printf '%s\n' '# audit-taint legit work' > modules/audit-legit.nix
git add modules/audit-legit.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    before = len(_read_audit_events(project))

    rc = worktree_run(
        path=project,
        goal="create module audit-legit with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
    )
    capsys.readouterr()

    after = _read_audit_events(project)

    assert rc != 0
    assert len(after) == before + 1
    event = after[-1]
    assert event["action"] == "worktree_run"
    assert event["mode"] == "worktree"
    assert event["result"] == "source_workspace_mutated"
    assert event["passed"] is False
    assert event["source_modified"] is True
    assert event["error"] == "source_workspace_mutated"
    assert event["path"] == str(project)


def test_controller_run_audit_events_for_dry_run_and_execute(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# controller-audit work' > modules/controller-audit.nix
git add modules/controller-audit.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    before = len(_read_audit_events(project))

    dry = run_agentix(
        "controller-run",
        "create module controller-audit with template packages",
        "--path",
        str(project),
        cwd=project,
    )
    assert dry.returncode == 0

    after_dry = _read_audit_events(project)
    assert len(after_dry) == before + 1
    dry_event = after_dry[-1]
    assert dry_event["action"] == "controller_run"
    assert dry_event["mode"] == "dry_run"
    assert dry_event["result"] == "ok"
    assert dry_event["execute"] is False
    assert dry_event["passed"] is True
    assert dry_event["source_modified"] is False
    assert dry_event["proposal_saved"] is None
    assert dry_event["error"] is None
    assert dry_event["path"] == str(project)

    exe = run_agentix(
        "controller-run",
        "create module controller-audit with template packages",
        "--path",
        str(project),
        "--agentix-command",
        str(fake_agentix),
        "--execute",
        cwd=project,
    )
    assert exe.returncode == 0

    after_exe = _read_audit_events(project)
    new = after_exe[len(after_dry):]
    assert len(new) == 1
    assert all(event["action"] == "controller_run" for event in new)

    outer = new[-1]
    assert outer["action"] == "controller_run"
    assert outer["mode"] == "execute"
    assert outer["result"] == "ok"
    assert outer["execute"] is True
    assert outer["passed"] is True
    assert outer["source_modified"] is False
    assert outer["proposal_saved"] is not None
    assert outer["error"] is None
    assert outer["path"] == str(project)


def test_worktree_run_cli_direct_invocation_writes_worktree_audit_event(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# direct cli worktree work' > modules/direct-wt.nix
git add modules/direct-wt.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    before = len(_read_audit_events(project))

    result = run_agentix(
        "worktree-run",
        "create module direct-wt with template packages",
        "--path",
        str(project),
        "--agentix-command",
        str(fake_agentix),
        "--save-proposal",
        "--json",
        cwd=project,
    )
    assert result.returncode == 0

    after = _read_audit_events(project)
    new = after[before:]

    assert len(new) == 1
    event = new[-1]
    assert event["action"] == "worktree_run"
    assert event["mode"] == "worktree"
    assert event["result"] == "ok"
    assert event["passed"] is True
    assert event["source_modified"] is False
    assert event["proposal_saved"] is not None
    assert event["error"] is None
    assert event["path"] == str(project)


def test_controller_run_execute_propagates_source_mutation_failure(tmp_path: Path) -> None:
    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '# controller-run taint' > "{project}/modules/controller-tampered.nix"
printf '%s\n' '# controller-run legit' > modules/controller-legit.nix
git add modules/controller-legit.nix
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    result = run_agentix(
        "controller-run",
        "create module controller-legit with template packages",
        "--path",
        str(project),
        "--agentix-command",
        str(fake_agentix),
        "--execute",
        cwd=project,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)

    assert payload["action"] == "controller_run"
    assert payload["mode"] == "execute"
    assert payload["execute"] is True
    assert payload["passed"] is False
    assert payload["source_modified"] is True
    assert payload["error"] == "source_workspace_mutated"
    assert isinstance(payload.get("source_mutations"), list)
    assert any("modules/controller-tampered.nix" in m for m in payload["source_mutations"])
    assert (project / "modules" / "controller-tampered.nix").exists()


def test_public_check_blocks_dot_claude_artifact(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Result: not public-safe" in result.stdout
    assert ".claude" in result.stdout


def test_public_check_blocks_save_file(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")
    nested = project / "drafts"
    nested.mkdir()
    (nested / "config.nix.save").write_text("# stale editor backup\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Result: not public-safe" in result.stdout
    assert "drafts/config.nix.save" in result.stdout


def test_public_check_allows_intentional_claude_docs(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")
    docs = project / "docs"
    docs.mkdir()
    (docs / "CLAUDE-CODE.md").write_text("# claude code contract\n", encoding="utf-8")
    prompts = docs / "prompts"
    prompts.mkdir()
    (prompts / "claude-agentix-controller.md").write_text("# prompt\n", encoding="utf-8")
    (docs / "CONTROLLER.md").write_text("# controller commands\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Result: public-safe candidate" in result.stdout
    assert "CLAUDE-CODE.md" not in result.stdout
    assert "claude-agentix-controller.md" not in result.stdout
    assert "CONTROLLER.md" not in result.stdout


def test_public_check_skips_internal_dirs(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")
    git_dir = project / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    venv = project / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Result: public-safe candidate" in result.stdout


def test_public_check_blocks_session_transcript_and_log_artifacts(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")

    nested = project / "data"
    nested.mkdir()
    (nested / "chat.transcript").write_text("turn 1\n", encoding="utf-8")
    (nested / "session.session.json").write_text("{}\n", encoding="utf-8")
    (project / "build.log").write_text("INFO\n", encoding="utf-8")
    (project / "MEMORY.md").write_text("private\n", encoding="utf-8")
    (project / "CLAUDE.local.md").write_text("local memory\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    output = result.stdout
    assert "data/chat.transcript" in output
    assert "data/session.session.json" in output
    assert "build.log" in output
    assert "MEMORY.md" in output
    assert "CLAUDE.local.md" in output


def test_public_check_flags_scripts_checkpoint_basename(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text("# ok\n", encoding="utf-8")
    scripts = project / "scripts"
    scripts.mkdir()
    (scripts / "checkpoint").write_text("#!/usr/bin/env bash\necho private\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Result: not public-safe" in result.stdout
    assert "scripts/checkpoint" in result.stdout


def test_public_check_allows_docs_mentioning_checkpoint(tmp_path: Path) -> None:
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "README.md").write_text(
        "# Project\n\nThis project mentions checkpoints in prose.\n",
        encoding="utf-8",
    )
    docs = project / "docs"
    docs.mkdir()
    (docs / "CONTROLLER.md").write_text(
        "# Controller\n\nPrivate repos may contain checkpoints.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Result: public-safe candidate" in result.stdout


def test_export_public_excludes_scripts_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source"
    dest = tmp_path / "public"

    source.mkdir()
    (source / "README.md").write_text("# ok\n", encoding="utf-8")
    scripts = source / "scripts"
    scripts.mkdir()
    (scripts / "checkpoint").write_text("#!/usr/bin/env bash\necho private\n", encoding="utf-8")
    (scripts / "dev-cycle").write_text("#!/usr/bin/env bash\necho dev\n", encoding="utf-8")

    result = subprocess.run(
        [
            "uv", "run", "agentix", "export-public",
            "--path", str(source),
            "--dest", str(dest),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert (dest / "README.md").exists()
    assert (dest / "scripts").exists()
    assert (dest / "scripts" / "dev-cycle").exists()
    assert not (dest / "scripts" / "checkpoint").exists()

    follow_up = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(dest)],
        text=True,
        capture_output=True,
    )
    assert follow_up.returncode == 0
    assert "Result: public-safe candidate" in follow_up.stdout


def test_export_public_excludes_claude_and_session_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    dest = tmp_path / "public"

    source.mkdir()
    (source / "README.md").write_text("# ok\n", encoding="utf-8")
    (source / ".claude").mkdir()
    (source / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (source / "CLAUDE.local.md").write_text("private\n", encoding="utf-8")
    nested = source / "data"
    nested.mkdir()
    (nested / "chat.transcript").write_text("turn 1\n", encoding="utf-8")
    (nested / "draft.save").write_text("draft\n", encoding="utf-8")

    result = subprocess.run(
        [
            "uv", "run", "agentix", "export-public",
            "--path", str(source),
            "--dest", str(dest),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert (dest / "README.md").exists()
    assert not (dest / ".claude").exists()
    assert not (dest / "CLAUDE.local.md").exists()
    assert (dest / "data").exists()
    assert not (dest / "data" / "chat.transcript").exists()
    assert not (dest / "data" / "draft.save").exists()

    follow_up = subprocess.run(
        ["uv", "run", "agentix", "public-check", "--path", str(dest)],
        text=True,
        capture_output=True,
    )
    assert follow_up.returncode == 0
    assert "Result: public-safe candidate" in follow_up.stdout


def test_worktree_run_subprocess_timeout(tmp_path: Path, capsys) -> None:
    from agentix.worktree_run import worktree_run

    project = tmp_path / "nixos-config"
    project.mkdir()
    create_nixos_fixture(project)

    fake_agentix = tmp_path / "fake-agentix"
    fake_agentix.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
sleep 5
""",
        encoding="utf-8",
    )
    fake_agentix.chmod(0o755)

    before = len(_read_audit_events(project))

    rc = worktree_run(
        path=project,
        goal="create module timeout-victim with template packages",
        agentix_command=str(fake_agentix),
        save_proposal_patch=True,
        json_output=True,
        timeout=1,
    )

    output = capsys.readouterr().out
    payload = json.loads(output)

    assert rc != 0
    assert payload["passed"] is False
    assert payload["error"] == "timeout"
    assert payload["timeout_seconds"] == 1
    assert payload["source_modified"] is False
    assert payload["proposal_saved"] is None

    after = _read_audit_events(project)
    new = after[before:]
    assert len(new) == 1
    event = new[-1]
    assert event["action"] == "worktree_run"
    assert event["mode"] == "worktree"
    assert event["result"] == "timeout"
    assert event["error"] == "timeout"
    assert event["passed"] is False

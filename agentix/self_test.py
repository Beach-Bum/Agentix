import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MODULE = """{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
  ];
}
"""

AGENTIC_BASE = """{ config, pkgs, ... }:

{
  imports = [
    ./devtools.nix
    ./fun.nix
  ];
}
"""

CLEAN_PATCH = """diff --git a/modules/ai.nix b/modules/ai.nix
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
"""

STALE_PATCH = """diff --git a/modules/missing.nix b/modules/missing.nix
index 1111111..2222222 100644
--- a/modules/missing.nix
+++ b/modules/missing.nix
@@ -1 +1 @@
-old
+new
"""


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    print("$ " + " ".join(command))
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def ok(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"command failed: {result.returncode}")


def write_fixture(root: Path) -> None:
    (root / "modules").mkdir(parents=True)
    (root / ".agentix" / "proposals").mkdir(parents=True)

    (root / ".gitignore").write_text(".agentix/audit.jsonl\n", encoding="utf-8")
    (root / "flake.nix").write_text("{ outputs = { self }: {}; }\n", encoding="utf-8")
    (root / ".agentix" / "policy.json").write_text("{}\n", encoding="utf-8")
    (root / "modules" / "agentic-base.nix").write_text(AGENTIC_BASE, encoding="utf-8")
    (root / "modules" / "devtools.nix").write_text(MODULE, encoding="utf-8")
    (root / "modules" / "fun.nix").write_text(MODULE, encoding="utf-8")
    (root / ".agentix" / "proposals" / "clean.patch").write_text(CLEAN_PATCH, encoding="utf-8")
    (root / ".agentix" / "proposals" / "stale.patch").write_text(STALE_PATCH, encoding="utf-8")
    (root / ".agentix" / "audit.jsonl").write_text(
        "\n".join([
            json.dumps({"action": "doctor", "result": "passed"}),
            json.dumps({"action": "apply", "result": "stale"}),
            json.dumps({"action": "proposals_clean", "result": "ok_stale"}),
        ]) + "\n",
        encoding="utf-8",
    )


def run_self_test(agentix_command: str | None = None) -> int:
    command = agentix_command or shutil.which("agentix") or sys.argv[0]

    with tempfile.TemporaryDirectory(prefix="agentix-self-test-") as tmp:
        root = Path(tmp) / "nixos-config"
        root.mkdir()

        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Agentix Self Test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "agentix-self-test@example.test"], cwd=root, check=True)

        write_fixture(root)

        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial self-test fixture"], cwd=root, check=True, capture_output=True)

        print("Agentix Self Test")
        print(f"Fixture: {root}")
        print()

        result = run([command, "proposals", "list", "--path", ".", "--json"], cwd=root)
        ok(result)
        proposals = json.loads(result.stdout)
        statuses = {proposal["name"]: proposal["status"] for proposal in proposals}
        assert statuses["clean.patch"] == "clean"
        assert statuses["stale.patch"] == "stale"
        print("OK proposals list --json")

        result = run([command, "proposals", "clean", "--path", ".", "--stale", "--yes", "--json"], cwd=root)
        ok(result)
        payload = json.loads(result.stdout)
        assert payload["deleted"] == 1
        assert payload["mode"] == "stale"
        assert (root / ".agentix" / "proposals" / "clean.patch").exists()
        assert not (root / ".agentix" / "proposals" / "stale.patch").exists()
        print("OK proposals clean --stale --json")

        result = run([command, "audit", "tail", "--path", ".", "--lines", "2", "--json"], cwd=root)
        ok(result)
        events = json.loads(result.stdout)
        assert len(events) == 2
        assert events[0]["action"] == "proposals_list"
        assert events[1]["action"] == "proposals_clean"
        print("OK audit tail --json")

        result = run([command, "audit", "summary", "--path", ".", "--json"], cwd=root)
        ok(result)
        summary = json.loads(result.stdout)
        assert summary["total"] >= 3
        assert summary["actions"]["doctor"] >= 1
        assert summary["results"]["stale"] >= 1
        print("OK audit summary --json")

        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Self-test: cleanup stale proposal"],
            cwd=root,
            check=True,
            capture_output=True,
        )

        fake_agentix = Path(tmp) / "fake-agentix-smoke"
        fake_agentix.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' '# smoke worktree work' > modules/smoke-test.nix\n"
            "git add modules/smoke-test.nix\n",
            encoding="utf-8",
        )
        fake_agentix.chmod(0o755)

        result = run([command, "controller-plan", "--path", ".", "--json"], cwd=root)
        ok(result)
        plan = json.loads(result.stdout)
        assert plan["action"] == "controller_plan"
        assert plan["source_workspace_must_remain_untouched"] is True
        print("OK controller-plan --json")

        result = run(
            [
                command,
                "controller-run",
                "create module smoke-test with template packages",
                "--path",
                ".",
            ],
            cwd=root,
        )
        ok(result)
        dry = json.loads(result.stdout)
        assert dry["action"] == "controller_run"
        assert dry["mode"] == "dry_run"
        assert dry["execute"] is False
        assert dry["passed"] is True
        assert dry["source_modified"] is False
        print("OK controller-run dry-run")

        result = run(
            [
                command,
                "controller-run",
                "create module smoke-test with template packages",
                "--path",
                ".",
                "--agentix-command",
                str(fake_agentix),
                "--execute",
            ],
            cwd=root,
        )
        ok(result)
        executed = json.loads(result.stdout)
        assert executed["mode"] == "execute"
        assert executed["execute"] is True
        assert executed["passed"] is True
        assert executed["source_modified"] is False
        assert executed["proposal_saved"] is not None
        assert Path(executed["proposal_saved"]).exists()
        assert not (root / "modules" / "smoke-test.nix").exists()
        print("OK controller-run --execute")

    print()
    print("Self-test passed.")
    print("No sudo, no rebuild, no system switch.")
    return 0

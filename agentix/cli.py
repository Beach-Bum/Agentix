import argparse
import contextlib
import difflib
import io
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agentix.audit_log import audit
from agentix.policy import check_policy, policy_summary
from agentix.init import init_workspace
from agentix.nixos import add_package_to_module
from agentix.status import collect_status, print_status
from agentix.preflight import nixos_preflight, workspace_preflight
from agentix.proposals import list_proposals, clean_proposals, list_stale_proposals, prune_stale_proposals, proposal_status
from agentix.audit_view import print_audit_tail
from agentix.audit_summary import print_audit_summary
from agentix.switch_plan import print_switch_plan
from agentix.public_check import print_public_check
from agentix.public_export import export_public_repo
from agentix.workflows import package_flow, apply_verify_flow
from agentix.modules import print_modules, print_module_explanation, create_module_patch
from agentix.doctor import run_doctor
from agentix.goal import run_goal
from agentix.self_test import run_self_test
from agentix.worktree_run import DEFAULT_GOAL_TIMEOUT_SECONDS, worktree_run
from agentix.agent_loop import agent_loop
from agentix.controller_plan import print_controller_plan
from agentix.controller_run import controller_run


LANGUAGE_MARKERS = {
    "rust": ["Cargo.toml"],
    "python": ["pyproject.toml", "requirements.txt", "setup.py"],
    "node": ["package.json"],
    "go": ["go.mod"],
    "nix": ["flake.nix", "shell.nix", "default.nix"],
}


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def detect_languages(path: Path) -> list[str]:
    detected = []

    for language, markers in LANGUAGE_MARKERS.items():
        for marker in markers:
            if (path / marker).exists():
                detected.append(language)
                break

    return detected


def inspect_path(path: Path) -> dict:
    files = [p.name for p in path.iterdir()] if path.exists() and path.is_dir() else []

    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "has_flake": (path / "flake.nix").exists(),
        "has_shell_nix": (path / "shell.nix").exists(),
        "has_default_nix": (path / "default.nix").exists(),
        "has_configuration_nix": (path / "configuration.nix").exists(),
        "has_home_manager": (path / "home.nix").exists(),
        "detected_languages": detect_languages(path),
        "detected_files": sorted(files),
    }


def rust_flake_template(project_name: str) -> str:
    safe_name = project_name.replace("_", "-")

    return f'''{{
  description = "{safe_name} development environment";

  inputs = {{
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  }};

  outputs = {{ self, nixpkgs }}:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {{
        inherit system;
      }};
    in
    {{
      devShells.${{system}}.default = pkgs.mkShell {{
        packages = with pkgs; [
          rustc
          cargo
          rustfmt
          clippy
          rust-analyzer
          pkg-config
        ];
      }};
    }};
}}
'''


def new_file_diff(filename: str, content: str) -> str:
    return "".join(
        difflib.unified_diff(
            [],
            content.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/{filename}",
        )
    )


def propose_rust_devshell(path: Path) -> tuple[int, str]:
    flake_path = path / "flake.nix"

    if flake_path.exists():
        return (
            1,
            "Refusing to modify an existing flake.nix in this first prototype.\n"
            "Next version will support safe patching of existing flakes.\n",
        )

    new_content = rust_flake_template(path.name)
    diff = new_file_diff("flake.nix", new_content)

    explanation = """Proposal: create a Rust Nix dev shell.

What this would do:
- create flake.nix
- add rustc, cargo, rustfmt, clippy, rust-analyzer, pkg-config
- avoid system-level changes
- avoid sudo
- avoid touching files outside this workspace

This is only a proposal. No files were changed.
"""

    return 0, explanation + "\n" + diff


def run_command(command: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd)
    return completed.returncode



def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    init_workspace(path)
    audit(path, {
        "action": "init",
        "result": "ok",
        "path": str(path),
    })

    print(f"Initialized Agentix workspace: {path}")
    print("Created:")
    print("- .agentix/policy.json")
    print("- .agentix/audit.jsonl")
    print("- .agentix/proposals/")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    result = inspect_path(path)
    print(json.dumps(result, indent=2))

    audit(path, {
        "action": "inspect",
        "result": "ok",
        "path": str(path),
    })

    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    request_text = " ".join(args.request)
    request = request_text.lower()

    findings = check_policy(request_text)
    denied_findings = [finding for finding in findings if finding.level == "deny"]

    if denied_findings:
        print("Policy denied this request.")
        print()
        for finding in denied_findings:
            print(f"DENY: {finding.rule}: {finding.message}")

        audit(path, {
            "action": "propose",
            "request": request_text,
            "result": "policy_denied",
            "policy_violations": [finding.rule for finding in denied_findings],
        })

        return 1

    info = inspect_path(path)

    if not info["exists"]:
        print(f"Path does not exist: {path}")
        return 1

    if "rust" in request or "rust" in info["detected_languages"]:
        code, output = propose_rust_devshell(path)
        print(output)

        if code == 0 and args.save:
            proposal_dir = path / ".agentix" / "proposals"
            proposal_dir.mkdir(parents=True, exist_ok=True)
            proposal_path = proposal_dir / f"{now_id()}-rust-devshell.patch"

            # Save only the diff part, not the explanation.
            diff_start = output.find("--- ")
            proposal_path.write_text(output[diff_start:], encoding="utf-8")

            print()
            print(f"Saved proposal: {proposal_path}")

            audit(path, {
                "action": "propose",
                "request": " ".join(args.request),
                "proposal": str(proposal_path),
                "result": "saved",
                "approval_required": True,
                "files_changed": ["flake.nix"],
            })
        else:
            audit(path, {
                "action": "propose",
                "request": " ".join(args.request),
                "result": "printed",
                "approval_required": True,
                "files_changed": ["flake.nix"] if code == 0 else [],
            })

        return code

    print("No proposal available yet.")
    print()
    print("Current prototype supports:")
    print("- Rust project without existing flake.nix")

    audit(path, {
        "action": "propose",
        "request": " ".join(args.request),
        "result": "unsupported",
    })

    return 1


def cmd_apply(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    patch_path = Path(args.patch).expanduser().resolve()

    ok, problems = workspace_preflight(path, allow_dirty=args.allow_dirty)
    if not ok:
        print("Preflight failed. Refusing to apply patch.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    if not patch_path.exists():
        print(f"Patch does not exist: {patch_path}")
        return 1

    precheck_code = run_command(["git", "apply", "--check", str(patch_path)], cwd=path)
    if precheck_code != 0:
        print("Patch is stale or does not apply cleanly. Not applying.")
        audit(path, {
            "action": "apply",
            "patch": str(patch_path),
            "result": "stale",
        })
        return precheck_code

    print(f"Patch to apply: {patch_path}")
    print()
    print(patch_path.read_text(encoding="utf-8"))

    if not args.yes:
        answer = input("Apply this patch? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not applying.")
            audit(path, {
                "action": "apply",
                "patch": str(patch_path),
                "result": "declined",
            })
            return 1

    check_code = run_command(["git", "apply", "--check", str(patch_path)], cwd=path)
    if check_code != 0:
        print("Patch check failed. Not applying.")
        audit(path, {
            "action": "apply",
            "patch": str(patch_path),
            "result": "patch_check_failed",
        })
        return check_code

    apply_code = run_command(["git", "apply", str(patch_path)], cwd=path)
    audit(path, {
        "action": "apply",
        "patch": str(patch_path),
        "result": "applied" if apply_code == 0 else "failed",
        "approval_required": True,
    })

    return apply_code


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not (path / "flake.nix").exists():
        print("No flake.nix found. Nothing to check yet.")
        return 1

    code = run_command(["nix", "flake", "check"], cwd=path)

    audit(path, {
        "action": "check",
        "command": "nix flake check",
        "result": "passed" if code == 0 else "failed",
    })

    return code



def cmd_policy(args: argparse.Namespace) -> int:
    print(policy_summary())
    return 0


def cmd_policy_check(args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    findings = check_policy(text)

    if not findings:
        print("Policy result: allowed")
        return 0

    denied = False

    for finding in findings:
        print(f"{finding.level.upper()}: {finding.rule}: {finding.message}")
        if finding.level == "deny":
            denied = True

    return 1 if denied else 0



def cmd_package(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    package = args.package

    ok, problems = nixos_preflight(path, allow_dirty=args.allow_dirty)
    if not ok:
        print("Preflight failed. Refusing to propose package change.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    request_text = f"add package {package}"
    findings = check_policy(request_text)
    denied_findings = [finding for finding in findings if finding.level == "deny"]

    if denied_findings:
        print("Policy denied this request.")
        for finding in denied_findings:
            print(f"DENY: {finding.rule}: {finding.message}")
        return 1

    try:
        diff, selected_module = add_package_to_module(path, package, args.module)
    except Exception as exc:
        print(f"Could not create package proposal: {exc}")
        return 1

    explanation = f"""Proposal: add package `{package}` to module `{selected_module}`.

What this would do:
- edit only the selected NixOS module
- add `{package}` to environment.systemPackages
- avoid /etc/nixos
- avoid sudo
- require approval before applying

This is only a proposal. No files were changed.
"""

    print(explanation)
    print(diff)

    if args.save:
        proposal_dir = path / ".agentix" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{now_id()}-add-package-{package}.patch"
        proposal_path.write_text(diff, encoding="utf-8")

        print()
        print(f"Saved proposal: {proposal_path}")

        audit(path, {
            "action": "propose_package",
            "package": package,
            "module": selected_module,
            "requested_module": args.module,
            "proposal": str(proposal_path),
            "result": "saved",
            "approval_required": True,
            "files_changed": [f"module:{selected_module}"],
        })
    else:
        audit(path, {
            "action": "propose_package",
            "package": package,
            "module": selected_module,
            "requested_module": args.module,
            "result": "printed",
            "approval_required": True,
            "files_changed": [f"module:{selected_module}"],
        })

    return 0



def cmd_nixos_check(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    host = args.host

    if not (path / "flake.nix").exists():
        print("No flake.nix found.")
        return 1

    command = [
        "nix",
        "build",
        "--no-link",
        f".#nixosConfigurations.{host}.config.system.build.toplevel",
    ]

    code = run_command(command, cwd=path)

    audit(path, {
        "action": "nixos_check",
        "host": host,
        "command": " ".join(command),
        "result": "passed" if code == 0 else "failed",
        "requires_sudo": False,
        "switched_system": False,
    })

    return code



def cmd_vm_check(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    host = args.host

    if not (path / "flake.nix").exists():
        print("No flake.nix found.")
        return 1

    command = [
        "nixos-rebuild",
        "build-vm",
        "--flake",
        f".#{host}",
    ]

    code = run_command(command, cwd=path)

    audit(path, {
        "action": "vm_check",
        "host": host,
        "command": " ".join(command),
        "result": "passed" if code == 0 else "failed",
        "requires_sudo": False,
        "switched_system": False,
        "built_vm": code == 0,
    })

    return code



def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    status = collect_status(path)
    print_status(status)

    audit(path, {
        "action": "status",
        "result": "ok",
        "path": str(path),
    })

    return 0



def cmd_doctor(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    code = run_doctor(path)

    audit(path, {
        "action": "doctor",
        "result": "passed" if code == 0 else "failed",
        "path": str(path),
    })

    return code



def cmd_proposals_list(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    proposals = list_proposals(path)

    rows = [
        {
            "name": proposal.name,
            "path": str(proposal),
            "status": proposal_status(path, proposal),
        }
        for proposal in proposals
    ]

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        audit(path, {
            "action": "proposals_list",
            "result": "ok_json",
            "path": str(path),
            "count": len(proposals),
        })
        return 0

    if not proposals:
        print("No saved proposals.")
        audit(path, {
            "action": "proposals_list",
            "result": "empty",
            "path": str(path),
        })
        return 0

    print("Saved proposals:")
    for row in rows:
        print(f"- [{row['status']}] {row['name']}")

    audit(path, {
        "action": "proposals_list",
        "result": "ok",
        "path": str(path),
        "count": len(proposals),
    })

    return 0


def cmd_proposals_clean(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if args.stale:
        stale = list_stale_proposals(path)

        if not stale:
            if args.json:
                print(json.dumps({
                    "action": "proposals_clean",
                    "mode": "stale",
                    "deleted": 0,
                }, indent=2, sort_keys=True))
            else:
                print("No stale proposals to clean.")
            audit(path, {
                "action": "proposals_clean",
                "result": "empty_stale",
                "count": 0,
            })
            return 0

        if not args.json:
            print("Stale proposals to remove:")
            for proposal in stale:
                print(f"- {proposal.name}")

        if not args.yes:
            answer = input("Delete these stale proposals? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Not deleting.")
                return 1

        count = prune_stale_proposals(path)

        audit(path, {
            "action": "proposals_clean",
            "result": "ok_stale",
            "count": count,
        })

        if args.json:
            print(json.dumps({
                "action": "proposals_clean",
                "mode": "stale",
                "deleted": count,
            }, indent=2, sort_keys=True))
        else:
            print(f"Deleted {count} stale proposal(s).")
        return 0

    proposals = list_proposals(path)

    if not proposals:
        if args.json:
            print(json.dumps({
                "action": "proposals_clean",
                "mode": "all",
                "deleted": 0,
            }, indent=2, sort_keys=True))
        else:
            print("No saved proposals to clean.")
        return 0

    if not args.json:
        print("Proposals to remove:")
        for proposal in proposals:
            print(f"- {proposal}")

    if not args.yes:
        answer = input("Delete these saved proposals? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not deleting.")
            return 1

    count = clean_proposals(path)

    audit(path, {
        "action": "proposals_clean",
        "result": "ok",
        "count": count,
    })

    if args.json:
        print(json.dumps({
            "action": "proposals_clean",
            "mode": "all",
            "deleted": count,
        }, indent=2, sort_keys=True))
    else:
        print(f"Deleted {count} proposal(s).")
    return 0


def cmd_proposals_prune_stale(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    stale = list_stale_proposals(path)

    if not stale:
        if args.json:
            print(json.dumps({
                "action": "proposals_prune_stale",
                "deleted": 0,
            }, indent=2, sort_keys=True))
        else:
            print("No stale proposals found.")
        audit(path, {
            "action": "proposals_prune_stale",
            "result": "empty",
            "path": str(path),
        })
        return 0

    if not args.json:
        print("Stale proposals:")
        for proposal in stale:
            print(f"- {proposal.name}")

    if not args.yes:
        answer = input("Delete stale proposals? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not deleting.")
            return 1

    count = prune_stale_proposals(path)

    audit(path, {
        "action": "proposals_prune_stale",
        "result": "deleted",
        "path": str(path),
        "count": count,
    })

    if args.json:
        print(json.dumps({
            "action": "proposals_prune_stale",
            "deleted": count,
        }, indent=2, sort_keys=True))
    else:
        print(f"Deleted {count} stale proposal(s).")
    return 0


def _read_audit_events(path: Path) -> list[dict]:
    audit_path = path / ".agentix" / "audit.jsonl"
    if not audit_path.exists():
        return []

    events: list[dict] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = {
                "raw": line,
                "parse_error": True,
            }
        events.append(event)

    return events


def _audit_summary(events: list[dict]) -> dict:
    actions: dict[str, int] = {}
    results: dict[str, int] = {}

    for event in events:
        action = str(event.get("action", "unknown"))
        result = str(event.get("result", "unknown"))
        actions[action] = actions.get(action, 0) + 1
        results[result] = results.get(result, 0) + 1

    return {
        "total": len(events),
        "actions": actions,
        "results": results,
    }


def cmd_audit_tail(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if args.json:
        events = _read_audit_events(path)
        if args.lines is not None and args.lines >= 0:
            events = events[-args.lines:]
        print(json.dumps(events, indent=2, sort_keys=True))
        return 0

    return print_audit_tail(path, args.lines)


def cmd_audit_summary(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if args.json:
        events = _read_audit_events(path)
        summary = _audit_summary(events)
        summary["path"] = str(path)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    return print_audit_summary(path)


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    host = args.host

    if args.json:
        result = {
            "action": "verify",
            "path": str(path),
            "host": host,
            "requires_sudo": False,
            "switched_system": False,
            "passed": False,
            "steps": [],
        }

        doctor_result = _run_doctor_captured(path)
        result["steps"].append({
            "name": "doctor",
            **doctor_result,
        })

        if doctor_result["returncode"] != 0:
            result["result"] = "doctor_failed"
            print(json.dumps(result, indent=2, sort_keys=True))
            audit(path, {
                "action": "verify",
                "result": "doctor_failed",
                "host": host,
                "switched_system": False,
                "json": True,
            })
            return doctor_result["returncode"]

        nixos_command = [
            "nix",
            "build",
            "--no-link",
            f".#nixosConfigurations.{host}.config.system.build.toplevel",
        ]
        nixos_result = _run_command_captured(nixos_command, cwd=path)
        result["steps"].append({
            "name": "nixos-check",
            **nixos_result,
        })

        if nixos_result["returncode"] != 0:
            result["result"] = "nixos_check_failed"
            print(json.dumps(result, indent=2, sort_keys=True))
            audit(path, {
                "action": "verify",
                "result": "nixos_check_failed",
                "host": host,
                "command": " ".join(nixos_command),
                "switched_system": False,
                "json": True,
            })
            return nixos_result["returncode"]

        vm_command = [
            "nixos-rebuild",
            "build-vm",
            "--flake",
            f".#{host}",
        ]
        vm_result = _run_command_captured(vm_command, cwd=path)
        result["steps"].append({
            "name": "vm-check",
            **vm_result,
        })

        if vm_result["returncode"] != 0:
            result["result"] = "vm_check_failed"
            print(json.dumps(result, indent=2, sort_keys=True))
            audit(path, {
                "action": "verify",
                "result": "vm_check_failed",
                "host": host,
                "command": " ".join(vm_command),
                "switched_system": False,
                "json": True,
            })
            return vm_result["returncode"]

        result["passed"] = True
        result["result"] = "passed"
        result["next_safe_command"] = "cd ~/nixos-config && rebuild-nixos"

        audit(path, {
            "action": "verify",
            "result": "passed",
            "host": host,
            "requires_sudo": False,
            "switched_system": False,
            "json": True,
        })

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("Agentix Verify")
    print()
    print("Step 1: doctor")
    doctor_code = run_doctor(path)
    if doctor_code != 0:
        audit(path, {
            "action": "verify",
            "result": "doctor_failed",
            "host": host,
            "switched_system": False,
        })
        return doctor_code

    print()
    print("Step 2: nixos-check")
    nixos_command = [
        "nix",
        "build",
        "--no-link",
        f".#nixosConfigurations.{host}.config.system.build.toplevel",
    ]
    nixos_code = run_command(nixos_command, cwd=path)
    if nixos_code != 0:
        audit(path, {
            "action": "verify",
            "result": "nixos_check_failed",
            "host": host,
            "command": " ".join(nixos_command),
            "switched_system": False,
        })
        return nixos_code

    print()
    print("Step 3: vm-check")
    vm_command = [
        "nixos-rebuild",
        "build-vm",
        "--flake",
        f".#{host}",
    ]
    vm_code = run_command(vm_command, cwd=path)
    if vm_code != 0:
        audit(path, {
            "action": "verify",
            "result": "vm_check_failed",
            "host": host,
            "command": " ".join(vm_command),
            "switched_system": False,
        })
        return vm_code

    audit(path, {
        "action": "verify",
        "result": "passed",
        "host": host,
        "requires_sudo": False,
        "switched_system": False,
    })

    print()
    print("Verify result: passed")
    print()
    print("Safe to run human-controlled rebuild:")
    print("  cd ~/nixos-config && rebuild-nixos")

    return 0



def cmd_switch_plan(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    host = args.host

    print_switch_plan(path, host)

    audit(path, {
        "action": "switch_plan",
        "result": "printed",
        "host": host,
        "requires_sudo": False,
        "switched_system": False,
    })

    return 0



def cmd_public_check(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    return print_public_check(path)



def cmd_export_public(args: argparse.Namespace) -> int:
    source = Path(args.path).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()

    if not source.exists():
        print(f"Source path does not exist: {source}")
        return 1

    if dest.exists() and not args.yes:
        print(f"Destination already exists: {dest}")
        print("Pass --yes to overwrite.")
        return 1

    export_public_repo(source, dest, overwrite=args.yes)

    print("Public export created.")
    print(f"Source: {source}")
    print(f"Destination: {dest}")
    print()
    print("Next checks:")
    print(f"  agentix public-check --path {dest}")
    print(f"  cd {dest} && git init && git status")

    return 0



def cmd_modules_list(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    code = print_modules(path)

    audit(path, {
        "action": "modules_list",
        "result": "ok" if code == 0 else "failed",
        "path": str(path),
    })

    return code



def cmd_modules_explain(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()

    if not path.exists():
        print(f"Path does not exist: {path}")
        return 1

    code = print_module_explanation(path, args.module)

    audit(path, {
        "action": "modules_explain",
        "result": "ok" if code == 0 else "failed",
        "path": str(path),
        "module": args.module,
    })

    return code



def cmd_modules_create(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    name = args.name

    ok, problems = nixos_preflight(path, allow_dirty=args.allow_dirty)
    if not ok:
        print("Preflight failed. Refusing to create module proposal.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    try:
        diff = create_module_patch(path, name, args.template)
    except Exception as exc:
        print(f"Could not create module proposal: {exc}")
        return 1

    print(f"Proposal: create NixOS module `{name}` using template `{args.template}`.")
    print()
    print("What this would do:")
    print(f"- create modules/{name}.nix")
    print("- import it from modules/agentic-base.nix")
    print("- avoid /etc/nixos")
    print("- avoid sudo")
    print("- require approval before applying")
    print()
    print("This is only a proposal. No files were changed.")
    print()
    print(diff)

    if args.save:
        proposal_dir = path / ".agentix" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{now_id()}-create-module-{name}.patch"
        proposal_path.write_text(diff, encoding="utf-8")

        print()
        print(f"Saved proposal: {proposal_path}")

        audit(path, {
            "action": "modules_create",
            "module": name,
            "template": args.template,
            "proposal": str(proposal_path),
            "result": "saved",
            "approval_required": True,
            "files_changed": ["modules/agentic-base.nix", f"modules/{name}.nix"],
        })
    else:
        audit(path, {
            "action": "modules_create",
            "module": name,
            "template": args.template,
            "result": "printed",
            "approval_required": True,
            "files_changed": ["modules/agentic-base.nix", f"modules/{name}.nix"],
        })

    return 0



def cmd_package_flow(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    return package_flow(
        path,
        args.package,
        args.module,
        yes=args.yes,
        allow_dirty=args.allow_dirty,
    )



def cmd_apply_verify(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    patch_path = Path(args.patch).expanduser().resolve()

    return apply_verify_flow(
        path=path,
        patch_path=patch_path,
        host=args.host,
        yes=args.yes,
        allow_dirty=args.allow_dirty,
    )



def cmd_controller_run(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    goal = " ".join(args.goal)
    return controller_run(
        path=path,
        goal=goal,
        host=args.host,
        module=args.module,
        agentix_command=args.agentix_command,
        keep=args.keep,
        execute=args.execute,
        timeout=args.timeout,
    )


def cmd_controller_plan(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    return print_controller_plan(path, json_output=args.json)


def cmd_agent_loop(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    goal = " ".join(args.goal)
    return agent_loop(
        path=path,
        goal=goal,
        host=args.host,
        module=args.module,
        agentix_command=args.agentix_command,
        keep=args.keep,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )


def cmd_worktree_run(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    goal = " ".join(args.goal)
    return worktree_run(
        path=path,
        goal=goal,
        host=args.host,
        module=args.module,
        agentix_command=args.agentix_command,
        keep=args.keep,
        save_proposal_patch=args.save_proposal,
        json_output=args.json,
        timeout=args.timeout,
    )


def cmd_self_test(args: argparse.Namespace) -> int:
    return run_self_test(agentix_command=args.agentix_command)


def cmd_run_goal(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    goal = " ".join(args.goal)

    return run_goal(
        path=path,
        goal=goal,
        host=args.host,
        module=args.module,
        yes=args.yes,
        dry_run=args.dry_run,
        allow_dirty=args.allow_dirty,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentix",
        description="Agentic control layer for NixOS and Nix flakes",
    )

    subcommands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subcommands.add_parser("inspect", help="Inspect a project or NixOS config directory")
    inspect_parser.add_argument("path", nargs="?", default=".")
    inspect_parser.set_defaults(func=cmd_inspect)

    init_parser = subcommands.add_parser("init", help="Initialize an Agentix workspace")
    init_parser.add_argument("path", nargs="?", default=".")
    init_parser.set_defaults(func=cmd_init)


    propose_parser = subcommands.add_parser("propose", help="Propose a safe Nix patch")
    propose_parser.add_argument("request", nargs="+")
    propose_parser.add_argument("--path", default=".")
    propose_parser.add_argument("--save", action="store_true")
    propose_parser.set_defaults(func=cmd_propose)

    apply_parser = subcommands.add_parser("apply", help="Apply a saved patch after approval")
    apply_parser.add_argument("patch")
    apply_parser.add_argument("--path", default=".")
    apply_parser.add_argument("--yes", action="store_true")
    apply_parser.add_argument("--allow-dirty", action="store_true")
    apply_parser.set_defaults(func=cmd_apply)

    apply_verify_parser = subcommands.add_parser(
        "apply-verify",
        help="Apply a saved patch and run Agentix verification",
        description="Apply a saved patch and run Agentix verification",
    )
    apply_verify_parser.add_argument("patch")
    apply_verify_parser.add_argument("--path", default=".")
    apply_verify_parser.add_argument("--host", default="nixos")
    apply_verify_parser.add_argument("--yes", action="store_true")
    apply_verify_parser.add_argument("--allow-dirty", action="store_true")
    apply_verify_parser.set_defaults(func=cmd_apply_verify)


    check_parser = subcommands.add_parser("check", help="Run safe checks for a Nix flake")
    check_parser.add_argument("--path", default=".")
    check_parser.set_defaults(func=cmd_check)

    policy_parser = subcommands.add_parser("policy", help="Show Agentix policy")
    policy_parser.set_defaults(func=cmd_policy)

    policy_check_parser = subcommands.add_parser("policy-check", help="Check text against Agentix policy")
    policy_check_parser.add_argument("text", nargs="+")
    policy_check_parser.set_defaults(func=cmd_policy_check)

    package_parser = subcommands.add_parser("package", help="Propose adding a package to agentic-base.nix")
    package_parser.add_argument("package")
    package_parser.add_argument("--path", default=".")
    package_parser.add_argument("--save", action="store_true")
    package_parser.add_argument("--module", default="devtools", choices=["auto", "devtools", "fun", "agentic-base"])
    package_parser.add_argument("--allow-dirty", action="store_true")
    package_parser.set_defaults(func=cmd_package)

    package_flow_parser = subcommands.add_parser(
        "package-flow",
        help="Run propose, approve, apply, and verify for a package change",
        description="Run propose, approve, apply, and verify for a package change",
    )
    package_flow_parser.add_argument("package")
    package_flow_parser.add_argument("--path", default=".")
    package_flow_parser.add_argument("--module", default="auto", choices=["auto", "devtools", "fun", "agentic-base"])
    package_flow_parser.add_argument("--yes", action="store_true", help="Apply without interactive confirmation")
    package_flow_parser.add_argument("--allow-dirty", action="store_true")
    package_flow_parser.set_defaults(func=cmd_package_flow)


    nixos_check_parser = subcommands.add_parser("nixos-check", help="Build-check a NixOS flake host without switching")
    nixos_check_parser.add_argument("--path", default=".")
    nixos_check_parser.add_argument("--host", default="nixos")
    nixos_check_parser.set_defaults(func=cmd_nixos_check)

    vm_check_parser = subcommands.add_parser("vm-check", help="Build a NixOS VM from the flake without switching")
    vm_check_parser.add_argument("--path", default=".")
    vm_check_parser.add_argument("--host", default="nixos")
    vm_check_parser.set_defaults(func=cmd_vm_check)

    status_parser = subcommands.add_parser("status", help="Show Agentix workspace status")
    status_parser.add_argument("--path", default=".")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subcommands.add_parser("doctor", help="Run Agentix preflight checks")
    doctor_parser.add_argument("--path", default=".")
    doctor_parser.set_defaults(func=cmd_doctor)

    proposals_parser = subcommands.add_parser("proposals", help="Manage saved Agentix proposals")
    proposals_subcommands = proposals_parser.add_subparsers(dest="proposal_command", required=True)

    proposals_list_parser = proposals_subcommands.add_parser("list", help="List saved proposal patches")
    proposals_list_parser.add_argument("--path", default=".")
    proposals_list_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    proposals_list_parser.set_defaults(func=cmd_proposals_list)

    proposals_clean_parser = proposals_subcommands.add_parser("clean", help="Delete saved proposal patches")
    proposals_clean_parser.add_argument("--path", default=".")
    proposals_clean_parser.add_argument("--yes", action="store_true")
    proposals_clean_parser.add_argument("--stale", action="store_true", help="Delete only stale proposals")
    proposals_clean_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    proposals_clean_parser.set_defaults(func=cmd_proposals_clean)

    proposals_prune_parser = proposals_subcommands.add_parser("prune-stale", help="Delete saved patches that no longer apply cleanly")
    proposals_prune_parser.add_argument("--path", default=".")
    proposals_prune_parser.add_argument("--yes", action="store_true")
    proposals_prune_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    proposals_prune_parser.set_defaults(func=cmd_proposals_prune_stale)


    audit_parser = subcommands.add_parser("audit", help="View Agentix audit log")
    audit_subcommands = audit_parser.add_subparsers(dest="audit_command", required=True)

    audit_tail_parser = audit_subcommands.add_parser("tail", help="Show recent audit events")
    audit_tail_parser.add_argument("--path", default=".")
    audit_tail_parser.add_argument("--lines", type=int, default=10)
    audit_tail_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    audit_tail_parser.set_defaults(func=cmd_audit_tail)

    audit_summary_parser = audit_subcommands.add_parser("summary", help="Summarize Agentix audit history")
    audit_summary_parser.add_argument("--path", default=".")
    audit_summary_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    audit_summary_parser.set_defaults(func=cmd_audit_summary)

    verify_parser = subcommands.add_parser(
        "verify",
        help="Run doctor, NixOS build check, and VM build check",
        description="Run doctor, NixOS build check, and VM build check",
    )
    verify_parser.add_argument("--path", default=".")
    verify_parser.add_argument("--host", default="nixos")
    verify_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    verify_parser.set_defaults(func=cmd_verify)

    switch_plan_parser = subcommands.add_parser(
        "switch-plan",
        help="Print the human-controlled NixOS switch plan",
        description="Print the human-controlled NixOS switch plan",
    )
    switch_plan_parser.add_argument("--path", default=".")
    switch_plan_parser.add_argument("--host", default="nixos")
    switch_plan_parser.set_defaults(func=cmd_switch_plan)

    public_check_parser = subcommands.add_parser(
        "public-check",
        help="Check whether a repo is safe to publish publicly",
        description="Check whether a repo is safe to publish publicly",
    )
    public_check_parser.add_argument("--path", default=".")
    public_check_parser.set_defaults(func=cmd_public_check)

    export_public_parser = subcommands.add_parser(
        "export-public",
        help="Create a sanitized public export of a private repo",
        description="Create a sanitized public export of a private repo",
    )
    export_public_parser.add_argument("--path", default=".")
    export_public_parser.add_argument("--dest", required=True)
    export_public_parser.add_argument("--yes", action="store_true", help="Overwrite destination if it exists")
    export_public_parser.set_defaults(func=cmd_export_public)

    modules_parser = subcommands.add_parser(
        "modules",
        help="Inspect NixOS modules",
        description="Inspect NixOS modules",
    )
    modules_subcommands = modules_parser.add_subparsers(dest="modules_command", required=True)

    modules_list_parser = modules_subcommands.add_parser(
        "list",
        help="List NixOS modules",
        description="List NixOS modules",
    )
    modules_list_parser.add_argument("--path", default=".")
    modules_list_parser.set_defaults(func=cmd_modules_list)

    modules_explain_parser = modules_subcommands.add_parser(
        "explain",
        help="Explain a NixOS module",
        description="Explain a NixOS module",
    )
    modules_explain_parser.add_argument("module")
    modules_explain_parser.add_argument("--path", default=".")
    modules_explain_parser.set_defaults(func=cmd_modules_explain)

    modules_create_parser = modules_subcommands.add_parser(
        "create",
        help="Propose creating a new NixOS module",
        description="Propose creating a new NixOS module",
    )
    modules_create_parser.add_argument("name")
    modules_create_parser.add_argument("--path", default=".")
    modules_create_parser.add_argument("--save", action="store_true")
    modules_create_parser.add_argument("--template", default="empty", choices=["empty", "packages", "services"])
    modules_create_parser.add_argument("--allow-dirty", action="store_true")
    modules_create_parser.set_defaults(func=cmd_modules_create)

















    goal_parser = subcommands.add_parser(
        "run",
        help="Run a supported high-level Agentix goal",
        description="Run a supported high-level Agentix goal",
    )
    goal_parser.add_argument("goal", nargs="+")
    goal_parser.add_argument("--path", default=".")
    goal_parser.add_argument("--host", default="nixos")
    goal_parser.add_argument("--module", default="auto", choices=["auto", "devtools", "fun", "agentic-base"])
    goal_parser.add_argument("--yes", action="store_true", help="Apply without interactive confirmation")
    goal_parser.add_argument("--dry-run", action="store_true", help="Parse and print the plan without changing files")
    goal_parser.add_argument("--allow-dirty", action="store_true")
    goal_parser.set_defaults(func=cmd_run_goal)

    controller_run_parser = subcommands.add_parser(
        "controller-run",
        help="Run a controller-safe goal plan, optionally executing only in a sandbox",
        description="Run a controller-safe goal plan, optionally executing only in a sandbox",
    )
    controller_run_parser.add_argument("goal", nargs="+")
    controller_run_parser.add_argument("--path", default=".")
    controller_run_parser.add_argument("--host", default="nixos")
    controller_run_parser.add_argument("--module", default="auto", choices=["auto", "devtools", "fun", "agentic-base"])
    controller_run_parser.add_argument("--agentix-command", default="agentix")
    controller_run_parser.add_argument("--keep", action="store_true", help="Keep the temporary worktree for manual inspection when executing")
    controller_run_parser.add_argument("--execute", action="store_true", help="Execute the goal only inside a temporary worktree and save a proposal")
    controller_run_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GOAL_TIMEOUT_SECONDS,
        help=f"Seconds to wait for the inner goal subprocess before killing it (default: {DEFAULT_GOAL_TIMEOUT_SECONDS}). Timeout returns non-zero with error=timeout.",
    )
    controller_run_parser.set_defaults(func=cmd_controller_run)

    controller_plan_parser = subcommands.add_parser(
        "controller-plan",
        help="Print the safe command contract for an LLM/controller",
        description="Print the safe command contract for an LLM/controller",
    )
    controller_plan_parser.add_argument("--path", default=".")
    controller_plan_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    controller_plan_parser.set_defaults(func=cmd_controller_plan)

    agent_loop_parser = subcommands.add_parser(
        "agent-loop",
        help="Run one safe sandboxed agent loop and save a proposal",
        description="Run one safe sandboxed agent loop and save a proposal",
    )
    agent_loop_parser.add_argument("goal", nargs="+")
    agent_loop_parser.add_argument("--path", default=".")
    agent_loop_parser.add_argument("--host", default="nixos")
    agent_loop_parser.add_argument("--module", default="auto", choices=["auto", "devtools", "fun", "agentic-base"])
    agent_loop_parser.add_argument("--agentix-command", default="agentix")
    agent_loop_parser.add_argument("--keep", action="store_true", help="Keep the temporary worktree for manual inspection")
    agent_loop_parser.add_argument("--dry-run", action="store_true", help="Plan the agent loop without creating a worktree or proposal")
    agent_loop_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GOAL_TIMEOUT_SECONDS,
        help=f"Seconds to wait for the inner goal subprocess before killing it (default: {DEFAULT_GOAL_TIMEOUT_SECONDS}). Timeout returns non-zero with error=timeout.",
    )
    agent_loop_parser.set_defaults(func=cmd_agent_loop)

    worktree_parser = subcommands.add_parser(
        "worktree-run",
        help="Run a supported goal inside a temporary Git worktree",
        description="Run a supported goal inside a temporary Git worktree",
    )
    worktree_parser.add_argument("goal", nargs="+")
    worktree_parser.add_argument("--path", default=".")
    worktree_parser.add_argument("--host", default="nixos")
    worktree_parser.add_argument("--module", default="auto", choices=["auto", "devtools", "fun", "agentic-base"])
    worktree_parser.add_argument("--agentix-command", default="agentix")
    worktree_parser.add_argument("--keep", action="store_true", help="Keep the temporary worktree for manual inspection")
    worktree_parser.add_argument("--save-proposal", action="store_true", help="Save the staged worktree diff as a source workspace proposal")
    worktree_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    worktree_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GOAL_TIMEOUT_SECONDS,
        help=f"Seconds to wait for the inner goal subprocess before killing it (default: {DEFAULT_GOAL_TIMEOUT_SECONDS}). Timeout returns non-zero with error=timeout.",
    )
    worktree_parser.set_defaults(func=cmd_worktree_run)

    self_test_parser = subcommands.add_parser(
        "self-test",
        help="Run installed-command smoke tests against a temporary fixture",
        description="Run installed-command smoke tests against a temporary fixture",
    )
    self_test_parser.add_argument("--agentix-command", default=None)
    self_test_parser.set_defaults(func=cmd_self_test)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

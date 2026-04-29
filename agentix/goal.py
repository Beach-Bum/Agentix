import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agentix.modules import create_module_patch
from agentix.preflight import nixos_preflight
from agentix.workflows import package_flow


PACKAGE_RE = re.compile(
    r"^(?:add|install)\s+(?:package\s+)?(?P<package>[a-zA-Z0-9_.+-]+)(?:\s+(?:to|in)\s+(?:module\s+)?(?P<module>[a-zA-Z0-9_-]+))?$",
    re.IGNORECASE,
)

CREATE_MODULE_RE = re.compile(
    r"^create\s+(?:a\s+)?module\s+(?P<name>[a-zA-Z0-9_-]+)(?:\s+(?:with\s+)?(?:template\s+)?(?P<template>empty|packages|services))?$",
    re.IGNORECASE,
)


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def run_command(command: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(command)}")
    return subprocess.run(command, cwd=cwd).returncode


def parse_goal(goal: str) -> dict:
    goal = goal.strip()

    package_match = PACKAGE_RE.match(goal)
    if package_match:
        return {
            "kind": "package",
            "package": package_match.group("package"),
            "module": package_match.group("module") or "auto",
        }

    module_match = CREATE_MODULE_RE.match(goal)
    if module_match:
        return {
            "kind": "module_create",
            "name": module_match.group("name"),
            "template": module_match.group("template") or "empty",
        }

    return {
        "kind": "unsupported",
        "goal": goal,
    }


def apply_patch_and_verify(
    path: Path,
    patch_path: Path,
    host: str,
    yes: bool = False,
    allow_dirty: bool = False,
) -> int:
    ok, problems = nixos_preflight(path, allow_dirty=allow_dirty)
    if not ok:
        print("Preflight failed. Refusing goal apply.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    precheck_code = run_command(["git", "apply", "--check", str(patch_path)], cwd=path)
    if precheck_code != 0:
        print("Patch is stale or does not apply cleanly. Refusing goal apply.")
        return precheck_code

    print(f"Patch: {patch_path}")
    print()
    print(patch_path.read_text(encoding="utf-8"))

    if not yes:
        answer = input("Apply this patch and run verify? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not applying.")
            return 1

    check_code = run_command(["git", "apply", "--check", str(patch_path)], cwd=path)
    if check_code != 0:
        print("Patch check failed. Not applying.")
        return check_code

    apply_code = run_command(["git", "apply", str(patch_path)], cwd=path)
    if apply_code != 0:
        print("Patch apply failed.")
        return apply_code

    print()
    print("Patch applied.")
    print("Adding changed files to Git so flakes can see new files...")

    add_code = run_command(["git", "add", "."], cwd=path)
    if add_code != 0:
        print("git add failed.")
        return add_code

    print()
    print("Running Agentix verify...")

    verify_code = run_command(
        ["agentix", "verify", "--path", str(path), "--host", host],
        cwd=path,
    )

    if verify_code != 0:
        print("Verify failed. Review the output above.")
        return verify_code

    print()
    print("Goal flow passed.")
    print()
    print("Next human-controlled step:")
    print(f"  cd {path} && rebuild-nixos")

    return 0


def run_goal(
    path: Path,
    goal: str,
    host: str = "nixos",
    module: str = "auto",
    yes: bool = False,
    dry_run: bool = False,
    allow_dirty: bool = False,
) -> int:
    parsed = parse_goal(goal)

    print("Agentix Goal Runner")
    print()
    print(f"Goal: {goal}")
    print("Parsed:")
    print(json.dumps(parsed, indent=2, sort_keys=True))
    print()

    if parsed["kind"] == "unsupported":
        print("Unsupported goal.")
        print()
        print("Supported examples:")
        print('  agentix run "add package btop" --path ~/nixos-config')
        print('  agentix run "install lolcat" --path ~/nixos-config')
        print('  agentix run "create module ai with template packages" --path ~/nixos-config')
        return 1

    if dry_run:
        print("Dry run only. No files changed.")
        return 0

    if parsed["kind"] == "package":
        selected_module = parsed.get("module") or module
        if selected_module == "auto":
            selected_module = module

        return package_flow(
            path=path,
            package=parsed["package"],
            module=selected_module,
            yes=yes,
            allow_dirty=allow_dirty,
        )

    if parsed["kind"] == "module_create":
        ok, problems = nixos_preflight(path, allow_dirty=allow_dirty)
        if not ok:
            print("Preflight failed. Refusing to create module proposal.")
            print()
            for problem in problems:
                print(f"- {problem}")
            return 1

        try:
            diff = create_module_patch(path, parsed["name"], parsed["template"])
        except Exception as exc:
            print(f"Could not create module proposal: {exc}")
            return 1

        proposal_dir = path / ".agentix" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = proposal_dir / f"{now_id()}-create-module-{parsed['name']}.patch"
        proposal_path.write_text(diff, encoding="utf-8")

        print(f"Saved proposal: {proposal_path}")
        print()

        return apply_patch_and_verify(
            path=path,
            patch_path=proposal_path,
            host=host,
            yes=yes,
            allow_dirty=allow_dirty,
        )

    print("Unsupported parsed goal kind.")
    return 1

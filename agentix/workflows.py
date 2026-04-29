import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agentix.nixos import add_package_to_module
from agentix.preflight import nixos_preflight


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def run(command: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(command)}")
    return subprocess.run(command, cwd=cwd).returncode


def package_flow(
    path: Path,
    package: str,
    module: str,
    yes: bool = False,
    allow_dirty: bool = False,
) -> int:
    ok, problems = nixos_preflight(path, allow_dirty=allow_dirty)

    if not ok:
        print("Preflight failed. Refusing package flow.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    try:
        diff, selected_module = add_package_to_module(path, package, module)
    except Exception as exc:
        print(f"Could not create package proposal: {exc}")
        return 1

    print(f"Package flow: add `{package}` to module `{selected_module}`")
    print()
    print("This workflow will:")
    print("- create a proposal patch")
    print("- ask before applying")
    print("- apply through git apply")
    print("- run agentix verify")
    print("- stop before system switch")
    print()
    print(diff)

    proposal_dir = path / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    proposal_path = proposal_dir / f"{now_id()}-add-package-{package}.patch"
    proposal_path.write_text(diff, encoding="utf-8")

    print()
    print(f"Saved proposal: {proposal_path}")
    print()

    if not yes:
        answer = input("Apply this patch and run verify? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not applying.")
            return 1

    check_code = run(["git", "apply", "--check", str(proposal_path)], cwd=path)
    if check_code != 0:
        print("Patch check failed. Not applying.")
        return check_code

    apply_code = run(["git", "apply", str(proposal_path)], cwd=path)
    if apply_code != 0:
        print("Patch apply failed.")
        return apply_code

    print()
    print("Patch applied.")
    print()
    print("Important: adding changed files to Git before verify.")
    run(["git", "add", "."], cwd=path)

    print()
    print("Running Agentix verify...")
    verify_code = run(["agentix", "verify", "--path", str(path), "--host", "nixos"], cwd=path)

    if verify_code != 0:
        print()
        print("Verify failed. Review the output above.")
        return verify_code

    print()
    print("Package flow passed.")
    print()
    print("Next human-controlled step:")
    print(f"  cd {path} && rebuild-nixos")
    print()
    print("After successful rebuild:")
    print(f'  git commit -m "Add {package} through Agentix package flow"')

    return 0



def apply_verify_flow(
    path: Path,
    patch_path: Path,
    host: str = "nixos",
    yes: bool = False,
    allow_dirty: bool = False,
) -> int:
    patch_path = patch_path.expanduser().resolve()

    if not patch_path.exists():
        print(f"Patch does not exist: {patch_path}")
        return 1

    ok, problems = nixos_preflight(path, allow_dirty=allow_dirty)
    if not ok:
        print("Preflight failed. Refusing apply + verify flow.")
        print()
        for problem in problems:
            print(f"- {problem}")
        return 1

    precheck_code = run(["git", "apply", "--check", str(patch_path)], cwd=path)
    if precheck_code != 0:
        print("Patch is stale or does not apply cleanly. Refusing apply + verify.")
        return precheck_code

    print("Agentix Apply + Verify Flow")
    print()
    print(f"Workspace: {path}")
    print(f"Patch: {patch_path}")
    print()
    print(patch_path.read_text(encoding="utf-8"))

    if not yes:
        answer = input("Apply this patch and run verify? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Not applying.")
            return 1

    check_code = run(["git", "apply", "--check", str(patch_path)], cwd=path)
    if check_code != 0:
        print("Patch check failed. Not applying.")
        return check_code

    apply_code = run(["git", "apply", str(patch_path)], cwd=path)
    if apply_code != 0:
        print("Patch apply failed.")
        return apply_code

    print()
    print("Patch applied.")
    print()
    print("Adding changed files to Git so flakes can see new files...")
    add_code = run(["git", "add", "."], cwd=path)
    if add_code != 0:
        print("git add failed.")
        return add_code

    print()
    print("Running Agentix verify...")
    verify_code = run(["agentix", "verify", "--path", str(path), "--host", host], cwd=path)

    if verify_code != 0:
        print()
        print("Verify failed. Review the output above.")
        return verify_code

    print()
    print("Apply + verify passed.")
    print()
    print("Next human-controlled step:")
    print(f"  cd {path} && rebuild-nixos")
    print()
    print("After successful rebuild:")
    print("  git commit -m \"Describe the verified config change\"")

    return 0

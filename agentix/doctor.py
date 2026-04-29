import shutil
import subprocess
from pathlib import Path


REQUIRED_COMMANDS = [
    "git",
    "nix",
    "nixos-rebuild",
]

REQUIRED_FILES = [
    "flake.nix",
    ".agentix/policy.json",
    "modules/devtools.nix",
    "modules/fun.nix",
]


def git_dirty(path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=path,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return ["not a git repository"]

    return [line for line in result.stdout.splitlines() if line.strip()]


def run_doctor(path: Path) -> int:
    failures = 0

    print("Agentix Doctor")
    print()
    print(f"Path: {path}")
    print()

    print("Commands:")
    for command in REQUIRED_COMMANDS:
        found = shutil.which(command)
        if found:
            print(f"  OK   {command}: {found}")
        else:
            print(f"  FAIL {command}: not found")
            failures += 1

    print()
    print("Files:")
    for rel in REQUIRED_FILES:
        target = path / rel
        if target.exists():
            print(f"  OK   {rel}")
        else:
            print(f"  FAIL {rel}")
            failures += 1

    print()
    dirty = git_dirty(path)

    if dirty:
        print("Git: dirty")
        for line in dirty:
            print(f"  {line}")
    else:
        print("Git: clean")

    print()
    if failures:
        print(f"Doctor result: failed with {failures} issue(s)")
        return 1

    print("Doctor result: ready")
    return 0

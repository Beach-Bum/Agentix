import subprocess
from pathlib import Path


NIXOS_REQUIRED_FILES = [
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

    lines = [line for line in result.stdout.splitlines() if line.strip()]

    # Agentix runtime files should not block preflight.
    ignored_prefixes = [
        "?? .agentix/",
        " M .agentix/",
        "M  .agentix/",
        "A  .agentix/",
    ]

    return [
        line for line in lines
        if not any(line.startswith(prefix) for prefix in ignored_prefixes)
    ]


def workspace_preflight(path: Path, allow_dirty: bool = False) -> tuple[bool, list[str]]:
    problems: list[str] = []

    if not (path / ".git").exists():
        problems.append("not a Git repository")

    dirty = git_dirty(path)
    if dirty and not allow_dirty:
        problems.append("Git tree is dirty. Commit, restore, or pass --allow-dirty.")
        problems.extend([f"  {line}" for line in dirty])

    return len(problems) == 0, problems


def nixos_preflight(path: Path, allow_dirty: bool = False) -> tuple[bool, list[str]]:
    ok, problems = workspace_preflight(path, allow_dirty=allow_dirty)

    for rel in NIXOS_REQUIRED_FILES:
        if not (path / rel).exists():
            problems.append(f"missing required file: {rel}")

    return len(problems) == 0, problems


# Backward-compatible default: NixOS-specific.
def preflight(path: Path, allow_dirty: bool = False) -> tuple[bool, list[str]]:
    return nixos_preflight(path, allow_dirty=allow_dirty)

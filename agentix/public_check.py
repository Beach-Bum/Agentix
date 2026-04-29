import fnmatch
import os
from pathlib import Path


PUBLIC_UNSAFE_NAMES = {
    ".agentix",
    ".claude",
    "private",
    "MEMORY.md",
    "AGENTIX-CHECKPOINT.md",
    "CLAUDE.local.md",
    "audit.jsonl",
    "checkpoint",
}

PUBLIC_UNSAFE_PATTERNS = [
    "*.local.md",
    "*.secret",
    "*.secrets",
    "*.key",
    "*.pem",
    "*.transcript",
    "*.transcript.json",
    "*.session",
    "*.session.json",
    "*.checkpoint",
    "*.checkpoint.json",
    "*.log",
    "*.tmp",
    "*.swp",
    "*.bak",
    "*.save",
    "*~",
]

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def _is_unsafe_name(name: str) -> bool:
    if name in PUBLIC_UNSAFE_NAMES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in PUBLIC_UNSAFE_PATTERNS)


def find_public_unsafe_paths(path: Path) -> list[str]:
    findings: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(path):
        rel_dir = Path(dirpath).relative_to(path)

        keep_dirs = []
        for d in dirnames:
            if d in SKIP_DIRS:
                continue
            if _is_unsafe_name(d):
                findings.add(str(rel_dir / d))
                continue
            keep_dirs.append(d)
        dirnames[:] = keep_dirs

        for f in filenames:
            if _is_unsafe_name(f):
                findings.add(str(rel_dir / f))

    return sorted(findings)


def print_public_check(path: Path) -> int:
    findings = find_public_unsafe_paths(path)

    print("Agentix Public Release Check")
    print()
    print(f"Path: {path}")
    print()

    if not findings:
        print("Result: public-safe candidate")
        return 0

    print("Result: not public-safe")
    print()
    print("Found private/local files that should not be in a public release:")
    for finding in findings:
        print(f"- {finding}")

    print()
    print("Recommendation:")
    print("- Keep this repo private.")
    print("- Create a sanitized export for public release.")
    print("- Do not publish Git history containing MEMORY.md or private checkpoints.")

    return 1

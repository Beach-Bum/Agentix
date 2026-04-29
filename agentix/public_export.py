import fnmatch
import shutil
from pathlib import Path


EXCLUDE_NAMES = {
    ".git",
    ".agentix",
    ".claude",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "private",
    "MEMORY.md",
    "AGENTIX-CHECKPOINT.md",
    "CLAUDE.local.md",
    "audit.jsonl",
    "checkpoint",
}

EXCLUDE_PATTERNS = [
    "*.pyc",
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


def should_exclude(path: Path) -> bool:
    name = path.name

    if name in EXCLUDE_NAMES:
        return True

    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_PATTERNS)


def export_public_repo(source: Path, dest: Path, overwrite: bool = False) -> None:
    source = source.resolve()
    dest = dest.resolve()

    if dest.exists():
        if not overwrite:
            raise FileExistsError(f"Destination already exists: {dest}")
        shutil.rmtree(dest)

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            candidate = Path(directory) / name
            if should_exclude(candidate):
                ignored.add(name)
        return ignored

    shutil.copytree(source, dest, ignore=ignore)

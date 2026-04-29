import hashlib
import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_source(path: Path) -> dict:
    head_proc = _git(["rev-parse", "HEAD"], path)
    diff_proc = _git(["diff", "HEAD", "--"], path)
    listed_proc = _git(["ls-files", "--others", "--exclude-standard"], path)

    failures: list[str] = []
    for label, proc in (
        ("rev-parse HEAD", head_proc),
        ("diff HEAD --", diff_proc),
        ("ls-files --others --exclude-standard", listed_proc),
    ):
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip() or "no stderr"
            failures.append(f"git {label} failed (returncode={proc.returncode}): {stderr}")

    if failures:
        return {"error": "; ".join(failures)}

    untracked: dict[str, str] = {}
    for line in listed_proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        full = path / rel
        try:
            if full.is_file():
                untracked[rel] = _hash_file(full)
        except OSError as exc:
            return {"error": f"hash of untracked path {rel} failed: {exc}"}

    return {
        "head": head_proc.stdout.strip(),
        "tracked_diff": diff_proc.stdout,
        "untracked": untracked,
    }


def compare_source(
    before: dict,
    after: dict,
    allowed_new_paths: set[str] | None = None,
) -> list[str]:
    allowed = set(allowed_new_paths or set())
    mutations: list[str] = []

    if before.get("head") != after.get("head"):
        mutations.append(
            f"head changed: {before.get('head')} -> {after.get('head')}"
        )

    if before.get("tracked_diff") != after.get("tracked_diff"):
        mutations.append("tracked files changed in source workspace")

    before_untracked = before.get("untracked", {}) or {}
    after_untracked = after.get("untracked", {}) or {}

    for rel, hash_ in sorted(after_untracked.items()):
        if rel not in before_untracked:
            if rel in allowed:
                continue
            mutations.append(f"new untracked file: {rel}")
        elif before_untracked[rel] != hash_:
            mutations.append(f"untracked file content changed: {rel}")

    for rel in sorted(before_untracked):
        if rel not in after_untracked:
            mutations.append(f"untracked file removed: {rel}")

    return mutations

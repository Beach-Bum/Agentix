import subprocess
from pathlib import Path


def proposals_dir(path: Path) -> Path:
    return path / ".agentix" / "proposals"


def list_proposals(path: Path) -> list[Path]:
    directory = proposals_dir(path)

    if not directory.exists():
        return []

    return sorted(directory.glob("*.patch"))


def clean_proposals(path: Path) -> int:
    proposals = list_proposals(path)

    for proposal in proposals:
        proposal.unlink()

    return len(proposals)


def proposal_applies(path: Path, proposal: Path) -> bool:
    result = subprocess.run(
        ["git", "apply", "--check", str(proposal)],
        cwd=path,
        text=True,
        capture_output=True,
    )

    return result.returncode == 0


def proposal_status(path: Path, proposal: Path) -> str:
    return "clean" if proposal_applies(path, proposal) else "stale"


def list_stale_proposals(path: Path) -> list[Path]:
    stale: list[Path] = []

    for proposal in list_proposals(path):
        if not proposal_applies(path, proposal):
            stale.append(proposal)

    return stale


def prune_stale_proposals(path: Path) -> int:
    stale = list_stale_proposals(path)

    for proposal in stale:
        proposal.unlink()

    return len(stale)

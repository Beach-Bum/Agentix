import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agentix.audit_log import audit
from agentix.preflight import workspace_preflight
from agentix.source_snapshot import compare_source, snapshot_source


DEFAULT_GOAL_TIMEOUT_SECONDS = 1800


def run(
    command: list[str],
    cwd: Path,
    capture: bool = False,
    quiet: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    if not quiet:
        print("$ " + " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture or quiet,
        timeout=timeout,
    )


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.+-]+", "-", text.strip().lower()).strip("-")
    return slug[:80] or "goal"


def save_proposal(path: Path, goal: str, diff: str) -> Path:
    proposal_dir = path / ".agentix" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)

    proposal = proposal_dir / f"{now_id()}-worktree-{safe_slug(goal)}.patch"
    proposal.write_text(diff, encoding="utf-8")
    return proposal


def emit_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def worktree_run(
    path: Path,
    goal: str,
    host: str = "nixos",
    module: str = "auto",
    agentix_command: str = "agentix",
    keep: bool = False,
    save_proposal_patch: bool = False,
    json_output: bool = False,
    audit_event: bool = True,
    timeout: int | None = DEFAULT_GOAL_TIMEOUT_SECONDS,
) -> int:
    result: dict = {
        "action": "worktree_run",
        "goal": goal,
        "source_workspace": str(path),
        "passed": False,
        "source_modified": False,
        "worktree_kept": keep,
        "worktree_path": None,
        "proposal_saved": None,
        "staged_diff": "",
        "status": "",
        "error": None,
    }

    def _audit_worktree(result_label: str) -> None:
        if not audit_event:
            return
        audit(path, {
            "action": "worktree_run",
            "mode": "worktree",
            "goal": goal,
            "result": result_label,
            "passed": result["passed"],
            "source_modified": result["source_modified"],
            "proposal_saved": result["proposal_saved"],
            "error": result["error"],
            "path": str(path),
        })

    ok, problems = workspace_preflight(path, allow_dirty=False)
    if not ok:
        result["error"] = "preflight_failed"
        result["problems"] = problems
        _audit_worktree("preflight_failed")
        if json_output:
            emit_json(result)
        else:
            print("Preflight failed. Refusing worktree run.")
            print()
            for problem in problems:
                print(f"- {problem}")
        return 1

    source_before = snapshot_source(path)
    if source_before.get("error"):
        result["passed"] = False
        result["source_modified"] = True
        result["error"] = "source_snapshot_failed"
        result["source_mutations"] = [source_before["error"]]
        _audit_worktree("source_snapshot_failed")
        if json_output:
            emit_json(result)
        else:
            print("Source snapshot failed. Refusing worktree run.")
            print(f"- {source_before['error']}")
        return 1

    if keep:
        tmp_path = tempfile.mkdtemp(prefix="agentix-worktree-")
        cleanup_tmp = False
        tmp_context = None
    else:
        tmp_context = tempfile.TemporaryDirectory(prefix="agentix-worktree-")
        tmp_path = tmp_context.__enter__()
        cleanup_tmp = True

    worktree = Path(tmp_path) / "worktree"
    result["worktree_path"] = str(worktree)

    try:
        if not json_output:
            print("Agentix Worktree Run")
            print()
            print(f"Source workspace: {path}")
            print(f"Temporary worktree: {worktree}")
            print(f"Goal: {goal}")
            print()

        add_result = run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            cwd=path,
            quiet=json_output,
        )
        if add_result.returncode != 0:
            result["error"] = "worktree_add_failed"
            result["stderr"] = add_result.stderr
            _audit_worktree("worktree_add_failed")
            if json_output:
                emit_json(result)
            else:
                print("Could not create temporary worktree.")
            return add_result.returncode

        try:
            try:
                goal_result = run(
                    [
                        agentix_command,
                        "run",
                        goal,
                        "--path",
                        str(worktree),
                        "--host",
                        host,
                        "--module",
                        module,
                        "--yes",
                    ],
                    cwd=worktree,
                    quiet=json_output,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                result["error"] = "timeout"
                result["timeout_seconds"] = timeout
                if json_output:
                    result["goal_stdout"] = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                    result["goal_stderr"] = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
                _audit_worktree("timeout")
                if json_output:
                    emit_json(result)
                else:
                    print()
                    print(f"Goal subprocess timed out after {timeout}s.")
                return 124

            result["goal_returncode"] = goal_result.returncode
            if json_output:
                result["goal_stdout"] = goal_result.stdout
                result["goal_stderr"] = goal_result.stderr

            if goal_result.returncode != 0:
                result["error"] = "goal_failed"
                _audit_worktree("goal_failed")
                if json_output:
                    emit_json(result)
                else:
                    print("Goal failed inside temporary worktree.")
                return goal_result.returncode

            status_result = run(["git", "status", "--short"], cwd=worktree, capture=True, quiet=json_output)
            diff_result = run(["git", "diff", "--cached"], cwd=worktree, capture=True, quiet=json_output)
            diff = diff_result.stdout

            result["status"] = status_result.stdout
            result["staged_diff"] = diff

            if not json_output:
                print()
                print("Temporary worktree status:")
                if status_result.stdout.strip():
                    print(status_result.stdout, end="")
                else:
                    print("clean")

                print()
                print("Temporary worktree staged diff:")
                if diff.strip():
                    print(diff, end="")
                else:
                    print("No staged diff.")

            if save_proposal_patch:
                if not diff.strip():
                    result["error"] = "no_staged_diff"
                    _audit_worktree("no_staged_diff")
                    if json_output:
                        emit_json(result)
                    else:
                        print()
                        print("No staged diff to save as a proposal.")
                    return 1

                proposal = save_proposal(path, goal, diff)
                result["proposal_saved"] = str(proposal)

                if not json_output:
                    print()
                    print(f"Saved proposal: {proposal}")
                    print("The proposal was saved in the source workspace, but not applied.")

            allowed_paths: set[str] = set()
            if result["proposal_saved"]:
                try:
                    allowed_paths.add(
                        str(Path(result["proposal_saved"]).resolve().relative_to(path.resolve()))
                    )
                except ValueError:
                    pass

            source_after = snapshot_source(path)
            if source_after.get("error"):
                result["passed"] = False
                result["source_modified"] = True
                result["error"] = "source_snapshot_failed"
                result["source_mutations"] = [source_after["error"]]
                _audit_worktree("source_snapshot_failed")
                if json_output:
                    emit_json(result)
                else:
                    print()
                    print("Source snapshot failed after run.")
                    print(f"- {source_after['error']}")
                return 1

            mutations = compare_source(source_before, source_after, allowed_new_paths=allowed_paths)
            if mutations:
                result["passed"] = False
                result["source_modified"] = True
                result["error"] = "source_workspace_mutated"
                result["source_mutations"] = mutations
                _audit_worktree("source_workspace_mutated")
                if json_output:
                    emit_json(result)
                else:
                    print()
                    print("Source workspace was mutated unexpectedly:")
                    for m in mutations:
                        print(f"- {m}")
                return 1

            result["passed"] = True
            result["source_modified"] = False
            _audit_worktree("ok")

            if json_output:
                emit_json(result)
            else:
                print()
                print("Original workspace was not modified.")
                print("Review the diff above before applying anything to the real config.")
            return 0
        finally:
            if keep:
                if not json_output:
                    print()
                    print(f"Kept temporary worktree: {worktree}")
                    print("Remove it manually when done:")
                    print(f"  cd {path} && git worktree remove --force {worktree}")
            else:
                remove_result = run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=path,
                    quiet=json_output,
                )
                if remove_result.returncode != 0 and not json_output:
                    print("Warning: failed to remove temporary worktree.")
    finally:
        if cleanup_tmp and tmp_context is not None:
            tmp_context.__exit__(None, None, None)

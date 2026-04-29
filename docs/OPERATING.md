# Agentix Operating Guide

Agentix is a cautious control layer for NixOS configuration work. It prepares
verified proposals; the human applies and rebuilds.

## Safety contract

Agentix behaves like a cautious junior infrastructure engineer:

1. Inspect the workspace.
2. Plan the change.
3. Propose a patch.
4. Ask for approval before applying.
5. Apply only after approval.
6. Add new files to Git so flakes can see them.
7. Run verification.
8. Stop before final system activation.

Agentix does not run `sudo`, does not run `nixos-rebuild switch`, does not run
`rebuild-nixos`, and does not directly mutate `/etc/nixos`.

The human runs the final activation:

```bash
cd ~/nixos-config
rebuild-nixos
```

## Controller workflow

For LLM-driven runs the safety ladder is:

```
controller-plan
       v
controller-run (dry-run)
       v
controller-run --execute
       v
saved proposal patch
       v
human apply-verify
       v
human rebuild-nixos
```

Each rung is reversible until the next. The controller stops at the saved
proposal; everything below is human-only.

`controller-plan --json` prints the allowed commands, forbidden commands, and
safety boundaries. Run it first whenever a controller starts a session.

`controller-run` defaults to dry-run: it parses the goal, prints the plan,
and stops without spawning the worktree subprocess. With `--execute` it
spawns a temporary Git worktree, runs the goal there, captures the diff,
saves a proposal patch into the source workspace's `.agentix/proposals/`,
and exits. Always emits JSON.

`worktree-run` is the lower-level building block. `--save-proposal` saves the
staged diff, `--json` emits machine-readable output (and captures the inner
goal's stdout/stderr), `--keep` keeps the temporary worktree for inspection.
`agent-loop` is a single-pass wrapper around `worktree-run` that always saves
a proposal in non-dry-run mode.

See [CONTROLLER.md](CONTROLLER.md) for the full flag reference.

## Source workspace untouched

Every controller and worktree run snapshots the source workspace before and
after the inner subprocess: HEAD commit, `git diff HEAD --`, and SHA-256 of
every untracked file. Any of these counts as a violation:

- HEAD changed.
- Any tracked file added, modified, deleted, renamed, or mode-changed.
- Any untracked file added or removed outside `.agentix/proposals/`.
- Any untracked file's content changed.

The only allowed mutation is exactly one new patch under `.agentix/proposals/`
when the run asks to save a proposal. Anything else fails with
`error="source_workspace_mutated"` and a non-zero exit. A failed git snapshot
itself fails closed with `error="source_snapshot_failed"`.

## Timeout

The inner goal subprocess has a default timeout of 1800 seconds (30 minutes).
Override with `--timeout SECONDS` on `controller-run`, `worktree-run`, or
`agent-loop`. On expiry the goal child is killed and the run returns exit
code 124 with `error="timeout"` and a `timeout_seconds` field. Audit records
`result="timeout"`. Timeout is scoped to the goal subprocess only — git
worktree create/remove is not timed.

## Audit log

Every controller-run, worktree-run, and agent-loop invocation appends one
JSON line to `<repo>/.agentix/audit.jsonl` (gitignored). Fields:

- `action` — `controller_run` or `worktree_run`.
- `mode` — `dry_run`/`execute` for controller-run, `worktree` for worktree-run.
- `goal`, `result`, `passed`, `source_modified`, `proposal_saved`, `error`,
  `path`, `timestamp`.

Inspect with:

```bash
agentix audit tail --path . --lines 5 --json
agentix audit summary --path . --json
```

When `controller-run --execute` runs, the inner worktree audit is suppressed
so each top-level invocation produces exactly one event.

## Claude Code integration

Claude Code reads [CLAUDE-CODE.md](CLAUDE-CODE.md) and the session prompt at
[prompts/claude-agentix-controller.md](prompts/claude-agentix-controller.md).
It must run `controller-plan` first, may run `controller-run` and
`worktree-run` for sandboxed work, and must stop at the saved proposal.
Apply, verify, and rebuild are human-only.

## Public release

Private repositories typically contain `MEMORY.md`, `.agentix/audit.jsonl`,
`.claude/`, local checkpoints, transcripts, and other session artifacts. Do
not publish their history directly. Use the sanitized export workflow:

```bash
agentix public-check --path ~/projects/agentix
agentix export-public --path ~/projects/agentix --dest /tmp/agentix-public --yes
agentix public-check --path /tmp/agentix-public
```

`public-check` recursively flags Claude session state, transcripts, audit
logs, editor temps, and other private artifacts. `export-public` mirrors the
same exclusions when copying. The intentional public docs
(`docs/CLAUDE-CODE.md`, `docs/prompts/claude-agentix-controller.md`,
`docs/CONTROLLER.md`) are preserved.

## What Agentix is not

Agentix is not a fully autonomous deployer. It does not bypass review. It
prepares verified proposals; the human owns the apply and rebuild step.

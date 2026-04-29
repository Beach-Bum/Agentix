# Agentix Controller Commands

The controller commands let an LLM (or human) plan and run goals inside a
sandboxed Git worktree without ever mutating the source workspace or the live
NixOS system. The human stays on the apply/rebuild side of the boundary.

## Safety ladder

Every NixOS goal walks the same ladder. Each rung is reversible until the next.

```
controller-plan                # describe what is allowed
       v
controller-run (dry-run)       # parse + validate; no subprocess
       v
controller-run --execute       # run goal in a temp worktree, save proposal
       v
saved proposal patch           # human reviews the diff
       v
human apply-verify             # human applies the patch and runs verify
       v
human rebuild-nixos            # human activates the new system
```

Claude Code (or any controller) stops at the saved-proposal rung. Apply,
verify, and rebuild are human-only.

## Commands

### controller-plan

Print the controller's safety contract. Always read-only.

```
agentix controller-plan --path ~/nixos-config --json
```

Output: `allowed_commands`, `forbidden_commands`, `safety_boundaries`,
`default_mode`, `source_workspace_must_remain_untouched`, `final_activation`,
`recommended_first_command`. No subprocess; no audit event.

Run this first whenever a controller starts a session.

Flags:

| Flag | Meaning |
|---|---|
| `--path PATH` | Workspace path (default `.`). |
| `--json` | Emit machine-readable JSON. |

### controller-run

Plan and (optionally) execute a goal under the controller's contract. Always
emits JSON.

```
agentix controller-run "create module foo with template packages" --path ~/nixos-config
agentix controller-run "create module foo with template packages" --path ~/nixos-config --execute
```

Without `--execute`: dry-run. Parses the goal, prints the plan, stops without
spawning the worktree subprocess. Result fields include `would_run_worktree`
and `would_save_proposal`.

With `--execute`: spawns a temporary Git worktree, runs the goal there,
captures the diff, saves a proposal patch into the source workspace's
`.agentix/proposals/`, and exits. Source workspace files outside that
directory are guaranteed untouched (verified by snapshot before and after).

Flags:

| Flag | Meaning |
|---|---|
| `--execute` | Run inside a temp worktree and save a proposal patch. Without this, dry-run only. |
| `--keep` | Keep the temp worktree for manual inspection (debug). |
| `--timeout SECONDS` | Kill the goal subprocess after N seconds (default 1800). On timeout: returns 124, payload `error="timeout"`. |
| `--path PATH` | Source workspace path (default `.`). |
| `--host HOST` | NixOS host name (default `nixos`). |
| `--module MODULE` | One of `auto`, `devtools`, `fun`, `agentic-base`. |
| `--agentix-command CMD` | Override the inner agentix binary (testing only). |

Audit: writes one `controller_run` event per invocation
(`action=controller_run`, `mode=dry_run|execute`, `result=ok|...`). The inner
worktree audit is suppressed to keep the audit log uncluttered.

### worktree-run

Run a goal inside a temp worktree without the controller wrapper. Lower-level
than `controller-run`: no controller plan in the output, no dry-run/execute
mode distinction. Use it for diagnostics or in scripts that already enforce
the controller contract themselves.

```
agentix worktree-run "create module foo with template packages" --path ~/nixos-config --save-proposal --json
```

Flags:

| Flag | Meaning |
|---|---|
| `--save-proposal` | Save the staged worktree diff as a source proposal. Without this, no proposal is written. |
| `--json` | Emit machine-readable JSON (also captures stdout/stderr of the inner goal). |
| `--keep` | Keep the temp worktree for manual inspection. |
| `--timeout SECONDS` | Default 1800. Same semantics as `controller-run`. |
| `--path` / `--host` / `--module` / `--agentix-command` | As above. |

Audit: writes one `worktree_run` event (`action=worktree_run`,
`mode=worktree`).

### agent-loop

Single-pass agent loop: parse the goal, run it in a temp worktree, save the
proposal.

```
agentix agent-loop "create module foo with template packages" --path ~/nixos-config --dry-run
agentix agent-loop "create module foo with template packages" --path ~/nixos-config
```

Flags:

| Flag | Meaning |
|---|---|
| `--dry-run` | Plan only — no worktree, no proposal. |
| `--keep` | Keep the temp worktree for manual inspection. |
| `--timeout SECONDS` | Default 1800. Same semantics. |
| `--path` / `--host` / `--module` / `--agentix-command` | As above. |

Audit: writes one `worktree_run` event when a worktree run actually happens.

## Source-workspace-untouched semantics

Before each worktree subprocess runs, the controller snapshots the source
workspace: HEAD commit, `git diff HEAD --` output, and SHA-256 hashes of
every untracked file. After the subprocess (and any proposal save), it
snapshots again. Any of the following is reported as
`error="source_workspace_mutated"`:

- HEAD changed.
- Any tracked file added, modified, deleted, renamed, or mode-changed.
- Any untracked file added or removed outside `.agentix/proposals/`.
- Any untracked file's content changed.

The only allowed source mutation is exactly one new proposal patch under
`.agentix/proposals/` when `--save-proposal` (or `controller-run --execute`)
asks for it.

If `git` itself fails during a snapshot (e.g. corrupted repo), the controller
fails closed with `error="source_snapshot_failed"`.

## Forbidden for the controller

The controller never runs:

- `sudo`
- `nixos-rebuild switch`
- `rebuild-nixos`
- direct edits to `/etc/nixos`
- `agentix apply` or `agentix apply-verify`
- `git commit` or `git push` of system config changes
- secret access (`~/.ssh`, private keys)

These are human-only.

## Claude Code workflow

When Claude Code (or any LLM controller) starts a session in this repo:

1. Read `docs/prompts/claude-agentix-controller.md`, `docs/CLAUDE-CODE.md`,
   `docs/OPERATING.md`.
2. Run `agentix controller-plan --path ~/nixos-config --json`. Summarize the
   contract.
3. For each NixOS goal:
   1. `agentix controller-run "<goal>" --path ~/nixos-config` (dry-run).
   2. Summarize the JSON.
   3. Wait for human approval.
   4. `agentix controller-run "<goal>" --path ~/nixos-config --execute`.
   5. Report `passed`, `source_modified`, `proposal_saved`,
      `stops_before_apply`, `stops_before_rebuild`.
   6. Stop.
4. The human reviews `<workspace>/.agentix/proposals/<latest>.patch` and runs
   `apply-verify` if it looks right.
5. The human runs `rebuild-nixos` to activate.

If a controller-run reports `error="source_workspace_mutated"`,
`error="source_snapshot_failed"`, or `error="timeout"`, stop and surface the
JSON to the human. Do not retry without understanding why.

## Auditing

All controller and worktree invocations append one event to
`<workspace>/.agentix/audit.jsonl` (gitignored). Inspect with:

```
agentix audit tail --path ~/nixos-config --json
agentix audit summary --path ~/nixos-config --json
```

Useful when retracing what the controller did during a session.

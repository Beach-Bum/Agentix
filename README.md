# Agentix

Agentix is a cautious control layer for NixOS and Nix flake work. It helps an
LLM (or a human) plan and prepare configuration changes inside a sandboxed Git
worktree, save them as reviewable proposal patches, and stop. The human
applies the patch and runs the rebuild.

Agentix does not run `sudo`, `nixos-rebuild switch`, or `rebuild-nixos`. It
does not edit `/etc/nixos`. It does not push or commit system config changes.
Apply, verify, and activation are human-only. Agentix prepares verified
proposals; the human owns the apply and rebuild step.

## What it does today

| Version | Capability |
|---|---|
| v0.1 | MVP: inspect repos, propose Nix dev shells, save patches, manual apply with audit. |
| v0.2 | Sandboxed agent-loop: run a goal in a temporary Git worktree, save the diff as a proposal. Source workspace stays untouched. |
| v0.3 | Controller layer: `controller-plan` describes the contract, `controller-run` plans and (optionally) executes a goal end-to-end with full audit, a hardened source-untouched invariant, and conservative subprocess timeouts. Claude Code integrates here. |

## Commands at a glance

- `agentix controller-plan --path <repo> --json` — print the safety contract.
- `agentix controller-run "<goal>" --path <repo>` — dry-run only.
- `agentix controller-run "<goal>" --path <repo> --execute` — run the goal in a temp worktree, save a proposal patch, stop.
- `agentix worktree-run "<goal>" --path <repo> --save-proposal --json` — lower-level form for scripts. `--keep` retains the temp worktree for inspection.
- `agentix agent-loop "<goal>" --path <repo>` — single-pass agent loop.
- `agentix audit tail --path <repo> --json` / `agentix audit summary --path <repo> --json` — review what happened.
- `agentix public-check --path <repo>` / `agentix export-public --path <repo> --dest <out> --yes` — check for or strip private artifacts before sharing.

See [docs/CONTROLLER.md](docs/CONTROLLER.md) for the full flag tables.

## Safety invariants

- **Source workspace untouched.** Every controller and worktree run snapshots
  HEAD, `git diff HEAD --`, and SHA-256 of every untracked file before and
  after the inner subprocess. Any unexpected change → exit non-zero with
  `error="source_workspace_mutated"`. The only allowed mutation is exactly
  one new patch under `.agentix/proposals/` when `--save-proposal` (or
  `controller-run --execute`) asks for it.
- **No apply, no rebuild, no sudo from the agent.** The agent stops at the
  saved proposal. A human runs `agentix apply-verify` and `rebuild-nixos`.
- **Conservative subprocess timeout.** Default 1800 seconds (30 minutes) on
  the inner goal subprocess (`--timeout SECONDS` to override). Timeout
  returns exit code 124 with `error="timeout"` and a clear audit line.
- **Audit log per run.** One JSON line per controller-run / worktree-run /
  agent-loop invocation, appended to `<repo>/.agentix/audit.jsonl`
  (gitignored). Inspect with `agentix audit tail` and `agentix audit summary`.

## Claude Code integration

Claude Code (and other LLM controllers) operate against the same contract.
Read [docs/prompts/claude-agentix-controller.md](docs/prompts/claude-agentix-controller.md)
and [docs/CLAUDE-CODE.md](docs/CLAUDE-CODE.md) for the session contract. The
controller stops at the saved-proposal rung; the human takes over from there.

## Public release

Private workspaces typically contain `MEMORY.md`, `.agentix/audit.jsonl`,
`.claude/`, local checkpoints, transcripts, and other session artifacts. Do
not publish a private repo's history directly. Use the sanitized export
workflow:

```
agentix public-check --path ~/projects/agentix
agentix export-public --path ~/projects/agentix --dest /tmp/agentix-public --yes
agentix public-check --path /tmp/agentix-public
```

`public-check` recursively flags Claude session state, transcripts, audit
logs, editor temps, and other private artifacts. `export-public` mirrors the
same exclusions when copying.

## Further reading

- [docs/OPERATING.md](docs/OPERATING.md) — operating contract and workflow.
- [docs/CONTROLLER.md](docs/CONTROLLER.md) — controller commands and flags.
- [docs/CLAUDE-CODE.md](docs/CLAUDE-CODE.md) — Claude Code integration contract.
- [docs/prompts/claude-agentix-controller.md](docs/prompts/claude-agentix-controller.md) — the LLM session prompt.

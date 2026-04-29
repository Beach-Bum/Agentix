# Contributing to Agentix

Agentix is a safety-first control layer for NixOS and other agentic
configuration workflows. It prepares verified proposal patches inside a
sandboxed Git worktree; humans apply and rebuild. The project's safety story
matters more than any single feature.

## Principles

- **Plan before changing.** Every goal starts with a parsed plan and a
  controller contract.
- **Prefer proposal patches over direct mutation.** Output a reviewable diff
  rather than touching the live tree.
- **Run risky work in temporary worktrees.** The source workspace must stay
  untouched outside `.agentix/proposals/`.
- **Verify before humans apply changes.** `agentix verify` runs doctor,
  `nix build`, and the VM build check before an apply step is offered.
- **Stop before live activation.** The controller halts at the saved
  proposal. Apply and rebuild are explicit, manual, human steps.
- **Humans control apply and rebuild.** The whole point of the design.

## What Agentix should not do

These are non-negotiable. Patches that loosen these will be rejected:

- Do not run `sudo`.
- Do not run `nixos-rebuild switch`.
- Do not run `rebuild-nixos`.
- Do not directly mutate `/etc/nixos`.
- Do not encourage unattended live-system changes.

If a feature seems to require any of these, that is a sign the design needs
rethinking, not the safety boundary.

## Development setup

Clone the repo and use [`uv`](https://docs.astral.sh/uv/) for the Python
environment:

```bash
uv sync
```

The three checks every change should pass before review:

```bash
uv run pytest
scripts/dev-cycle
agentix self-test
```

`scripts/dev-cycle` runs the test suite then reinstalls Agentix in editable
mode. `agentix self-test` is a smoke test against an installed Agentix
binary, including the controller dry-run/execute paths.

## Safety-sensitive files

Changes to these files need extra care:

- `agentix/controller_run.py` — top-level controller entry point.
- `agentix/worktree_run.py` — sandboxed worktree execution.
- `agentix/source_snapshot.py` — source-workspace-untouched integrity check.
- `agentix/preflight.py` — pre-run guards.
- `agentix/policy.py` — deny/warn rules.
- `agentix/public_check.py` — public-release artifact scanner.
- `agentix/public_export.py` — sanitized export.

Any safety-sensitive change must come with tests that prove the failure modes
fail closed — i.e. when something is wrong, the run exits non-zero with a
specific `error=...` code rather than silently passing or partially
proceeding. Tampering, timeout, snapshot failure, and source mutation are
already covered; new code paths should follow the same pattern.

## What not to commit

Do not commit private artifacts, secrets, transcripts, local machine state,
or temporary files. In particular:

- No `MEMORY.md` or other private memory files.
- No `.agentix/audit.jsonl`, `.claude/`, or session transcripts.
- No SSH keys, API credentials, or other secret material.
- No editor temp files (`*.swp`, `*.bak`, `*~`, `*.save`).
- No local logs or `*.tmp` files.
- No personal home paths or usernames in source code.

Before sending a patch, run:

```bash
agentix public-check --path .
```

If it reports anything other than "Result: public-safe candidate", do not
push — investigate first. The same check runs in CI for sanitized release
exports.

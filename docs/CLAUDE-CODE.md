# Claude Code Operating Contract for Agentix

Claude Code may help develop Agentix and Agentic NixOS, but it must operate through the Agentix safety model.

## Core rule

Claude Code must not directly activate or mutate the live NixOS system.

Claude Code may inspect, plan, and use Agentix sandbox commands. The human controls final apply and rebuild.

## Allowed commands

Claude Code may suggest or run:

```bash
agentix controller-plan --path ~/nixos-config --json
agentix controller-run "goal..." --path ~/nixos-config
agentix controller-run "goal..." --path ~/nixos-config --execute
agentix agent-loop "goal..." --path ~/nixos-config --dry-run
agentix worktree-run "goal..." --path ~/nixos-config --json
agentix worktree-run "goal..." --path ~/nixos-config --save-proposal --json
agentix proposals list --path ~/nixos-config --json
agentix audit summary --path ~/nixos-config --json
agentix self-test
uv run pytest
scripts/dev-cycle
```

## Forbidden commands

Claude Code must not run:

```bash
sudo
rebuild-nixos
nixos-rebuild switch
rm -rf
commands that read ~/.ssh or private keys
commands that directly edit /etc/nixos
commands that apply proposals without human approval
commands that push system config changes without human approval
```

## Required workflow for NixOS goals

1. Run controller-plan.
2. Run controller-run without --execute.
3. Explain the dry-run JSON.
4. Ask human approval before --execute.
5. If approved, run controller-run with --execute.
6. Save proposal only.
7. Stop before apply, rebuild, sudo, or live activation.

## Human-only steps

Only the human may run:

```bash
agentix apply-verify ...
rebuild-nixos
git commit
git push
```

## First Claude Code prompt

Use this prompt when starting Claude Code in the Agentix repo:

```text
Read docs/CLAUDE-CODE.md and docs/OPERATING.md. You are helping develop Agentix. Do not run sudo, rebuild-nixos, nixos-rebuild switch, or directly mutate /etc/nixos. For NixOS goals, only use agentix controller-plan, controller-run dry-run, and controller-run --execute after explicit approval. Start by running agentix controller-plan --path ~/nixos-config --json and summarize the safety contract.
```

## Public release safety

Private repos may contain local memory, checkpoints, and machine-specific data.

Do not publish private repo history directly. Use:

```bash
agentix export-public --path ~/projects/agentix --dest /tmp/agentix-public --yes
agentix public-check --path /tmp/agentix-public
```

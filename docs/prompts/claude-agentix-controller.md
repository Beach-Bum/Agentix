# Claude Agentix Controller Prompt

Read this before doing any work in the Agentix repository.

You are helping develop Agentix and Agentic NixOS.

## Core safety rule

You must not directly activate or mutate the live NixOS system.

You may inspect, plan, and use Agentix sandbox/controller commands.

The human controls final apply and rebuild.

## Forbidden commands

Do not run:

- sudo
- rebuild-nixos
- nixos-rebuild switch
- rm -rf

Do not directly edit:

- /etc/nixos
- ~/.ssh
- private keys
- secrets

Do not apply proposals, commit NixOS config changes, push system config changes, or rebuild without explicit human approval.

## Allowed first commands

Start by reading:

- docs/CLAUDE-CODE.md
- docs/OPERATING.md

Then run:

agentix controller-plan --path ~/nixos-config --json

Then summarize the safety contract.

## Required NixOS goal workflow

For any NixOS configuration goal:

1. Run a dry-run controller plan first:

agentix controller-run "goal..." --path ~/nixos-config

2. Summarize the JSON result.

3. Ask the human before executing.

4. Only after explicit approval, run sandbox execution:

agentix controller-run "goal..." --path ~/nixos-config --execute

5. Summarize:

- passed
- source_modified
- proposal_saved
- stops_before_apply
- stops_before_rebuild

6. Stop.

Do not run apply, rebuild, sudo, or direct live edits.

## Expected safe behavior

A safe successful execution should:

- run only in a temporary worktree
- save a proposal patch
- leave ~/nixos-config real files untouched
- stop before apply
- stop before rebuild

## Human-only steps

Only the human may run:

- agentix apply-verify ...
- rebuild-nixos
- git commit
- git push

## First action

Run:

agentix controller-plan --path ~/nixos-config --json

Then summarize the safety boundaries before doing anything else.

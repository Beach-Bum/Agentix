# Agentix

A safety-first control layer that lets LLM agents propose NixOS configuration changes without live-system access.

## Why not just use good VCS hygiene?

Tools like `jj` or disciplined Git workflows already prevent "mixing" approved and unapproved changes. Agentix solves a different problem: an LLM agent wants to change your NixOS configuration, but you don't want it anywhere near `sudo nixos-rebuild switch`.

Agentix gives the agent a sandbox (a temporary Git worktree), lets it plan and write changes there, captures the result as a reviewable patch, and stops. The agent never touches your source tree or runs privileged commands. You review the diff, apply it yourself, and rebuild.

The core loop:

```
plan -> sandbox -> propose -> verify -> human apply/rebuild
```

This isn't about version control — it's about constraining what an LLM can do to your system while still letting it be useful.

## Install

### With Nix (recommended)

Run directly:

```sh
nix run github:Beach-Bum/Agentix -- --help
```

Development shell:

```sh
nix develop github:Beach-Bum/Agentix
```

Install to your NixOS system or home-manager profile by adding the flake input:

```nix
# flake.nix
{
  inputs.agentix.url = "github:Beach-Bum/Agentix";

  # In your system or home-manager config:
  # environment.systemPackages = [ inputs.agentix.packages.${system}.default ];
}
```

### With pip/uv

```sh
pip install git+https://github.com/Beach-Bum/Agentix.git
```

Or for development:

```sh
git clone https://github.com/Beach-Bum/Agentix.git
cd Agentix
uv sync --group dev
```

## What it does today

| Version | Capability |
|---------|------------|
| v0.1 | Inspect repos, propose Nix dev shells, save patches, manual apply with audit |
| v0.2 | Sandboxed agent-loop: run a goal in a temporary Git worktree, save the diff as a proposal. Source workspace stays untouched |
| v0.3 | Controller layer: `controller-plan` describes the safety contract, `controller-run` plans and (optionally) executes a goal end-to-end with full audit, hardened source-untouched invariant, and conservative subprocess timeouts |

## Commands

```sh
# Print the safety contract for a repo
agentix controller-plan --path <repo> --json

# Dry-run a goal (no changes)
agentix controller-run "<goal>" --path <repo>

# Execute: run the goal in a temp worktree, save a proposal patch, stop
agentix controller-run "<goal>" --path <repo> --execute

# Lower-level form for scripts (--keep retains the temp worktree)
agentix worktree-run "<goal>" --path <repo> --save-proposal --json

# Single-pass agent loop
agentix agent-loop "<goal>" --path <repo>

# Review audit trail
agentix audit tail --path <repo> --json
agentix audit summary --path <repo> --json

# Check for private artifacts before publishing
agentix public-check --path <repo>
agentix export-public --path <repo> --dest <out> --yes
```

See [docs/CONTROLLER.md](docs/CONTROLLER.md) for the full flag reference.

## Safety invariants

- **Source workspace untouched.** Every run snapshots HEAD, `git diff HEAD --`, and SHA-256 of every untracked file before and after the subprocess. Any unexpected mutation exits non-zero with `error="source_workspace_mutated"`. The only allowed write is one new patch under `.agentix/proposals/`.
- **No apply, no rebuild, no sudo.** The agent stops at the saved proposal. A human runs `agentix apply-verify` and `nixos-rebuild switch`.
- **Subprocess timeout.** Default 1800s (30 min) on the inner goal subprocess (`--timeout SECONDS` to override). Timeout exits 124 with `error="timeout"`.
- **Audit log per run.** One JSON line per invocation, appended to `<repo>/.agentix/audit.jsonl` (gitignored). Inspect with `agentix audit tail` and `agentix audit summary`.

## Claude Code integration

Claude Code (and other LLM controllers) operate against the same contract. See [docs/CLAUDE-CODE.md](docs/CLAUDE-CODE.md) and [docs/prompts/claude-agentix-controller.md](docs/prompts/claude-agentix-controller.md) for the session contract.

## Docs

- [docs/OPERATING.md](docs/OPERATING.md) — operating contract and workflow
- [docs/CONTROLLER.md](docs/CONTROLLER.md) — controller commands and flags
- [docs/CLAUDE-CODE.md](docs/CLAUDE-CODE.md) — Claude Code integration

## License

MIT

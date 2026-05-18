# Agentix — Agent Rules

## Before committing

1. Run `pytest tests/ -x` — all tests must pass
2. Run `scripts/dev-cycle` if it exists
3. Check all markdown files have matched code fences (even number of ``` lines)
4. Run `agentix public-check --path .` — must report "public-safe candidate"
5. If flake.nix was changed, run `nix flake check` (on a nix-capable machine)

## Quality rules

- Do not commit broken markdown. Check code blocks are closed, tables render, links work.
- Do not commit Python syntax errors. Run `python3 -c "import ast; ast.parse(open('file.py').read())"` on changed files.
- Keep README install instructions tested and current. If you change dependencies or packaging, update the README.
- Version in `pyproject.toml` and `agentix/__init__.py` must match.

## Safety rules (non-negotiable)

- No `sudo`, `nixos-rebuild switch`, or direct `/etc/nixos` mutation from agent code
- Source workspace must stay untouched outside `.agentix/proposals/`
- All failures must exit non-zero with a specific `error=...` code

## Do not commit

- MEMORY.md, .agentix/audit.jsonl, .claude/, session transcripts
- SSH keys, API credentials, secrets
- Editor temp files, local logs

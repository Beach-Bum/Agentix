# Security Policy

Agentix is **experimental software** for safety-first agentic NixOS workflows.
It is intended for personal and research use, not for production-grade
unattended system administration.

## Intended workflow

```
plan -> sandbox -> propose -> verify -> human apply -> human rebuild
```

The agent prepares verified proposal patches and stops. Humans remain
responsible for applying patches and activating system changes. If a feature
or workflow appears to skip the human apply/rebuild step, treat it as a bug.

## Reporting a vulnerability

**Please do not open public issues for vulnerabilities or safety bypasses.**

If GitHub private vulnerability reporting is enabled on this repository,
please use it. Otherwise, contact the maintainer privately (e.g. via the
contact details on the GitHub profile). Allow a reasonable window for triage
before any disclosure.

A useful report includes:

- The exact command sequence (or test case) that triggers the issue.
- The expected behavior under the safety contract.
- The actual behavior, including any audit-log entry or JSON payload.
- Whether the issue affects the source workspace, a sandbox worktree, or the
  live system.

## Out of scope

Agentix does not claim, and is not engineered to provide:

- Production-grade sandbox isolation. The "sandbox" is a Git worktree with a
  conservative timeout and a source-snapshot integrity check, not a process
  or filesystem jail.
- Protection from a malicious local user. Agentix runs with the caller's
  privileges.
- Protection from a malicious or compromised LLM provider. The controller
  contract limits what the LLM can ask Agentix to do; it does not constrain
  what the LLM may emit.
- Unattended secure system administration. Apply and rebuild are human-only
  by design.
- Secrets management. Agentix should never read or handle secrets; if your
  workflow requires them, use a dedicated secrets tool and keep them outside
  Agentix's path.

## Boundaries that must hold

The following are non-negotiable and any bypass is a vulnerability:

- No `sudo`.
- No `nixos-rebuild switch`.
- No `rebuild-nixos`.
- No direct mutation of `/etc/nixos`.
- No SSH key or other secret access.

Reports especially welcome on issues that show:

- Controller or worktree workflows can mutate the source workspace
  unexpectedly (i.e. anything that produces `source_modified=false` while
  files outside `.agentix/proposals/` actually changed).
- A path that bypasses the proposal-review step and applies a change
  directly.
- Any way for the controller to trigger live activation
  (`apply`, `apply-verify`, `nixos-rebuild switch`, `rebuild-nixos`,
  `/etc/nixos` writes) without explicit human action.

Thanks for helping keep Agentix's safety story honest.

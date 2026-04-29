import json
from pathlib import Path


ALLOWED_COMMANDS = [
    "agentix agent-loop <goal> --path <repo> --dry-run",
    "agentix agent-loop <goal> --path <repo>",
    "agentix worktree-run <goal> --path <repo> --json",
    "agentix worktree-run <goal> --path <repo> --save-proposal --json",
    "agentix proposals list --path <repo> --json",
    "agentix audit summary --path <repo> --json",
    "agentix audit tail --path <repo> --json",
    "agentix self-test",
]

FORBIDDEN_COMMANDS = [
    "sudo",
    "nixos-rebuild switch",
    "rebuild-nixos",
    "direct /etc/nixos mutation",
    "apply without human approval",
    "git push from generated system config changes",
    "secret access",
    "ssh private key access",
]

SAFETY_BOUNDARIES = [
    "Controller may inspect and plan.",
    "Controller may run sandboxed worktree goals.",
    "Controller may save proposal patches.",
    "Controller must leave the source workspace files untouched unless using approved proposal workflows.",
    "Controller must stop before apply, rebuild, sudo, or live system activation.",
    "Human reviews proposals.",
    "Human runs apply-verify if approved.",
    "Human runs rebuild-nixos if final activation is desired.",
]


def controller_plan(path: Path) -> dict:
    return {
        "action": "controller_plan",
        "path": str(path),
        "allowed_commands": ALLOWED_COMMANDS,
        "forbidden_commands": FORBIDDEN_COMMANDS,
        "safety_boundaries": SAFETY_BOUNDARIES,
        "default_mode": "dry_run_first",
        "source_workspace_must_remain_untouched": True,
        "final_activation": "human_controlled",
        "recommended_first_command": f"agentix agent-loop \"<goal>\" --path {path} --dry-run",
    }


def print_controller_plan(path: Path, json_output: bool = False) -> int:
    plan = controller_plan(path)

    if json_output:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    print("Agentix Controller Plan")
    print()
    print(f"Path: {path}")
    print()
    print("Allowed commands:")
    for command in plan["allowed_commands"]:
        print(f"- {command}")

    print()
    print("Forbidden commands:")
    for command in plan["forbidden_commands"]:
        print(f"- {command}")

    print()
    print("Safety boundaries:")
    for boundary in plan["safety_boundaries"]:
        print(f"- {boundary}")

    print()
    print(f"Default mode: {plan['default_mode']}")
    print(f"Final activation: {plan['final_activation']}")
    print()
    print("Recommended first command:")
    print(f"  {plan['recommended_first_command']}")

    return 0

import subprocess
from pathlib import Path


def read_command(command: list[str]) -> str:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def current_system_path() -> str:
    return read_command(["readlink", "-f", "/run/current-system"])


def system_generations() -> str:
    return read_command([
        "nix-env",
        "--list-generations",
        "--profile",
        "/nix/var/nix/profiles/system",
    ])


def print_switch_plan(path: Path, host: str) -> None:
    config_dir = str(path)
    flake_ref = f"{config_dir}#{host}"

    print("Agentix Switch Plan")
    print()
    print("This command does not switch the system.")
    print("It only prints the human-controlled activation plan.")
    print()

    current = current_system_path()
    if current:
        print("Current system:")
        print(f"  {current}")
        print()

    generations = system_generations()
    if generations:
        print("System generations:")
        for line in generations.splitlines()[-5:]:
            print(f"  {line}")
        print()

    print("Recommended pre-switch verification:")
    print(f"  agentix verify --path {config_dir} --host {host}")
    print()

    print("Human-controlled switch command:")
    print(f"  sudo nixos-rebuild switch --flake {flake_ref}")
    print()

    print("Rollback command if needed:")
    print("  sudo nixos-rebuild switch --rollback")
    print()

    print("Safer normal path:")
    print(f"  cd {config_dir} && rebuild-nixos")

import difflib
import re
import subprocess
from pathlib import Path


SAFE_PACKAGE_RE = re.compile(r"^[a-zA-Z0-9_.+-]+$")

MODULE_TARGETS = {
    "devtools": "modules/devtools.nix",
    "fun": "modules/fun.nix",
    "agentic-base": "modules/agentic-base.nix",
}

FUN_PACKAGES = {
    "cowsay",
    "figlet",
    "hello",
    "lolcat",
    "fortune",
    "fortune-kind",
    "sl",
    "ponysay",
    "toilet",
}


def validate_package_name(package: str) -> None:
    if not SAFE_PACKAGE_RE.match(package):
        raise ValueError(f"Unsafe package name: {package}")


def package_exists(package: str) -> bool:
    validate_package_name(package)

    result = subprocess.run(
        ["nix", "eval", "--raw", f"nixpkgs#{package}.name"],
        text=True,
        capture_output=True,
    )

    return result.returncode == 0


def resolve_package_module(package: str, requested_module: str) -> str:
    if requested_module != "auto":
        return requested_module

    if package in FUN_PACKAGES:
        return "fun"

    return "devtools"


def find_module(path: Path, module: str) -> Path:
    if module not in MODULE_TARGETS:
        allowed = ", ".join(sorted(MODULE_TARGETS))
        raise ValueError(f"Unknown module `{module}`. Allowed modules: {allowed}, auto")

    target = path / MODULE_TARGETS[module]

    if not target.exists():
        raise FileNotFoundError(f"Expected module file: {target}")

    return target


def add_package_to_module(path: Path, package: str, module: str = "devtools") -> tuple[str, str]:
    validate_package_name(package)

    selected_module = resolve_package_module(package, module)

    if not package_exists(package):
        raise ValueError(f"Package not found in nixpkgs: {package}")

    target = find_module(path, selected_module)
    rel_target = target.relative_to(path)

    old = target.read_text(encoding="utf-8")

    package_line = f"    {package}\n"

    if package_line in old:
        raise ValueError(f"Package already appears in {rel_target}: {package}")

    marker = "  ];\n"
    if marker not in old:
        raise ValueError(f"Could not find end of environment.systemPackages list in {rel_target}.")

    new = old.replace(marker, package_line + marker, 1)

    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel_target}",
            tofile=f"b/{rel_target}",
        )
    )

    return diff, selected_module

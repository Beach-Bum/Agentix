import difflib
import re
from pathlib import Path


MODULE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def modules_dir(path: Path) -> Path:
    return path / "modules"


def list_modules(path: Path) -> list[Path]:
    directory = modules_dir(path)

    if not directory.exists():
        return []

    return sorted(directory.glob("*.nix"))


def module_name(module_path: Path) -> str:
    return module_path.stem


def validate_module_name(name: str) -> None:
    if not MODULE_NAME_RE.match(name):
        raise ValueError(f"Unsafe module name: {name}")


def find_module(path: Path, name: str) -> Path:
    candidate = modules_dir(path) / f"{name}.nix"

    if not candidate.exists():
        available = ", ".join(module_name(module) for module in list_modules(path))
        raise FileNotFoundError(f"Module not found: {name}. Available modules: {available}")

    return candidate


def extract_list_items(text: str, assignment_name: str) -> list[str]:
    pattern = re.compile(
        rf"{re.escape(assignment_name)}\s*=\s*(?:with pkgs;\s*)?\[(.*?)\];",
        re.DOTALL,
    )
    match = pattern.search(text)

    if not match:
        return []

    block = match.group(1)
    items: list[str] = []

    for raw_line in block.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        line = line.split("#", 1)[0].strip()
        line = line.rstrip(";").strip()

        if line:
            items.append(line)

    return items


def module_summary(module_path: Path) -> dict:
    text = module_path.read_text(encoding="utf-8")

    return {
        "name": module_path.stem,
        "path": str(module_path),
        "line_count": len(text.splitlines()),
        "imports": extract_list_items(text, "imports"),
        "packages": extract_list_items(text, "environment.systemPackages"),
        "enables_flakes": "experimental-features" in text and "flakes" in text,
        "uses_services": "services." in text,
        "uses_users": "users." in text,
    }


def print_modules(path: Path) -> int:
    modules = list_modules(path)

    print("Agentix Modules")
    print()
    print(f"Path: {path}")
    print()

    if not modules:
        print("No modules found.")
        return 1

    print("NixOS modules:")
    for module in modules:
        print(f"- {module_name(module)}")

    return 0


def print_module_explanation(path: Path, name: str) -> int:
    try:
        module_path = find_module(path, name)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    summary = module_summary(module_path)

    print("Agentix Module Explanation")
    print()
    print(f"Name: {summary['name']}")
    print(f"Path: {summary['path']}")
    print(f"Lines: {summary['line_count']}")
    print()

    if summary["imports"]:
        print("Imports:")
        for item in summary["imports"]:
            print(f"- {item}")
    else:
        print("Imports: none")

    print()

    if summary["packages"]:
        print("Packages:")
        for item in summary["packages"]:
            print(f"- {item}")
    else:
        print("Packages: none")

    print()
    print("Signals:")
    print(f"- enables flakes: {'yes' if summary['enables_flakes'] else 'no'}")
    print(f"- configures services: {'yes' if summary['uses_services'] else 'no'}")
    print(f"- configures users: {'yes' if summary['uses_users'] else 'no'}")

    return 0


def new_module_content(name: str, template: str = "empty") -> str:
    if template == "empty":
        return f'''{{ config, pkgs, ... }}:

{{
  # {name} module
}}
'''

    if template == "packages":
        return f'''{{ config, pkgs, ... }}:

{{
  # {name} module
  environment.systemPackages = with pkgs; [
  ];
}}
'''

    if template == "services":
        return f'''{{ config, pkgs, ... }}:

{{
  # {name} module
  # Add service configuration here.
}}
'''

    raise ValueError(f"Unknown module template: {template}")


def create_module_patch(path: Path, name: str, template: str = "empty") -> str:
    validate_module_name(name)

    module_path = modules_dir(path) / f"{name}.nix"
    agentic_base = modules_dir(path) / "agentic-base.nix"

    if module_path.exists():
        raise FileExistsError(f"Module already exists: {module_path}")

    if not agentic_base.exists():
        raise FileNotFoundError("Expected modules/agentic-base.nix")

    old_base = agentic_base.read_text(encoding="utf-8")
    import_line = f"    ./{name}.nix\n"

    if import_line in old_base:
        raise ValueError(f"Module already imported in agentic-base.nix: {name}")

    marker = "  ];\n"
    if marker not in old_base:
        raise ValueError("Could not find imports list end in modules/agentic-base.nix")

    new_base = old_base.replace(marker, import_line + marker, 1)
    module_text = new_module_content(name, template)

    base_diff = "".join(
        difflib.unified_diff(
            old_base.splitlines(keepends=True),
            new_base.splitlines(keepends=True),
            fromfile="a/modules/agentic-base.nix",
            tofile="b/modules/agentic-base.nix",
        )
    )

    module_diff = "".join(
        difflib.unified_diff(
            [],
            module_text.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/modules/{name}.nix",
        )
    )

    return base_diff + "\n" + module_diff

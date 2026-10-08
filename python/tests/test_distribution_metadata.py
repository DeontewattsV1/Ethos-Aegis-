"""Release identity, provenance and installable CLI regression contracts.

All assertions use the standard library so they run on the Python 3.10–3.12
CI matrix without adding a runtime or test-only TOML dependency.
"""

from pathlib import Path
import importlib
import re

ROOT = Path(__file__).resolve().parents[2]
IMMUNE = ROOT / "python"


def _section(document: str, section: str) -> str:
    text = document.split(f"[{section}]\n", 1)
    assert len(text) == 2, f"missing TOML section: {section}"
    return text[1].split("\n[", 1)[0]


def _project_value(path: Path, name: str) -> str:
    content = _section(path.read_text(encoding="utf-8"), "project")
    match = re.search(rf'(?m)^{re.escape(name)}\s*=\s*"([^"]+)"\s*$', content)
    assert match is not None, f"missing {name} in {path}"
    return match.group(1)


def test_python_distribution_names_are_distinct() -> None:
    """Root governance and Python immune code must not publish under one name."""
    root = ROOT / "pyproject.toml"
    immune = IMMUNE / "pyproject.toml"
    assert _project_value(root, "name") == "ethos-aegis-governance"
    assert _project_value(immune, "name") == "ethos-aegis"
    assert _project_value(root, "version") == "0.1.0"
    assert _project_value(immune, "version") == "1.0.0"
    assert _project_value(root, "requires-python") == ">=3.12"
    assert _project_value(immune, "requires-python") == ">=3.10"


def test_package_scopes_and_legacy_setup_are_explicit() -> None:
    governance = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    immune = (IMMUNE / "pyproject.toml").read_text(encoding="utf-8")
    shim = (IMMUNE / "setup.py").read_text(encoding="utf-8")
    assert 'include = ["ethos_core*", "agents*", "graph*", "simulation*"]' in governance
    assert 'include = ["ethos_aegis*", "ethos_4d*"]' in immune
    assert 'license = {text = "CC0-1.0"}' in governance
    assert 'license = {text = "MIT"}' in immune
    assert "setup()" in shim
    assert "version=" not in shim
    assert "install_requires=" not in shim
    assert "entry_points=" not in shim


def test_only_package_shipped_console_script_is_exposed() -> None:
    scripts = _section((IMMUNE / "pyproject.toml").read_text(encoding="utf-8"), "project.scripts")
    assert 'aegis-security = "ethos_aegis.security_toolkit.__main__:main"' in scripts
    assert "ethos-aegis =" not in scripts
    assert "aegis-server =" not in scripts
    assert callable(importlib.import_module("ethos_aegis.security_toolkit.__main__").main)


def test_python_package_contains_its_declared_mit_notice() -> None:
    license_text = (IMMUNE / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License\n")
    assert "Permission is hereby granted, free of charge" in license_text
    assert "copyright notice" in license_text.lower()
    root_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "CC0 1.0 Universal" in root_license

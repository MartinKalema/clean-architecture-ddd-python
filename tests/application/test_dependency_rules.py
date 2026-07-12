"""Executable Clean Architecture dependency rules."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imports_below(package: str):
    for path in (ROOT / "src" / package).rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                yield path, node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name


def test_domain_never_depends_on_outer_layers():
    forbidden = ("src.application", "src.infrastructure", "src.presentation")
    violations = [
        f"{path.relative_to(ROOT)} -> {module}"
        for path, module in _imports_below("domain")
        if module.startswith(forbidden)
    ]

    assert violations == []


def test_application_never_depends_on_delivery_or_infrastructure():
    forbidden = ("src.infrastructure", "src.presentation")
    violations = [
        f"{path.relative_to(ROOT)} -> {module}"
        for path, module in _imports_below("application")
        if module.startswith(forbidden)
    ]

    assert violations == []


def test_domain_shared_kernel_contains_only_domain_concepts():
    shared_kernel = ROOT / "src" / "domain" / "shared_kernel"
    assert not (shared_kernel / "interfaces.py").exists()

    exported = (shared_kernel / "__init__.py").read_text()
    for operational_port in (
        "ICache",
        "IConfigurationProvider",
        "IEmailService",
        "IEventDispatcher",
        "IEventHandler",
        "ILogger",
    ):
        assert operational_port not in exported

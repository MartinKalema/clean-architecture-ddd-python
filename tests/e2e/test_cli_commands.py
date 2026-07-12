"""CLI composition smoke tests.

Database behavior is covered by the migrated-PostgreSQL command-handler and
repository suites. This test deliberately does not synthesize a second schema
with ``metadata.create_all``.
"""
from click.testing import CliRunner

from src.presentation.cli.main import cli


def test_cli_exposes_catalog_commands_without_bootstrapping_infrastructure():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "add" in result.output
    assert "list" in result.output
    assert "borrow" in result.output

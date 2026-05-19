from click.testing import CliRunner

from xerodemo.cli import main


def test_cli_help() -> None:
    """Test CLI help command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "web" in result.output
    assert "auth" in result.output

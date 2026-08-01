"""Tests for the CLI commands (PLAN T4.2).

All 18 commands from SPEC §3.1.  Tests use Typer's CliRunner for
invocation isolation.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from codingkit.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Basic commands
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_output(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "CodingKit" in result.output
        assert "init" in result.output
        assert "run" in result.output
        assert "config" in result.output
        assert "session" in result.output
        assert "tool" in result.output
        assert "status" in result.output
        assert "cancel" in result.output
        assert "version" in result.output
        assert "web" in result.output


class TestVersion:
    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "CodingKit v" in result.output

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        # Typer does not have a built-in --version; this tests that it
        # doesn't crash and returns an error.
        assert result.exit_code != 0


class TestInit:
    def test_init_help(self) -> None:
        """init command exists."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize" in result.output


class TestStatus:
    def test_status(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "CodingKit Status" in result.output
        assert "idle" in result.output


class TestCancel:
    def test_cancel(self) -> None:
        result = runner.invoke(app, ["cancel"])
        assert result.exit_code == 0
        assert "No running task" in result.output


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_with_task(self) -> None:
        result = runner.invoke(app, ["run", "Write a test"])
        assert result.exit_code == 0
        assert "CodingKit" in result.output
        assert "Result" in result.output

    def test_run_empty_task(self) -> None:
        result = runner.invoke(app, ["run", ""])
        assert result.exit_code != 0

    def test_run_plan_only(self) -> None:
        result = runner.invoke(app, ["run", "--plan-only", "Write a test"])
        assert result.exit_code == 0
        assert "Plan" in result.output


# ---------------------------------------------------------------------------
# config commands
# ---------------------------------------------------------------------------


class TestConfig:
    def test_config_help(self) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "key" in result.output
        assert "method" in result.output
        assert "model" in result.output

    # config key

    def test_config_key_show_when_not_configured(self) -> None:
        """key show when no key is configured."""
        result = runner.invoke(app, ["config", "key", "show"])
        assert result.exit_code == 0
        # Should handle gracefully
        assert "configured" in result.output.lower() or "no" in result.output.lower()

    def test_config_key_delete(self) -> None:
        """key delete without confirmation."""
        result = runner.invoke(app, ["config", "key", "delete"], input="y\n")
        # Exit code can be non-zero if no key exists, that's fine
        assert "deleted" in result.output.lower() or "no" in result.output.lower()

    # config method

    def test_config_method_valid(self) -> None:
        result = runner.invoke(app, ["config", "method", "keychain"])
        assert result.exit_code == 0
        assert "keychain" in result.output

    def test_config_method_invalid(self) -> None:
        result = runner.invoke(app, ["config", "method", "invalid"])
        assert result.exit_code != 0
        assert "unsupported" in result.output.lower()

    # config model

    def test_config_model_list(self) -> None:
        result = runner.invoke(app, ["config", "model", "list"])
        assert result.exit_code == 0
        assert "claude" in result.output.lower() or "gpt" in result.output.lower()

    def test_config_model_set_valid(self) -> None:
        result = runner.invoke(app, ["config", "model", "set", "claude-sonnet-5"])
        assert result.exit_code == 0
        assert "claude-sonnet-5" in result.output

    def test_config_model_set_invalid(self) -> None:
        result = runner.invoke(app, ["config", "model", "set", "unknown-model"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# session commands
# ---------------------------------------------------------------------------


class TestSession:
    def test_session_list(self) -> None:
        result = runner.invoke(app, ["session", "list"])
        assert result.exit_code == 0
        # Should handle empty list gracefully
        assert "No sessions" in result.output or "ID" in result.output

    def test_session_show_nonexistent(self) -> None:
        result = runner.invoke(app, ["session", "show", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_session_delete_nonexistent(self) -> None:
        result = runner.invoke(app, ["session", "delete", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# tool commands
# ---------------------------------------------------------------------------


class TestTool:
    def test_tool_list(self) -> None:
        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "read_file" in result.output
        assert "write_file" in result.output
        assert "execute_command" in result.output
        assert "dangerous" in result.output.lower()

    def test_tool_enable_valid(self) -> None:
        result = runner.invoke(app, ["tool", "enable", "read_file"])
        assert result.exit_code == 0
        assert "read_file" in result.output.lower()

    def test_tool_enable_invalid(self) -> None:
        result = runner.invoke(app, ["tool", "enable", "nonexistent_tool"])
        assert result.exit_code != 0
        assert "unknown" in result.output.lower() or "not found" in result.output.lower()

    def test_tool_disable_valid(self) -> None:
        result = runner.invoke(app, ["tool", "disable", "read_file"])
        assert result.exit_code == 0
        assert "read_file" in result.output.lower()

    def test_tool_disable_invalid(self) -> None:
        result = runner.invoke(app, ["tool", "disable", "nonexistent_tool"])
        assert result.exit_code != 0
        assert "unknown" in result.output.lower() or "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# web command
# ---------------------------------------------------------------------------


class TestWeb:
    @patch("codingkit.web.server.serve")
    def test_web(self, mock_serve: Mock) -> None:
        result = runner.invoke(app, ["web", "--port", "9090"])
        assert result.exit_code == 0
        mock_serve.assert_called_once_with(port=9090)
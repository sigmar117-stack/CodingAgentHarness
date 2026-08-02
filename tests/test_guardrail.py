"""Tests for T2.2 Governance Guardrail.

Tests cover:
- Guardrail.check() — dangerous tool names, dangerous command patterns, safe commands
- ApprovalHandler — mock user input for y/n/m, timeout auto-reject
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from codingkit.core.llm_client import ToolCall
from codingkit.governance.approval import ApprovalDecision, ApprovalHandler
from codingkit.governance.guardrail import Guardrail

# ---------------------------------------------------------------------------
# Guardrail tests
# ---------------------------------------------------------------------------


class TestGuardrailCheck:
    """Guardrail.check() unit tests."""

    def setup_method(self) -> None:
        self.guardrail = Guardrail()

    # -- dangerous commands ---------------------------------------------------

    def test_dangerous_shell_command_rm_rf(self) -> None:
        """传入危险命令 Action(command="rm -rf /") -> 断言 is_dangerous=True"""
        action = ToolCall(name="execute_command", arguments={"command": "rm -rf /"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True
        assert "rm -rf" in result.risk_reason.lower() or "dangerous" in result.risk_reason.lower()

    def test_dangerous_shell_command_sudo(self) -> None:
        """传入包含 sudo 的命令 -> 断言 is_dangerous=True"""
        action = ToolCall(name="execute_command", arguments={"command": "sudo apt install nginx"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_dangerous_shell_command_dd(self) -> None:
        """传入包含 dd 的危险命令 -> 断言 is_dangerous=True"""
        action = ToolCall(name="execute_command", arguments={"command": "dd if=/dev/zero of=/dev/sda bs=1M"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_dangerous_shell_command_mkfs(self) -> None:
        """传入包含 mkfs 的命令 -> 断言 is_dangerous=True"""
        action = ToolCall(name="execute_command", arguments={"command": "mkfs.ext4 /dev/sda1"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_safe_shell_command_ls(self) -> None:
        """传入普通命令 Action(command="ls -la") -> 断言 is_dangerous=False"""
        action = ToolCall(name="execute_command", arguments={"command": "ls -la"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    def test_safe_shell_command_git_status(self) -> None:
        """传入普通 git 命令 -> 断言 is_dangerous=False"""
        action = ToolCall(name="execute_command", arguments={"command": "git status"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    # -- dangerous tool names -------------------------------------------------

    def test_dangerous_tool_delete_file(self) -> None:
        """传入危险工具 Action(name="delete_file", params={"path": "/etc"}) -> 断言 is_dangerous=True"""
        action = ToolCall(name="delete_file", arguments={"path": "/etc"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_dangerous_tool_git_operation(self) -> None:
        """传入危险工具 git_operation -> 断言 is_dangerous=True"""
        action = ToolCall(name="git_operation", arguments={"operation": "push", "remote": "origin"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_dangerous_tool_install_dependencies(self) -> None:
        """传入危险工具 install_dependencies -> 断言 is_dangerous=True"""
        action = ToolCall(name="install_dependencies", arguments={"packages": ["numpy"]})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True

    def test_safe_tool_read_file(self) -> None:
        """传入普通工具 Action(name="read_file") -> 断言 is_dangerous=False"""
        action = ToolCall(name="read_file", arguments={"path": "README.md"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    def test_safe_tool_write_file(self) -> None:
        """传入普通工具 Action(name="write_file") -> 断言 is_dangerous=False"""
        action = ToolCall(name="write_file", arguments={"path": "test.txt", "content": "hello"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    # -- risk_reason and suggested_alternative fields -------------------------

    def test_risk_reason_is_present_when_dangerous(self) -> None:
        """危险动作应包含 risk_reason 说明"""
        action = ToolCall(name="execute_command", arguments={"command": "rm -rf /"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True
        assert result.risk_reason  # non-empty string

    def test_safe_action_returns_no_reason(self) -> None:
        """安全动作 risk_reason 应为空字符串"""
        action = ToolCall(name="read_file", arguments={"path": "README.md"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False
        assert result.risk_reason == ""


# ---------------------------------------------------------------------------
# ApprovalHandler tests
# ---------------------------------------------------------------------------


class TestApprovalHandler:
    """ApprovalHandler.request_approval() unit tests."""

    def setup_method(self) -> None:
        self.handler = ApprovalHandler(timeout=timedelta(seconds=120))

    def test_approve_y(self) -> None:
        """Mock 用户输入 y -> 断言 APPROVED"""
        with patch("builtins.input", return_value="y"):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.APPROVED
        assert modified_params is None

    def test_approve_yes(self) -> None:
        """Mock 用户输入 yes -> 断言 APPROVED"""
        with patch("builtins.input", return_value="yes"):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="delete_file", arguments={"path": "/etc/passwd"}),
            )
        assert decision == ApprovalDecision.APPROVED

    def test_reject_n(self) -> None:
        """Mock 用户输入 n -> 断言 REJECTED"""
        with patch("builtins.input", return_value="n"):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.REJECTED
        assert modified_params is None

    def test_reject_no(self) -> None:
        """Mock 用户输入 no -> 断言 REJECTED"""
        with patch("builtins.input", return_value="no"):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.REJECTED

    def test_modified(self) -> None:
        """Mock 用户输入 m + 修改内容 -> 断言 MODIFIED 且返回修改后的参数"""
        with patch("builtins.input", side_effect=["m", "ls -la"]):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.MODIFIED
        assert modified_params is not None
        assert modified_params.get("command") == "ls -la"

    def test_modified_keeps_other_params(self) -> None:
        """修改后放行应保留除 command 外的其他参数"""
        with patch("builtins.input", side_effect=["m", "ls -la /safe"]):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /", "timeout": 30}),
            )
        assert decision == ApprovalDecision.MODIFIED
        assert modified_params is not None
        assert modified_params["command"] == "ls -la /safe"
        assert modified_params["timeout"] == 30  # original param preserved

    def test_empty_input_treated_as_reject(self) -> None:
        """空输入应视为否决"""
        with patch("builtins.input", return_value=""):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.REJECTED

    def test_invalid_input_retry_then_accept(self) -> None:
        """无效输入应重新提示，直到有效输入为止"""
        with patch("builtins.input", side_effect=["x", "?", "y"]):
            decision, modified_params = self.handler.request_approval(
                ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
            )
        assert decision == ApprovalDecision.APPROVED

    def test_timeout_auto_reject(self) -> None:
        """审批超时 -> 自动否决 (mock _read_with_timeout to simulate timeout)"""
        handler = ApprovalHandler(timeout=timedelta(seconds=120))

        def _timeout_result(*_args: object, **_kwargs: object) -> object:
            return ApprovalDecision.REJECTED, None

        handler._read_with_timeout = _timeout_result  # type: ignore[method-assign]
        decision, modified_params = handler.request_approval(
            ToolCall(name="execute_command", arguments={"command": "rm -rf /"}),
        )
        assert decision == ApprovalDecision.REJECTED
        assert modified_params is None

    def test_timeout_with_short_timeout(self) -> None:
        """短超时后自动否决"""
        handler = ApprovalHandler(timeout=timedelta(seconds=0.001))
        # Mock input to sleep longer than the timeout.
        with patch("builtins.input", side_effect=lambda *a: (__import__("time").sleep(0.5), "y")[1]):
            decision, modified_params = handler.request_approval(
                ToolCall(name="delete_file", arguments={"path": "/etc/hosts"}),
            )
        assert decision == ApprovalDecision.REJECTED


# ---------------------------------------------------------------------------
# Supplementary edge-case tests (T7.1)
# ---------------------------------------------------------------------------


class TestGuardrailEdgeCases:
    """Guardrail edge cases for empty / non-string inputs."""

    def setup_method(self) -> None:
        self.guardrail = Guardrail()

    def test_empty_name_and_arguments(self) -> None:
        """ToolCall with empty name/arguments → should not be dangerous."""
        action = ToolCall(name="", arguments={})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    def test_non_string_arguments_integer(self) -> None:
        """Non-string arguments (integer) → should not crash guardrail."""
        action = ToolCall(name="execute_command", arguments={"command": 123})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    def test_non_string_arguments_list(self) -> None:
        """Non-string arguments (list) → should not crash guardrail."""
        action = ToolCall(name="execute_command", arguments={"command": ["rm", "-rf", "/"]})
        result = self.guardrail.check(action)
        assert result.is_dangerous is False

    def test_suggested_safe_alternative_field(self) -> None:
        """GuardrailResult.suggested_safe_alternative is accessible and None for known dangerous patterns."""
        action = ToolCall(name="execute_command", arguments={"command": "rm -rf /"})
        result = self.guardrail.check(action)
        assert result.is_dangerous is True
        # suggested_safe_alternative is defined but not yet populated
        assert result.suggested_safe_alternative is None
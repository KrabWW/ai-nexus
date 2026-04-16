"""Tests for Claude Code hooks (pre_plan and pre_commit)."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx

from ai_nexus.hooks.pre_plan import main as pre_plan_main
from ai_nexus.hooks.pre_commit import main as pre_commit_main


@pytest.fixture
def mock_hook_input():
    """Sample hook input from Claude Code."""
    return {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "src/ai_nexus/services/example.py",
            "content": "def example_function():\n    pass",
        },
    }


@pytest.mark.asyncio
async def test_pre_plan_successful_context_injection(mock_hook_input, monkeypatch, capsys):
    """Test pre_plan hook successfully injects business context."""
    # Mock the HTTP response with business context
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "context": {
            "entities": [
                {"id": 1, "name": "订单", "description": "客户订单实体", "domain": "ecommerce"},
                {"id": 2, "name": "支付", "description": "支付方式", "domain": "ecommerce"},
            ],
            "rules": [
                {
                    "id": 1,
                    "name": "订单状态流转规则",
                    "description": "订单只能从创建流向已支付",
                    "severity": "critical",
                }
            ],
        }
    }

    async def mock_post(*args, **kwargs):
        return mock_response

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit
    mock_client.timeout = 5.0

    # Mock stdin
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_plan_main()

    captured = capsys.readouterr()
    assert "<system-reminder>" in captured.out
    assert "AI Nexus Business Context:" in captured.out
    assert "订单" in captured.out
    assert "订单状态流转规则" in captured.out
    assert "[critical]" in captured.out


@pytest.mark.asyncio
async def test_pre_plan_service_unavailable_silent_pass(mock_hook_input, monkeypatch, capsys):
    """Test pre_plan hook silently passes when service is unavailable."""
    # Mock connection error
    async def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_plan_main()

    captured = capsys.readouterr()
    # Should not output anything (silent degradation)
    assert captured.out == ""


@pytest.mark.asyncio
async def test_pre_plan_timeout_silent_pass(mock_hook_input, monkeypatch, capsys):
    """Test pre_plan hook silently passes on timeout."""
    # Mock timeout
    async def mock_post(*args, **kwargs):
        raise httpx.TimeoutException("Request timeout")

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_plan_main()

    captured = capsys.readouterr()
    # Should not output anything (silent degradation)
    assert captured.out == ""


@pytest.mark.asyncio
async def test_pre_plan_empty_input_no_error(monkeypatch, capsys):
    """Test pre_plan hook handles empty input gracefully."""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    await pre_plan_main()

    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.asyncio
async def test_pre_commit_violations_detected(mock_hook_input, monkeypatch, capsys):
    """Test pre_commit hook outputs warning when violations found."""
    # Mock HTTP response with violations
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errors": [
            {
                "rule_id": "1",
                "rule": "禁止直接删除订单",
                "description": "订单只能通过软删除方式标记为删除",
                "severity": "critical",
            }
        ],
        "warnings": [],
        "infos": [],
        "passed": False,
    }

    async def mock_post(*args, **kwargs):
        return mock_response

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit

    # Mock event recording endpoint (should fail silently)
    async def mock_event_post(*args, **kwargs):
        raise httpx.ConnectError("Event service unavailable")

    mock_client.post.side_effect = [mock_response, mock_event_post, mock_event_post]

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_commit_main()

    captured = capsys.readouterr()
    assert "⚠️ AI Nexus: Business Rule Violations Detected" in captured.err
    assert "禁止直接删除订单" in captured.err
    assert "[critical]" in captured.err


@pytest.mark.asyncio
async def test_pre_commit_no_violations_silent_pass(mock_hook_input, monkeypatch, capsys):
    """Test pre_commit hook passes silently when no violations."""
    # Mock HTTP response with no violations
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errors": [],
        "warnings": [],
        "infos": [],
        "passed": True,
    }

    async def mock_post(*args, **kwargs):
        return mock_response

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_commit_main()

    captured = capsys.readouterr()
    # Should not output anything
    assert captured.err == ""


@pytest.mark.asyncio
async def test_pre_commit_service_unavailable_silent_pass(mock_hook_input, monkeypatch, capsys):
    """Test pre_commit hook silently passes when service unavailable."""
    async def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    async def mock_enter(self):
        return self

    async def mock_exit(self, *args):
        pass

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = mock_enter
    mock_client.__aexit__ = mock_exit

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(mock_hook_input)))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await pre_commit_main()

    captured = capsys.readouterr()
    # Should not output anything (silent degradation)
    assert captured.err == ""


# Import io for StringIO
import io

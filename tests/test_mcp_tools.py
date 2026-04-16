# tests/test_mcp_tools.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from ai_nexus.main import app


def test_health_and_mcp_mount():
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200


# MCP 工具的实际测试通过 mcp_server.py 函数直接调用
async def test_search_entities_tool_returns_json():
    from ai_nexus.mcp.server import search_entities

    with patch("ai_nexus.mcp.server._get_graph_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.search_entities.return_value = []
        mock_get.return_value = mock_svc
        result = await search_entities("订单")
        data = json.loads(result)
        assert "results" in data


async def test_search_rules_tool_returns_json():
    from ai_nexus.mcp.server import search_rules

    with patch("ai_nexus.mcp.server._get_query_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.query_rules.return_value = []
        mock_get.return_value = mock_svc
        result = await search_rules("支付规则")
        data = json.loads(result)
        assert "results" in data


async def test_get_session_ctx_returns_json():
    from ai_nexus.mcp.server import get_session_ctx

    with patch("ai_nexus.mcp.server._get_query_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.query_rules.return_value = []
        mock_get.return_value = mock_svc
        result = await get_session_ctx("用户登录流程")
        data = json.loads(result)
        assert "results" in data
        assert "query" in data
        assert data["query"] == "用户登录流程"
        assert data["total"] == 0


# --- get_business_context tests ---


async def test_get_business_context_happy_path():
    from ai_nexus.mcp.server import get_business_context

    with patch("ai_nexus.mcp.server._get_graph_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.get_business_context.return_value = {
            "entities": [{"id": 1, "name": "订单"}],
            "rules": [{"id": 1, "name": "支付规则"}],
        }
        mock_get.return_value = mock_svc
        result = await get_business_context("处理订单支付", keywords=["订单", "支付"])
        data = json.loads(result)
        assert "entities" in data
        assert "rules" in data
        assert data["entities"][0]["name"] == "订单"
        assert data["rules"][0]["name"] == "支付规则"


async def test_get_business_context_empty_result():
    from ai_nexus.mcp.server import get_business_context

    with patch("ai_nexus.mcp.server._get_graph_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.get_business_context.return_value = {}
        mock_get.return_value = mock_svc
        result = await get_business_context("无关任务")
        data = json.loads(result)
        assert data == {}


async def test_get_business_context_runtime_error():
    from ai_nexus.mcp.server import get_business_context

    with patch(
        "ai_nexus.mcp.server._get_graph_service",
        side_effect=RuntimeError("Services not initialized"),
    ):
        with pytest.raises(RuntimeError, match="Services not initialized"):
            await get_business_context("任何任务")


# --- validate_against_rules tests ---


async def test_validate_against_rules_happy_path():
    from ai_nexus.mcp.server import validate_against_rules
    from ai_nexus.models.rule import Rule

    rules = [
        Rule(id=1, name="禁止直接删除", description="不可直接删除订单", domain="订单",
             severity="critical", status="approved"),
        Rule(id=2, name="软删除建议", description="建议使用软删除", domain="订单",
             severity="warning", status="approved"),
        Rule(id=3, name="日志记录", description="操作需记录日志", domain="订单",
             severity="info", status="approved"),
    ]

    with patch("ai_nexus.mcp.server._get_query_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.query_rules.return_value = rules
        mock_get.return_value = mock_svc
        result = await validate_against_rules(
            "删除订单记录", affected_entities=["订单"]
        )
        data = json.loads(result)
        assert len(data["errors"]) == 1
        assert data["errors"][0]["severity"] == "critical"
        assert len(data["warnings"]) == 1
        assert len(data["infos"]) == 1
        assert data["passed"] is False


async def test_validate_against_rules_empty_keywords_fallback():
    from ai_nexus.mcp.server import validate_against_rules
    from ai_nexus.models.rule import Rule

    rules = [
        Rule(id=1, name="支付校验", description="支付需校验金额", domain="支付",
             severity="warning", status="approved"),
    ]

    with patch("ai_nexus.mcp.server._get_query_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.query_rules.return_value = rules
        mock_get.return_value = mock_svc
        result = await validate_against_rules("修改支付流程")
        # Without affected_entities, change_description is used as the only keyword
        mock_svc.query_rules.assert_called_with("修改支付流程", limit=5)
        data = json.loads(result)
        assert len(data["warnings"]) == 1
        assert data["passed"] is True


async def test_validate_against_rules_no_approved_rules():
    from ai_nexus.mcp.server import validate_against_rules
    from ai_nexus.models.rule import Rule

    rules = [
        Rule(id=1, name="待审核规则", description="尚未审核", domain="订单",
             severity="critical", status="pending"),
    ]

    with patch("ai_nexus.mcp.server._get_query_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.query_rules.return_value = rules
        mock_get.return_value = mock_svc
        result = await validate_against_rules(
            "修改订单", affected_entities=["订单"]
        )
        data = json.loads(result)
        assert data["errors"] == []
        assert data["warnings"] == []
        assert data["infos"] == []
        assert data["passed"] is True


# --- submit_knowledge_candidate tests ---


async def test_submit_knowledge_candidate_happy_path():
    from ai_nexus.mcp.server import submit_knowledge_candidate

    mock_audit_log = AsyncMock()
    mock_audit_log.id = 42

    with patch("ai_nexus.mcp.server._get_audit_repo") as mock_get:
        mock_repo = AsyncMock()
        mock_repo.create.return_value = mock_audit_log
        mock_get.return_value = mock_repo
        result = await submit_knowledge_candidate(
            type="entity",
            data={"name": "退款", "domain": "支付"},
            source="post_task",
            confidence=0.9,
        )
        data = json.loads(result)
        assert data["status"] == "submitted"
        assert data["audit_log_id"] == 42
        assert data["type"] == "entity"
        assert data["source"] == "post_task"
        assert data["confidence"] == 0.9


async def test_submit_knowledge_candidate_runtime_error_fallback():
    from ai_nexus.mcp.server import submit_knowledge_candidate

    with patch(
        "ai_nexus.mcp.server._get_audit_repo",
        side_effect=RuntimeError("AuditRepo not initialized"),
    ):
        result = await submit_knowledge_candidate(
            type="rule",
            data={"name": "退款规则", "domain": "支付"},
            source="manual",
            confidence=0.7,
        )
        data = json.loads(result)
        assert data["status"] == "pending"
        assert data["type"] == "rule"
        assert data["source"] == "manual"
        assert data["confidence"] == 0.7

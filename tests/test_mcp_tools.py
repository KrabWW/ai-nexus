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

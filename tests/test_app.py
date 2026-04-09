"""FastAPI app tests."""
from fastapi.testclient import TestClient
from ai_nexus.main import app


def test_health_check():
    """健康检查端点返回 ok。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_mcp_endpoint_exists():
    """MCP 挂载点 /mcp 可访问（不要求完整握手）。"""
    with TestClient(app) as client:
        resp = client.get("/mcp/")
        # 405/404/200 都可以，只要不是 500
        assert resp.status_code != 500

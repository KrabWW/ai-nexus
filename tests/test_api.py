# tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_create_entity(client):
    resp = client.post("/api/entities", json={
        "name": "订单", "type": "concept", "domain": "交易"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "订单"
    assert "id" in data


def test_get_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "用户", "type": "actor", "domain": "账户"
    })
    entity_id = create_resp.json()["id"]
    resp = client.get(f"/api/entities/{entity_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "用户"


def test_get_entity_not_found(client):
    resp = client.get("/api/entities/99999")
    assert resp.status_code == 404


def test_update_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "商品", "type": "object", "domain": "库存"
    })
    entity_id = create_resp.json()["id"]
    resp = client.put(f"/api/entities/{entity_id}", json={"description": "库存商品"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "库存商品"


def test_delete_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "临时实体", "type": "t", "domain": "测试"
    })
    entity_id = create_resp.json()["id"]
    resp = client.delete(f"/api/entities/{entity_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/entities/{entity_id}")
    assert resp.status_code == 404


def test_create_rule(client):
    resp = client.post("/api/rules", json={
        "name": "禁止删单",
        "description": "订单不能物理删除",
        "domain": "交易",
        "severity": "critical",
        "status": "approved",
    })
    assert resp.status_code == 201
    assert resp.json()["severity"] == "critical"


def test_search_rules(client):
    client.post("/api/rules", json={
        "name": "支付规则X",
        "description": "支付需要校验",
        "domain": "支付",
        "severity": "warning",
        "status": "approved",
    })
    resp = client.post("/api/search", json={"query": "支付", "type": "rules"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1

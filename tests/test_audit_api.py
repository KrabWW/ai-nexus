# tests/test_audit_api.py
import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_submit_candidate_and_list_pending(client):
    # 提交候选规则
    resp = client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 999,
        "action": "submit_candidate",
        "new_value": {"name": "候选规则"},
    })
    assert resp.status_code == 201

    # 查看待审核列表
    resp = client.get("/api/audit/pending")
    assert resp.status_code == 200
    pending = resp.json()
    assert len(pending) >= 1


def test_approve_candidate(client):
    # 提交
    client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 888,
        "action": "submit_candidate",
    })
    # 审核通过
    resp = client.post("/api/audit/888/approve", json={"reviewer": "admin"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject_candidate(client):
    client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 777,
        "action": "submit_candidate",
    })
    resp = client.post("/api/audit/777/reject", json={"reviewer": "admin"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_pre_plan_hook(client):
    resp = client.post("/api/hooks/pre-plan", json={
        "task_description": "实现支付退款功能",
        "keywords": ["支付", "退款"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert "rules" in data


def test_pre_commit_hook(client):
    resp = client.post("/api/hooks/pre-commit", json={
        "change_description": "删除了 orders 表的 delete 接口",
        "affected_entities": ["订单"],
        "diff_summary": "- router.delete('/orders/{id}')",
    })
    assert resp.status_code == 200
    data = resp.json()
    # New format returns graded violations: errors, warnings, infos
    assert "errors" in data
    assert "warnings" in data
    assert "infos" in data
    assert "passed" in data

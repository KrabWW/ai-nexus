"""Tests for audit approve ingestion: approving candidates writes to knowledge graph."""

import uuid

import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _uid() -> str:
    """Short unique id to avoid collisions from prior test runs."""
    return uuid.uuid4().hex[:8]


def _submit_candidate(client: TestClient, new_value: dict) -> int:
    """Submit a candidate and return its audit log id."""
    uid = _uid()
    resp = client.post("/api/audit/candidates", json={
        "table_name": "extraction",
        "record_id": abs(hash(f"test_{uid}")) % 100000,
        "action": "submit_candidate",
        "new_value": new_value,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


class TestApproveIngestion:
    def test_approve_with_entity_candidate(self, client: TestClient) -> None:
        """Approved entity candidate appears in entities table."""
        uid = _uid()
        entity_name = f"实体-{uid}"
        domain = f"域-{uid}"

        candidate = {
            "entities": [
                {
                    "name": entity_name,
                    "type": "概念",
                    "domain": domain,
                    "confidence": 0.9,
                    "description": "审核测试用实体",
                }
            ],
            "relations": [],
            "rules": [],
        }
        audit_id = _submit_candidate(client, candidate)

        resp = client.post(f"/api/audit/{audit_id}/approve", json={"reviewer": "admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["ingested"] is not None
        assert body["ingested"]["entities_created"] == 1

        # Verify entity exists
        entities = client.get("/api/entities", params={"domain": domain}).json()["items"]
        names = [e["name"] for e in entities]
        assert entity_name in names

    def test_approve_with_rule_candidate(self, client: TestClient) -> None:
        """Approved rule candidate appears in rules table."""
        uid = _uid()
        rule_name = f"规则-{uid}"
        domain = f"规则域-{uid}"

        candidate = {
            "entities": [],
            "relations": [],
            "rules": [
                {
                    "name": rule_name,
                    "severity": "error",
                    "domain": domain,
                    "confidence": 0.85,
                    "description": "审核测试规则",
                }
            ],
        }
        audit_id = _submit_candidate(client, candidate)

        resp = client.post(f"/api/audit/{audit_id}/approve", json={"reviewer": "admin"})
        assert resp.status_code == 200
        assert resp.json()["ingested"]["rules_created"] == 1

        rules = client.get("/api/rules", params={"domain": domain}).json()["items"]
        names = [r["name"] for r in rules]
        assert rule_name in names

    def test_approve_with_mixed_candidate(self, client: TestClient) -> None:
        """All items from mixed candidate are ingested."""
        uid = _uid()
        ent_a = f"实体A-{uid}"
        ent_b = f"实体B-{uid}"
        domain = f"混合域-{uid}"

        candidate = {
            "entities": [
                {
                    "name": ent_a,
                    "type": "系统",
                    "domain": domain,
                    "confidence": 0.8,
                    "description": "A",
                },
                {
                    "name": ent_b,
                    "type": "概念",
                    "domain": domain,
                    "confidence": 0.7,
                    "description": "B",
                },
            ],
            "relations": [
                {
                    "name": f"{ent_a} → depends_on → {ent_b}",
                    "type": "depends_on",
                    "domain": domain,
                    "confidence": 0.6,
                    "description": "A depends on B",
                },
            ],
            "rules": [
                {
                    "name": f"混合规则-{uid}",
                    "severity": "warning",
                    "domain": domain,
                    "confidence": 0.75,
                    "description": "mixed rule",
                },
            ],
        }
        audit_id = _submit_candidate(client, candidate)

        resp = client.post(f"/api/audit/{audit_id}/approve", json={"reviewer": "admin"})
        assert resp.status_code == 200
        ingested = resp.json()["ingested"]
        assert ingested["entities_created"] == 2
        assert ingested["relations_created"] == 1
        assert ingested["rules_created"] == 1

    def test_approve_with_duplicate_updates(self, client: TestClient) -> None:
        """Approving duplicate entity updates instead of creating new."""
        uid = _uid()
        entity_name = f"重复实体-{uid}"
        domain = f"重复域-{uid}"

        candidate1 = {
            "entities": [
                {
                    "name": entity_name,
                    "type": "概念",
                    "domain": domain,
                    "confidence": 0.8,
                    "description": "原始描述",
                }
            ],
            "relations": [],
            "rules": [],
        }
        audit_id1 = _submit_candidate(client, candidate1)
        client.post(f"/api/audit/{audit_id1}/approve", json={"reviewer": "admin"})

        # Submit and approve a second time with updated description
        candidate2 = {
            "entities": [
                {
                    "name": entity_name,
                    "type": "概念",
                    "domain": domain,
                    "confidence": 0.9,
                    "description": "更新描述",
                }
            ],
            "relations": [],
            "rules": [],
        }
        audit_id2 = _submit_candidate(client, candidate2)
        resp = client.post(f"/api/audit/{audit_id2}/approve", json={"reviewer": "admin"})
        assert resp.status_code == 200
        ingested = resp.json()["ingested"]
        assert ingested["entities_updated"] == 1
        assert ingested["entities_created"] == 0

    def test_reject_does_not_ingest(self, client: TestClient) -> None:
        """Rejecting a candidate does NOT ingest any items."""
        uid = _uid()
        entity_name = f"拒绝实体-{uid}"
        domain = f"拒绝域-{uid}"

        candidate = {
            "entities": [
                {
                    "name": entity_name,
                    "type": "概念",
                    "domain": domain,
                    "confidence": 0.8,
                    "description": "不应出现",
                }
            ],
            "relations": [],
            "rules": [],
        }
        audit_id = _submit_candidate(client, candidate)

        resp = client.post(f"/api/audit/{audit_id}/reject", json={"reviewer": "admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert "ingested" not in body

        # Entity should NOT exist
        entities = client.get("/api/entities", params={"domain": domain}).json()["items"]
        names = [e["name"] for e in entities]
        assert entity_name not in names

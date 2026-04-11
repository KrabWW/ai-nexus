"""Tests for POST /api/cold-start endpoint."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app
from ai_nexus.models.extraction import (
    ExtractedEntity,
    ExtractionResult,
)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestColdStart:
    def test_cold_start_generates_candidates(self, client: TestClient) -> None:
        uid = _uid()
        domain = f"冷启动域-{uid}"
        result = ExtractionResult(
            entities=[
                ExtractedEntity(
                    name=f"冷启动实体-{uid}",
                    type="概念",
                    domain=domain,
                    confidence=0.8,
                    description="测试冷启动",
                )
            ],
        )

        with patch.object(
            client.app.state.extraction_service,
            "cold_start",
            new_callable=AsyncMock,
            return_value=result,
        ):
            resp = client.post("/api/cold-start", json={
                "domain": domain,
                "description": "冷启动测试业务",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["audit_id"] is not None
        assert len(body["candidates"]["entities"]) == 1
        assert f"冷启动实体-{uid}" == body["candidates"]["entities"][0]["name"]
        assert "审核页面确认" in body["message"]

    def test_cold_start_submits_to_audit_log(self, client: TestClient) -> None:
        uid = _uid()
        domain = f"审计域-{uid}"
        result = ExtractionResult(
            entities=[
                ExtractedEntity(
                    name=f"审计实体-{uid}",
                    type="概念",
                    domain=domain,
                    confidence=0.9,
                    description="审计测试",
                )
            ],
        )

        with patch.object(
            client.app.state.extraction_service,
            "cold_start",
            new_callable=AsyncMock,
            return_value=result,
        ):
            resp = client.post("/api/cold-start", json={
                "domain": domain,
                "description": "审计测试业务",
            })

        body = resp.json()
        assert body["audit_id"] is not None
        assert isinstance(body["audit_id"], int)

    def test_cold_start_with_existing_entities(self, client: TestClient) -> None:
        """Cold start passes existing entity names to the service."""
        uid = _uid()
        domain = f"已有域-{uid}"
        existing_name = f"已有实体-{uid}"

        # Create an entity in the domain
        client.post("/api/entities", json={
            "name": existing_name,
            "type": "概念",
            "domain": domain,
            "description": "已存在的实体",
        })

        mock_cold_start = AsyncMock(return_value=ExtractionResult())

        with patch.object(
            client.app.state.extraction_service,
            "cold_start",
            mock_cold_start,
        ):
            resp = client.post("/api/cold-start", json={
                "domain": domain,
                "description": "已有实体测试",
            })

        assert resp.status_code == 200
        # Verify cold_start was called with existing entity names
        mock_cold_start.assert_called_once()
        call_args = mock_cold_start.call_args
        assert call_args[0][0] == domain  # domain arg
        assert call_args[0][1] == "已有实体测试"  # description arg
        assert existing_name in call_args[0][2]  # existing_entities list

    def test_cold_start_empty_result(self, client: TestClient) -> None:
        """Cold start with empty result returns appropriate message."""
        uid = _uid()
        with patch.object(
            client.app.state.extraction_service,
            "cold_start",
            new_callable=AsyncMock,
            return_value=ExtractionResult(),
        ):
            resp = client.post("/api/cold-start", json={
                "domain": f"空域-{uid}",
                "description": "空测试",
            })
        assert resp.status_code == 200
        assert resp.json()["audit_id"] is None

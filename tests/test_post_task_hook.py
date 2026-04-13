"""Tests for the post-task hook endpoint."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ai_nexus.models.extraction import ExtractedEntity, ExtractionResult


@pytest.fixture()
def _mock_db():
    """Create a mock Database with async execute/fetchone/fetchall."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.fetchone = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.connect = AsyncMock()
    db.disconnect = AsyncMock()
    db.run_migrations = AsyncMock()
    return db


def _make_app(_mock_db: MagicMock) -> TestClient:
    """Build a FastAPI app with mocked services for testing."""
    from fastapi import FastAPI

    from ai_nexus.api.router import router
    from ai_nexus.repos.audit_repo import AuditRepo
    from ai_nexus.services.extraction_service import ExtractionService

    app = FastAPI()
    app.include_router(router)

    # Wire up app.state
    app.state.extraction_service = MagicMock(spec=ExtractionService)
    app.state.audit_repo = AuditRepo(_mock_db)

    return TestClient(app)


def test_post_task_successful_extraction(_mock_db: MagicMock) -> None:
    """Post-task with extractable knowledge creates audit log and returns candidates."""
    app = _make_app(_mock_db)

    result = ExtractionResult(entities=[
        ExtractedEntity(name="OrderService", type="系统", domain="ecommerce", confidence=0.9),
    ])
    app.app.state.extraction_service.extract = AsyncMock(return_value=result)

    # Mock: no idempotency hit, then audit log creation
    _mock_db.fetchall.return_value = []
    _mock_db.execute.return_value = MagicMock(lastrowid=42)
    _mock_db.fetchone.return_value = (
        42, "extraction", 0, "submit_candidate",
        json.dumps({"hash": hashlib.md5(b"build order service").hexdigest()}),
        json.dumps(result.model_dump()),
        "post_task_hook", None, "2026-01-01T00:00:00",
    )

    resp = app.post("/api/hooks/post-task", json={
        "task_description": "build order service",
        "change_summary": "added order CRUD endpoints",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["submitted"] is True
    assert body["audit_id"] == 42
    assert len(body["candidates"]["entities"]) == 1
    assert body["candidates"]["entities"][0]["name"] == "OrderService"


def test_post_task_no_extractable_knowledge(_mock_db: MagicMock) -> None:
    """Post-task with no extractable knowledge returns submitted=False."""
    app = _make_app(_mock_db)

    empty_result = ExtractionResult()
    app.app.state.extraction_service.extract = AsyncMock(return_value=empty_result)

    _mock_db.fetchall.return_value = []

    resp = app.post("/api/hooks/post-task", json={
        "task_description": "refactor variable names",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["submitted"] is False
    assert body["audit_id"] is None


def test_post_task_idempotency(_mock_db: MagicMock) -> None:
    """Same task_description within 5 minutes returns existing result."""
    app = _make_app(_mock_db)

    app.app.state.extraction_service.extract = AsyncMock()

    task_hash = hashlib.md5(b"build order service").hexdigest()
    cached_value = {"entities": [{"name": "OrderService"}], "relations": [], "rules": []}

    # Simulate idempotency hit
    _mock_db.fetchall.return_value = [(
        10, "extraction", 0, "submit_candidate",
        json.dumps({"hash": task_hash}),
        json.dumps(cached_value),
        "post_task_hook", None, "2026-01-01T00:00:00",
    )]

    resp = app.post("/api/hooks/post-task", json={
        "task_description": "build order service",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["submitted"] is True
    assert body["audit_id"] == 10
    assert body["idempotent"] is True
    # extract should NOT have been called
    app.app.state.extraction_service.extract.assert_not_called()

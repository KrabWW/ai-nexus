"""Tests for AuditRepo."""

import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.audit import AuditLogCreate
from ai_nexus.repos.audit_repo import AuditRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield AuditRepo(db)
    await db.disconnect()


async def test_create_and_list(repo: AuditRepo):
    log = await repo.create(AuditLogCreate(
        table_name="entities",
        record_id=1,
        action="create",
        new_value={"name": "订单"},
        reviewer="admin",
    ))
    assert log.id is not None
    logs = await repo.list_by_record("entities", 1)
    assert len(logs) == 1
    assert logs[0].action == "create"


async def test_list_pending_candidates(repo: AuditRepo):
    candidate_a = await repo.create(AuditLogCreate(
        table_name="rules", record_id=10, action="submit_candidate",
    ))
    candidate_b = await repo.create(AuditLogCreate(
        table_name="rules", record_id=11, action="submit_candidate",
    ))
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=candidate_a.id, action="approve", reviewer="admin"
    ))
    # candidate_a (id=1) has been approved; only candidate_b is still pending
    pending = await repo.list_pending()
    assert len(pending) == 1
    assert pending[0].id == candidate_b.id

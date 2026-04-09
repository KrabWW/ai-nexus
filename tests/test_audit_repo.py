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
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=10, action="submit_candidate",
    ))
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=11, action="submit_candidate",
    ))
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=10, action="approve", reviewer="admin"
    ))
    # record_id=10 has been approved; only record_id=11 is still pending
    pending = await repo.list_pending()
    assert len(pending) == 1
    assert pending[0].record_id == 11

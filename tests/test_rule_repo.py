"""Tests for RuleRepo."""

import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import RuleCreate, RuleUpdate
from ai_nexus.repos.rule_repo import RuleRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield RuleRepo(db)
    await db.disconnect()


async def test_create_and_get(repo: RuleRepo):
    rule = await repo.create(RuleCreate(
        name="禁止直接删除订单",
        description="订单只能标记取消，不能物理删除",
        domain="交易",
        severity="critical",
        status="approved",
    ))
    assert rule.id is not None
    fetched = await repo.get(rule.id)
    assert fetched is not None
    assert fetched.name == "禁止直接删除订单"


async def test_update_status(repo: RuleRepo):
    rule = await repo.create(RuleCreate(
        name="规则X", description="描述", domain="测试", status="pending"
    ))
    updated = await repo.update(rule.id, RuleUpdate(status="approved"))
    assert updated is not None
    assert updated.status == "approved"


async def test_search_by_keyword(repo: RuleRepo):
    await repo.create(RuleCreate(name="支付规则A", description="支付相关", domain="支付", status="approved"))
    await repo.create(RuleCreate(name="库存规则B", description="库存相关", domain="库存", status="approved"))
    results = await repo.search(keyword="支付")
    assert len(results) == 1


async def test_list_by_domain_and_severity(repo: RuleRepo):
    await repo.create(RuleCreate(name="R1", description="d", domain="财务", severity="critical", status="approved"))
    await repo.create(RuleCreate(name="R2", description="d", domain="财务", severity="warning", status="approved"))
    results = await repo.list(domain="财务", severity="critical")
    assert len(results) == 1
    assert results[0].severity == "critical"


async def test_delete(repo: RuleRepo):
    rule = await repo.create(RuleCreate(name="临时规则", description="d", domain="测试", status="approved"))
    assert await repo.delete(rule.id) is True
    assert await repo.get(rule.id) is None

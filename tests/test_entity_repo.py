"""Tests for EntityRepo."""

import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate, EntityUpdate
from ai_nexus.repos.entity_repo import EntityRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield EntityRepo(db)
    await db.disconnect()


async def test_create_and_get(repo: EntityRepo):
    entity = await repo.create(EntityCreate(
        name="订单", type="concept", domain="交易"
    ))
    assert entity.id is not None
    assert entity.name == "订单"

    fetched = await repo.get(entity.id)
    assert fetched is not None
    assert fetched.name == "订单"


async def test_get_nonexistent_returns_none(repo: EntityRepo):
    assert await repo.get(99999) is None


async def test_update(repo: EntityRepo):
    entity = await repo.create(EntityCreate(name="用户", type="actor", domain="账户"))
    updated = await repo.update(entity.id, EntityUpdate(description="系统用户"))
    assert updated is not None
    assert updated.description == "系统用户"


async def test_delete(repo: EntityRepo):
    entity = await repo.create(EntityCreate(name="商品", type="object", domain="库存"))
    deleted = await repo.delete(entity.id)
    assert deleted is True
    assert await repo.get(entity.id) is None


async def test_list_by_domain(repo: EntityRepo):
    await repo.create(EntityCreate(name="A", type="t", domain="财务"))
    await repo.create(EntityCreate(name="B", type="t", domain="财务"))
    await repo.create(EntityCreate(name="C", type="t", domain="其他"))
    results = await repo.list(domain="财务")
    assert len(results) == 2


async def test_search_by_keyword(repo: EntityRepo):
    await repo.create(EntityCreate(name="支付订单", type="concept", domain="支付"))
    await repo.create(EntityCreate(name="退款单", type="concept", domain="支付"))
    await repo.create(EntityCreate(name="用户账户", type="actor", domain="账户"))
    results = await repo.search(keyword="订单")
    assert len(results) == 1
    assert results[0].name == "支付订单"


async def test_get_by_ids(repo: EntityRepo):
    e1 = await repo.create(EntityCreate(name="E1", type="t", domain="测试"))
    e2 = await repo.create(EntityCreate(name="E2", type="t", domain="测试"))
    e3 = await repo.create(EntityCreate(name="E3", type="t", domain="测试"))
    results = await repo.get_by_ids([e1.id, e3.id])
    assert len(results) == 2
    ids = {r.id for r in results}
    assert e1.id in ids
    assert e3.id in ids

"""Tests for RelationRepo."""

import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo


@pytest.fixture
async def repos():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    entity_repo = EntityRepo(db)
    relation_repo = RelationRepo(db)
    # 创建两个实体供关系使用
    e1 = await entity_repo.create(EntityCreate(name="订单", type="concept", domain="交易"))
    e2 = await entity_repo.create(EntityCreate(name="用户", type="actor", domain="交易"))
    yield relation_repo, e1, e2
    await db.disconnect()


async def test_create_and_get(repos):
    rel_repo, e1, e2 = repos
    rel = await rel_repo.create(RelationCreate(
        source_entity_id=e1.id,
        relation_type="belongs_to",
        target_entity_id=e2.id,
    ))
    assert rel.id is not None
    fetched = await rel_repo.get(rel.id)
    assert fetched is not None
    assert fetched.relation_type == "belongs_to"


async def test_get_by_entity(repos):
    rel_repo, e1, e2 = repos
    await rel_repo.create(RelationCreate(
        source_entity_id=e1.id, relation_type="rel_a", target_entity_id=e2.id
    ))
    results = await rel_repo.get_by_source(e1.id)
    assert len(results) == 1
    results = await rel_repo.get_by_target(e2.id)
    assert len(results) == 1


async def test_delete(repos):
    rel_repo, e1, e2 = repos
    rel = await rel_repo.create(RelationCreate(
        source_entity_id=e1.id, relation_type="rel_b", target_entity_id=e2.id
    ))
    assert await rel_repo.delete(rel.id) is True
    assert await rel_repo.get(rel.id) is None

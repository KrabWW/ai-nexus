# tests/test_graph_service.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.models.rule import RuleCreate
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService


@pytest.fixture
async def svc():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    entity_repo = EntityRepo(db)
    relation_repo = RelationRepo(db)
    rule_repo = RuleRepo(db)
    service = GraphService(entity_repo, relation_repo, rule_repo)
    yield service, entity_repo, relation_repo, rule_repo
    await db.disconnect()


async def test_search_entities_by_keyword(svc):
    service, entity_repo, _, _ = svc
    await entity_repo.create(EntityCreate(name="支付订单", type="concept", domain="支付"))
    await entity_repo.create(EntityCreate(name="用户账户", type="actor", domain="账户"))
    results = await service.search_entities("支付")
    assert len(results) == 1
    assert results[0].name == "支付订单"


async def test_search_rules_by_keyword(svc):
    service, _, _, rule_repo = svc
    await rule_repo.create(RuleCreate(
        name="禁止直接删单", description="订单只能标记", domain="交易", status="approved"
    ))
    results = await service.search_rules("删单")
    assert len(results) == 1


async def test_get_neighbors(svc):
    """get_neighbors 返回与指定实体直接相连的实体。"""
    service, entity_repo, relation_repo, _ = svc
    order = await entity_repo.create(EntityCreate(name="订单", type="concept", domain="交易"))
    user = await entity_repo.create(EntityCreate(name="用户", type="actor", domain="交易"))
    await relation_repo.create(RelationCreate(
        source_entity_id=order.id, relation_type="owned_by", target_entity_id=user.id
    ))
    neighbors = await service.get_neighbors(order.id)
    assert any(n.id == user.id for n in neighbors)


async def test_get_business_context(svc):
    """get_business_context 返回实体列表和规则列表。"""
    service, entity_repo, _, rule_repo = svc
    await entity_repo.create(EntityCreate(name="退款单", type="concept", domain="退款"))
    await rule_repo.create(RuleCreate(
        name="退款规则", description="退款须72h内", domain="退款", status="approved"
    ))
    ctx = await service.get_business_context("退款处理", keywords=["退款"])
    assert len(ctx["entities"]) >= 1
    assert len(ctx["rules"]) >= 1


async def test_fallback_search(svc):
    """fallback_search 用 LIKE 降级查询规则。"""
    service, _, _, rule_repo = svc
    await rule_repo.create(RuleCreate(
        name="库存警戒线", description="低于10件须补货", domain="库存", status="approved"
    ))
    results = await service.fallback_search("库存", domain=None)
    assert len(results) >= 1

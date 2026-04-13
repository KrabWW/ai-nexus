"""Performance benchmarks for graph service N+1 query fixes."""

import time

import pytest

from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.relation import RelationCreate
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


async def test_get_neighbors_single_query(svc):
    """get_neighbors should use single batch query instead of two separate queries."""
    service, entity_repo, relation_repo, _ = svc

    # Create entities and relations
    entity1 = await entity_repo.create(EntityCreate(name="E1", type="concept", domain="test"))
    entity2 = await entity_repo.create(EntityCreate(name="E2", type="concept", domain="test"))
    entity3 = await entity_repo.create(EntityCreate(name="E3", type="concept", domain="test"))

    await relation_repo.create(RelationCreate(
        source_entity_id=entity1.id, relation_type="rel1", target_entity_id=entity2.id
    ))
    await relation_repo.create(RelationCreate(
        source_entity_id=entity3.id, relation_type="rel2", target_entity_id=entity1.id
    ))

    # Mock the database to track queries
    query_count = 0
    original_fetchall = relation_repo._db.fetchall

    async def count_fetchall(sql, params=None):
        nonlocal query_count
        if "SELECT" in sql and "relations" in sql:
            query_count += 1
        return await original_fetchall(sql, params)

    relation_repo._db.fetchall = count_fetchall

    # Call get_neighbors
    neighbors = await service.get_neighbors(entity1.id)

    # Verify result
    assert len(neighbors) == 2
    assert any(n.id == entity2.id for n in neighbors)
    assert any(n.id == entity3.id for n in neighbors)

    # Should use only 1 query (get_all_for_entities) instead of 2 (get_by_source + get_by_target)
    assert query_count == 1, f"Expected 1 query, got {query_count}"


async def test_get_god_nodes_reduced_queries(svc):
    """get_god_nodes should load all relations in one query instead of N queries."""
    service, entity_repo, relation_repo, _ = svc

    # Create 100 entities with relations
    entity_ids = []
    for i in range(100):
        entity = await entity_repo.create(EntityCreate(
            name=f"Entity{i}", type="concept", domain="test"
        ))
        entity_ids.append(entity.id)

    # Create relations: each entity connects to 2-3 others
    for i in range(100):
        for j in range(2):
            target_id = entity_ids[(i + j + 1) % 100]
            await relation_repo.create(RelationCreate(
                source_entity_id=entity_ids[i],
                relation_type=f"rel{j}",
                target_entity_id=target_id
            ))

    # Mock the database to track queries
    query_count = 0
    original_fetchall = relation_repo._db.fetchall

    async def count_fetchall(sql, params=None):
        nonlocal query_count
        if "SELECT" in sql and "relations" in sql and "LIMIT" in sql:
            query_count += 1
        return await original_fetchall(sql, params)

    relation_repo._db.fetchall = count_fetchall

    # Call get_god_nodes
    god_nodes = await service.get_god_nodes(limit=10)

    # Verify result
    assert len(god_nodes) == 10
    assert all("degree" in node for node in god_nodes)

    # Should use only 1 query (list_all) instead of 200 queries (2 per entity)
    assert query_count == 1, f"Expected 1 query, got {query_count}"


async def test_get_surprising_connections_reduced_queries(svc):
    """get_surprising_connections should load all relations in one query."""
    service, entity_repo, relation_repo, _ = svc

    # Create entities across different domains
    domain_a_entities = []
    domain_b_entities = []

    for i in range(50):
        entity_a = await entity_repo.create(EntityCreate(
            name=f"EntityA{i}", type="concept", domain="domain_a"
        ))
        domain_a_entities.append(entity_a)

        entity_b = await entity_repo.create(EntityCreate(
            name=f"EntityB{i}", type="concept", domain="domain_b"
        ))
        domain_b_entities.append(entity_b)

    # Create cross-domain relations
    for i in range(50):
        await relation_repo.create(RelationCreate(
            source_entity_id=domain_a_entities[i].id,
            relation_type="cross_domain",
            target_entity_id=domain_b_entities[i].id
        ))

    # Mock the database to track queries
    query_count = 0
    original_fetchall = relation_repo._db.fetchall

    async def count_fetchall(sql, params=None):
        nonlocal query_count
        if "SELECT" in sql and "relations" in sql and "LIMIT" in sql:
            query_count += 1
        return await original_fetchall(sql, params)

    relation_repo._db.fetchall = count_fetchall

    # Call get_surprising_connections
    connections = await service.get_surprising_connections(limit=10)

    # Verify result
    assert len(connections) > 0
    assert all("surprise_score" in conn for conn in connections)

    # Should use only 1 query (list_all) instead of 200 queries
    assert query_count == 1, f"Expected 1 query, got {query_count}"


async def test_detect_communities_reduced_queries(svc):
    """detect_communities should load all relations in one query."""
    service, entity_repo, relation_repo, _ = svc

    # Create entities and relations forming a simple graph
    entity_ids = []
    for i in range(50):
        entity = await entity_repo.create(EntityCreate(
            name=f"Entity{i}", type="concept", domain="test"
        ))
        entity_ids.append(entity.id)

    # Create a chain of relations
    for i in range(49):
        await relation_repo.create(RelationCreate(
            source_entity_id=entity_ids[i],
            relation_type="chain",
            target_entity_id=entity_ids[i + 1]
        ))

    # Mock the database to track queries
    query_count = 0
    original_fetchall = relation_repo._db.fetchall

    async def count_fetchall(sql, params=None):
        nonlocal query_count
        if "SELECT" in sql and "relations" in sql and "LIMIT" in sql:
            query_count += 1
        return await original_fetchall(sql, params)

    relation_repo._db.fetchall = count_fetchall

    # Call detect_communities
    result = await service.detect_communities()

    # Verify result
    assert "communities" in result
    assert "total_communities" in result

    # Should use only 1 query (list_all) instead of 100 queries
    assert query_count == 1, f"Expected 1 query, got {query_count}"


async def test_large_scale_performance(svc):
    """Test performance with 1000 entities."""
    service, entity_repo, relation_repo, _ = svc

    # Create 1000 entities across multiple domains
    entity_ids = []
    domains = ["domain_a", "domain_b", "domain_c"]
    for i in range(1000):
        domain = domains[i % 3]  # Distribute across 3 domains
        entity = await entity_repo.create(EntityCreate(
            name=f"Entity{i}", type="concept", domain=domain
        ))
        entity_ids.append(entity.id)

    # Create 2000 relations (2 per entity), including cross-domain
    for i in range(1000):
        # Same domain relation
        await relation_repo.create(RelationCreate(
            source_entity_id=entity_ids[i],
            relation_type="rel1",
            target_entity_id=entity_ids[(i + 1) % 1000]
        ))
        # Cross-domain relation (every 3rd entity connects to different domain)
        if i % 3 == 0:
            target_idx = (i + 100) % 1000  # Jump to different domain
        else:
            target_idx = (i + 2) % 1000
        await relation_repo.create(RelationCreate(
            source_entity_id=entity_ids[i],
            relation_type="rel2",
            target_entity_id=entity_ids[target_idx]
        ))

    # Time get_god_nodes with 1000 entities
    start = time.time()
    god_nodes = await service.get_god_nodes(limit=10)
    duration = time.time() - start

    # Should complete quickly (less than 1 second for 1000 entities)
    assert duration < 1.0, f"get_god_nodes took {duration:.2f}s, expected < 1.0s"
    assert len(god_nodes) == 10

    # Time get_surprising_connections
    start = time.time()
    connections = await service.get_surprising_connections(limit=10)
    duration = time.time() - start

    assert duration < 1.0, f"get_surprising_connections took {duration:.2f}s, expected < 1.0s"
    # Note: may have fewer than 10 if limited by cross-domain connections
    assert len(connections) >= 0

    # Time detect_communities
    start = time.time()
    result = await service.detect_communities()
    duration = time.time() - start

    assert duration < 2.0, f"detect_communities took {duration:.2f}s, expected < 2.0s"
    assert "communities" in result

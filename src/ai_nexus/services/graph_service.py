"""GraphService — 知识图谱查询（图遍历 + 业务上下文组装）。"""

from collections import deque

from ai_nexus.models.entity import Entity
from ai_nexus.models.rule import Rule
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo


class GraphService:
    def __init__(
        self,
        entity_repo: EntityRepo,
        relation_repo: RelationRepo,
        rule_repo: RuleRepo,
    ) -> None:
        self._entities = entity_repo
        self._relations = relation_repo
        self._rules = rule_repo

    async def search_entities(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Entity]:
        return await self._entities.search(query, domain=domain, limit=limit)

    async def search_rules(
        self,
        query: str,
        domain: str | None = None,
        severity: str | None = None,
        limit: int = 10,
    ) -> list[Rule]:
        return await self._rules.search(query, domain=domain, severity=severity, limit=limit)

    async def get_neighbors(self, entity_id: int) -> list[Entity]:
        """返回与 entity_id 直接相连的所有实体（出边 + 入边）。"""
        out_rels = await self._relations.get_by_source(entity_id)
        in_rels = await self._relations.get_by_target(entity_id)
        neighbor_ids = (
            {r.target_entity_id for r in out_rels}
            | {r.source_entity_id for r in in_rels}
        )
        neighbor_ids.discard(entity_id)
        if not neighbor_ids:
            return []
        return await self._entities.get_by_ids(list(neighbor_ids))

    async def shortest_path(self, from_id: int, to_id: int) -> list[Entity]:
        """使用 BFS 查找两个实体之间的最短路径（返回实体列表）。"""
        if from_id == to_id:
            entity = await self._entities.get(from_id)
            return [entity] if entity else []

        # BFS 遍历
        queue = deque([from_id])
        visited = {from_id}
        parent: dict[int, int | None] = {from_id: None}
        found = False

        while queue and not found:
            current = queue.popleft()
            if current == to_id:
                found = True
                break

            # 获取邻居
            out_rels = await self._relations.get_by_source(current)
            in_rels = await self._relations.get_by_target(current)
            neighbors = (
                {r.target_entity_id for r in out_rels}
                | {r.source_entity_id for r in in_rels}
            )
            neighbors.discard(current)

            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = current
                    queue.append(neighbor)

        if not found:
            return []

        # 重建路径
        path_ids = []
        current = to_id
        while current is not None:
            path_ids.append(current)
            current = parent.get(current)  # type: ignore
        path_ids.reverse()

        # 批量获取实体
        return await self._entities.get_by_ids(path_ids)

    async def get_by_ids(self, ids: list[int]) -> list[Rule]:
        return await self._rules.get_by_ids(ids)

    async def get_business_context(
        self,
        task_description: str,
        keywords: list[str] | None = None,
    ) -> dict:
        """组装业务上下文：搜索相关实体 + 规则。"""
        search_terms = keywords or [task_description]
        entities: list[Entity] = []
        rules: list[Rule] = []
        seen_entity_ids: set[int] = set()
        seen_rule_ids: set[int] = set()

        for term in search_terms:
            for e in await self._entities.search(term, limit=5):
                if e.id not in seen_entity_ids:
                    entities.append(e)
                    seen_entity_ids.add(e.id)
            for r in await self._rules.search(term, limit=5):
                if r.id not in seen_rule_ids:
                    rules.append(r)
                    seen_rule_ids.add(r.id)

        return {
            "task": task_description,
            "entities": [e.model_dump() for e in entities],
            "rules": [r.model_dump() for r in rules],
        }

    async def fallback_search(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Rule]:
        """降级：SQLite LIKE 查询规则（mem0 不可用时使用）。"""
        return await self._rules.search(query, domain=domain, limit=limit)

    async def get_god_nodes(self, limit: int = 10) -> list[dict]:
        """Identify highest-degree nodes in the graph (connection hubs).

        Args:
            limit: Maximum number of god nodes to return

        Returns:
            List of dicts with entity details and degree counts:
            [
                {
                    "entity": {...},  # entity details
                    "degree": 15,      # total connections (in + out)
                    "in_degree": 7,    # incoming connections
                    "out_degree": 8    # outgoing connections
                },
                ...
            ]
        """
        # Get all entities
        entities = await self._entities.list(limit=10000)

        # Count degrees for each entity
        degree_map: dict[int, dict[str, int]] = {}

        for entity in entities:
            degree_map[entity.id] = {"in": 0, "out": 0, "total": 0}

        # Count relations
        all_relations = []
        for entity in entities:
            out_rels = await self._relations.get_by_source(entity.id)
            in_rels = await self._relations.get_by_target(entity.id)
            all_relations.extend(out_rels)
            all_relations.extend(in_rels)

        for rel in all_relations:
            if rel.source_entity_id in degree_map:
                degree_map[rel.source_entity_id]["out"] += 1
                degree_map[rel.source_entity_id]["total"] += 1
            if rel.target_entity_id in degree_map:
                degree_map[rel.target_entity_id]["in"] += 1
                degree_map[rel.target_entity_id]["total"] += 1

        # Build result sorted by total degree
        results = []
        for entity in entities:
            if entity.id in degree_map:
                stats = degree_map[entity.id]
                if stats["total"] > 0:  # Only include entities with connections
                    results.append({
                        "entity": entity.model_dump(),
                        "degree": stats["total"],
                        "in_degree": stats["in"],
                        "out_degree": stats["out"],
                    })

        # Sort by degree descending and limit
        results.sort(key=lambda x: x["degree"], reverse=True)
        return results[:limit]

    async def get_surprising_connections(self, limit: int = 10) -> list[dict]:
        """Find unexpected cross-domain correlations.

        Identifies entity pairs that are connected but belong to different domains.
        Scores by: domain_distance × relation_count × entity_importance.

        Args:
            limit: Maximum number of surprising connections to return

        Returns:
            List of dicts with connection details and surprise scores:
            [
                {
                    "source_entity": {...},
                    "target_entity": {...},
                    "source_domain": "domain1",
                    "target_domain": "domain2",
                    "relation_count": 3,
                    "surprise_score": 15.5,
                    "relation_types": ["related_to", "depends_on"]
                },
                ...
            ]
        """
        # Get all entities grouped by domain
        entities = await self._entities.list(limit=10000)
        entities_by_domain: dict[str, list[Entity]] = {}
        for entity in entities:
            if entity.domain not in entities_by_domain:
                entities_by_domain[entity.domain] = []
            entities_by_domain[entity.domain].append(entity)

        # Get domain list for distance calculation
        domains = list(entities_by_domain.keys())
        domain_index = {d: i for i, d in enumerate(domains)}

        # Calculate entity degrees for importance scoring
        degree_map: dict[int, int] = {}
        for entity in entities:
            out_rels = await self._relations.get_by_source(entity.id)
            in_rels = await self._relations.get_by_target(entity.id)
            degree_map[entity.id] = len(out_rels) + len(in_rels)

        # Find cross-domain connections
        connections: list[dict] = []
        seen_pairs: set[tuple[int, int]] = set()

        for entity in entities:
            out_rels = await self._relations.get_by_source(entity.id)
            in_rels = await self._relations.get_by_target(entity.id)

            # Check outgoing connections
            for rel in out_rels:
                pair = tuple(sorted((entity.id, rel.target_entity_id)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                target_entity = await self._entities.get(rel.target_entity_id)
                if target_entity and entity.domain != target_entity.domain:
                    # Calculate domain distance (absolute index difference)
                    domain_dist = abs(
                        domain_index.get(entity.domain, 0) -
                        domain_index.get(target_entity.domain, 0)
                    ) + 1  # Minimum distance of 1

                    # Calculate importance (average degree)
                    importance = (degree_map.get(entity.id, 0) +
                                  degree_map.get(target_entity.id, 0)) / 2

                    # Count relations between this pair
                    pair_rels = out_rels + [
                        r for r in in_rels
                        if r.source_entity_id == rel.target_entity_id
                    ]
                    relation_count = len(pair_rels)

                    # Calculate surprise score
                    surprise_score = domain_dist * relation_count * (importance + 1)

                    connections.append({
                        "source_entity": entity.model_dump(),
                        "target_entity": target_entity.model_dump(),
                        "source_domain": entity.domain,
                        "target_domain": target_entity.domain,
                        "relation_count": relation_count,
                        "surprise_score": round(surprise_score, 2),
                        "relation_types": list({r.relation_type for r in pair_rels}),
                    })

        # Sort by surprise score descending and limit
        connections.sort(key=lambda x: x["surprise_score"], reverse=True)
        return connections[:limit]

    async def detect_communities(self, resolution: float = 1.0) -> dict:
        """Detect communities using the Leiden algorithm.

        Partitions the graph into communities of densely connected nodes
        based on graph topology, without using embeddings.

        Args:
            resolution: Resolution parameter for community detection.
                       Higher values lead to more, smaller communities.
                       Range: 0.1 to 10.0, default 1.0

        Returns:
            Dict with community assignments:
            {
                "communities": [
                    {
                        "id": 0,
                        "size": 5,
                        "entities": [{...}, ...]
                    },
                    ...
                ],
                "entity_community_map": {entity_id: community_id, ...},
                "total_communities": 3,
                "modularity": 0.45
            }
        """
        try:
            import igraph as ig
        except ImportError:
            # igraph not available, return empty result
            return {
                "communities": [],
                "entity_community_map": {},
                "total_communities": 0,
                "modularity": 0.0,
                "error": "igraph library not available",
            }

        # Get all entities and relations
        entities = await self._entities.list(limit=10000)

        # Build entity ID to index mapping for igraph
        entity_ids = [e.id for e in entities]
        entity_id_to_index = {eid: i for i, eid in enumerate(entity_ids)}

        # Build edges list for igraph
        edges = []
        seen_edges: set[tuple[int, int]] = set()

        for entity in entities:
            out_rels = await self._relations.get_by_source(entity.id)
            in_rels = await self._relations.get_by_target(entity.id)

            # Add edges from outgoing relations
            for rel in out_rels:
                edge = tuple(sorted((entity.id, rel.target_entity_id)))
                if edge not in seen_edges and rel.target_entity_id in entity_id_to_index:
                    seen_edges.add(edge)
                    edges.append((
                        entity_id_to_index[edge[0]],
                        entity_id_to_index[edge[1]],
                    ))

            # Add edges from incoming relations
            for rel in in_rels:
                edge = tuple(sorted((rel.source_entity_id, entity.id)))
                if edge not in seen_edges and rel.source_entity_id in entity_id_to_index:
                    seen_edges.add(edge)
                    edges.append((
                        entity_id_to_index[edge[0]],
                        entity_id_to_index[edge[1]],
                    ))

        if not edges:
            return {
                "communities": [],
                "entity_community_map": {},
                "total_communities": 0,
                "modularity": 0.0,
                "error": "No edges found in graph",
            }

        # Create igraph
        g = ig.Graph(n=len(entities), edges=edges, directed=False)

        # Run Leiden community detection
        try:
            partition = g.community_leiden(resolution_parameter=resolution)
        except Exception:
            # Fallback to louvain if leiden fails
            partition = g.community_multilevel()

        # Build community results
        communities: list[dict] = []
        entity_community_map: dict[int, int] = {}

        for community_id, member_indices in enumerate(partition):
            community_entities = []
            for idx in member_indices:
                entity = entities[idx]
                entity_community_map[entity.id] = community_id
                community_entities.append(entity.model_dump())

            communities.append({
                "id": community_id,
                "size": len(community_entities),
                "entities": community_entities,
            })

        # Sort communities by size descending
        communities.sort(key=lambda x: x["size"], reverse=True)

        return {
            "communities": communities,
            "entity_community_map": entity_community_map,
            "total_communities": len(communities),
            "modularity": round(partition.quality("modularity"), 4),
        }

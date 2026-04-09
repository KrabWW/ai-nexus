"""GraphService — 知识图谱查询（图遍历 + 业务上下文组装）。"""

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

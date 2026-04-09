"""QueryService — 统一查询入口，内部自动路由。"""

from ai_nexus.models.rule import Rule
from ai_nexus.proxy.mem0_proxy import Mem0Proxy
from ai_nexus.services.graph_service import GraphService


class QueryService:
    def __init__(self, graph_service: GraphService, mem0_proxy: Mem0Proxy) -> None:
        self._graph = graph_service
        self._mem0 = mem0_proxy

    async def query_rules(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Rule]:
        """统一规则查询，自动路由：
        1. 图遍历（关键词命中）→ 直接返回
        2. mem0 语义检索（模糊匹配）→ 回查 SQLite
        3. 降级：SQLite LIKE
        """
        results = await self._graph.search_rules(query, domain=domain, limit=limit)
        if results:
            return results

        if await self._mem0.is_available():
            ids = await self._mem0.search(query, limit=limit)
            if ids:
                return await self._graph.get_by_ids(ids)

        return await self._graph.fallback_search(query, domain=domain, limit=limit)

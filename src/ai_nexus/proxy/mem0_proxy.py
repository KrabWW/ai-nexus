"""Mem0Proxy — 通过 httpx 代理调用 mem0 REST API。"""

import logging

import httpx

logger = logging.getLogger(__name__)


class Mem0Proxy:
    """代理 mem0 REST API，暴露 is_available + search。"""

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 3.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def is_available(self) -> bool:
        """检查 mem0 服务是否可达。"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def search(self, query: str, limit: int = 10) -> list[int]:
        """在 mem0 中语义搜索，返回命中的 record_id 列表。

        mem0 search API 预期返回格式：
        {"results": [{"id": <int>, "score": <float>}, ...]}

        如果 mem0 不可达，返回空列表（由上层降级处理）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/search",
                    json={"query": query, "limit": limit},
                )
                if resp.status_code != 200:
                    logger.warning("mem0 search returned %d", resp.status_code)
                    return []
                data = resp.json()
                return [r["id"] for r in data.get("results", [])]
        except Exception as e:
            logger.warning("mem0 search failed: %s", e)
            return []

# tests/test_query_service.py
from unittest.mock import AsyncMock

import pytest

from ai_nexus.models.rule import Rule
from ai_nexus.services.query_service import QueryService


def _make_rule(id: int, name: str) -> Rule:
    return Rule(id=id, name=name, description="d", domain="测试", status="approved")


@pytest.fixture
def mocks():
    graph_svc = AsyncMock()
    mem0_proxy = AsyncMock()
    return graph_svc, mem0_proxy


async def test_returns_graph_results_when_found(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = [_make_rule(1, "支付规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("支付")
    assert len(results) == 1
    graph_svc.search_rules.assert_called_once()
    mem0_proxy.is_available.assert_not_called()


async def test_falls_through_to_mem0_when_graph_empty(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = []
    mem0_proxy.is_available.return_value = True
    mem0_proxy.search.return_value = [42]
    graph_svc.get_by_ids.return_value = [_make_rule(42, "库存规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("库存")
    assert len(results) == 1
    assert results[0].id == 42


async def test_fallback_to_like_when_mem0_unavailable(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = []
    mem0_proxy.is_available.return_value = False
    graph_svc.fallback_search.return_value = [_make_rule(99, "退款规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("退款")
    assert len(results) == 1
    assert results[0].id == 99
    graph_svc.fallback_search.assert_called_once()

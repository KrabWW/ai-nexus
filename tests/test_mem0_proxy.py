# tests/test_mem0_proxy.py
from unittest.mock import AsyncMock, patch

import pytest

from ai_nexus.proxy.mem0_proxy import Mem0Proxy


@pytest.fixture
def proxy():
    return Mem0Proxy(base_url="http://localhost:8080")


async def test_is_available_when_up(proxy: Mem0Proxy):
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        assert await proxy.is_available() is True


async def test_is_available_when_down(proxy: Mem0Proxy):
    import httpx

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("refused")):
        assert await proxy.is_available() is False


async def test_search_returns_ids(proxy: Mem0Proxy):
    from unittest.mock import Mock
    mock_resp = Mock()
    mock_resp.status_code = 200
    # httpx.Response.json() is synchronous, not async
    mock_resp.json.return_value = {
        "results": [
            {"id": 10, "score": 0.9},
            {"id": 20, "score": 0.7},
        ]
    }
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        ids = await proxy.search("支付规则", limit=5)
        assert ids == [10, 20]


async def test_search_returns_empty_when_down(proxy: Mem0Proxy):
    import httpx

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        ids = await proxy.search("任意查询")
        assert ids == []

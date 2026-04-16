"""Tests for extraction/extraction_service.py.

Covers: successful extraction, empty input, API failure, missing API key,
malformed JSON, and cold_start flow.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.models.extraction import ExtractionResult

# Module path for patching
_MOD = "ai_nexus.extraction.extraction_service"


@pytest.fixture
def mock_client():
    """Build a mock Anthropic client with a fluent API."""
    client = MagicMock()
    response = MagicMock()
    return client, response


def _set_response(response: MagicMock, text: str) -> None:
    """Configure mock response to return *text*."""
    response.content = [MagicMock(text=text)]
    return response


class TestExtractionServiceInit:
    def test_stores_repos(self) -> None:
        svc = ExtractionService(
            entity_repo="e",
            relation_repo="r",
            rule_repo="ru",
            api_key="key",
        )
        assert svc._entity_repo == "e"
        assert svc._relation_repo == "r"
        assert svc._rule_repo == "ru"

    def test_default_model_and_tokens(self) -> None:
        svc = ExtractionService(api_key="key")
        assert svc._model == "claude-sonnet-4-20250514"
        assert svc._max_tokens == 4096

    def test_custom_model_and_tokens(self) -> None:
        svc = ExtractionService(
            api_key="key", model="claude-opus-4-20250514", max_tokens=8192
        )
        assert svc._model == "claude-opus-4-20250514"
        assert svc._max_tokens == 8192


class TestExtract:
    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_successful_extraction(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "entities": [
                            {
                                "name": "ICU排班",
                                "type": "系统",
                                "domain": "医疗排班",
                                "confidence": 0.95,
                                "description": "重症监护室排班系统",
                            }
                        ],
                        "relations": [],
                        "rules": [
                            {
                                "name": "ICU需要24小时值班",
                                "severity": "error",
                                "domain": "医疗排班",
                                "confidence": 0.9,
                                "description": "必须24小时值班",
                            }
                        ],
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.extract("新增ICU排班模块，支持24小时值班规则")

        assert not result.is_empty()
        assert len(result.entities) == 1
        assert result.entities[0].name == "ICU排班"
        assert len(result.rules) == 1
        assert result.rules[0].severity == "error"

    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_empty_irrelevant_input(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [
            MagicMock(text='{"entities": [], "relations": [], "rules": []}')
        ]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.extract("TODO: refactor later")

        assert result.is_empty()

    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_api_failure_returns_empty(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.extract("Some text")

        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_empty(self) -> None:
        svc = ExtractionService()  # no api_key
        result = await svc.extract("Some text")

        assert result.is_empty()

    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_malformed_json_returns_empty(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="This is not valid JSON")]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.extract("Some text")

        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self) -> None:
        svc = ExtractionService(api_key="test-key")
        assert (await svc.extract("")).is_empty()
        assert (await svc.extract("   \n\t  ")).is_empty()

    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_domain_hint_in_prompt(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [
            MagicMock(text='{"entities": [], "relations": [], "rules": []}')
        ]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        await svc.extract("some text", domain_hint="医疗排班")

        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "医疗排班" in prompt


class TestColdStart:
    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_cold_start_returns_result(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "entities": [
                            {
                                "name": "订单",
                                "type": "概念",
                                "domain": "电商",
                                "confidence": 0.7,
                                "description": "用户下单",
                            }
                        ],
                        "relations": [],
                        "rules": [],
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_resp
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.cold_start("电商", "电商平台业务", ["用户", "商品"])

        assert not result.is_empty()
        assert len(result.entities) == 1
        assert result.entities[0].name == "订单"

    @pytest.mark.asyncio
    async def test_cold_start_missing_api_key(self) -> None:
        svc = ExtractionService()
        result = await svc.cold_start("电商", "电商平台业务")
        assert result.is_empty()

    @pytest.mark.asyncio
    @patch(f"{_MOD}.anthropic.Anthropic")
    async def test_cold_start_api_failure(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("fail")
        mock_anthropic.return_value = mock_client

        svc = ExtractionService(api_key="test-key")
        result = await svc.cold_start("电商", "desc")
        assert result.is_empty()

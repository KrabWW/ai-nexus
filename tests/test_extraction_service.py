"""Tests for ExtractionService (extraction/ version).

Tests cover:
- Text with business knowledge -> structured output
- Text without business knowledge -> empty result
- Domain hint parameter affects extraction
- Malformed API response -> graceful fallback
- Prompt template file exists
- cold_start flow
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_nexus.extraction.extraction_service import (
    ExtractionService,
    _parse_response,
)
from ai_nexus.models.extraction import ExtractionResult


class TestExtractionService:
    """Test suite for ExtractionService."""

    def test_init_with_api_key(self) -> None:
        """Test service initialization with API key."""
        service = ExtractionService(api_key="test-key")
        assert service._model == "claude-sonnet-4-20250514"
        assert service._api_key == "test-key"

    def test_init_with_custom_model(self) -> None:
        """Test service initialization with custom model."""
        service = ExtractionService(api_key="test-key", model="claude-opus-4-20250514")
        assert service._model == "claude-opus-4-20250514"

    def test_init_with_repos(self) -> None:
        """Test service stores repo references."""
        svc = ExtractionService(
            entity_repo="e",
            relation_repo="r",
            rule_repo="ru",
            api_key="key",
        )
        assert svc._entity_repo == "e"
        assert svc._relation_repo == "r"
        assert svc._rule_repo == "ru"

    def test_init_default_model_and_tokens(self) -> None:
        """Test default model and max_tokens."""
        svc = ExtractionService(api_key="key")
        assert svc._model == "claude-sonnet-4-20250514"
        assert svc._max_tokens == 4096

    def test_init_custom_model_and_tokens(self) -> None:
        """Test custom model and max_tokens."""
        svc = ExtractionService(api_key="key", model="claude-opus-4-20250514", max_tokens=8192)
        assert svc._model == "claude-opus-4-20250514"
        assert svc._max_tokens == 8192

    @pytest.mark.asyncio
    async def test_extract_empty_text_returns_empty(self) -> None:
        """Test extraction with empty input text."""
        service = ExtractionService(api_key="test-key")

        result = await service.extract("")
        assert result.is_empty()

        result = await service.extract("   \n\t  ")
        assert result.is_empty()

        result = await service.extract("  ")
        assert result.is_empty()

    @pytest.mark.asyncio
    async def test_extract_missing_api_key_returns_empty(self) -> None:
        """Test extraction without API key returns empty result."""
        service = ExtractionService()
        result = await service.extract("Some text")
        assert result.is_empty()

    @pytest.mark.asyncio
    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_business_knowledge(self, mock_anthropic: MagicMock) -> None:
        """Test extraction from text containing business knowledge."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''```json
{
  "entities": [
    {
      "name": "ICU排班",
      "type": "系统",
      "domain": "医疗排班",
      "confidence": 0.95,
      "description": "重症监护室排班系统"
    }
  ],
  "relations": [
    {
      "name": "ICU排班 → requires → 24小时值班",
      "type": "requires",
      "domain": "医疗排班",
      "confidence": 0.9,
      "description": "ICU需要24小时值班医生"
    }
  ],
  "rules": [
    {
      "name": "ICU需要24小时值班医生",
      "severity": "error",
      "domain": "医疗排班",
      "confidence": 0.95,
      "description": "重症监护室必须保证24小时有医生值班"
    }
  ]
}
```''')]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("feat: 新增ICU排班模块，支持24小时值班规则")

        assert not result.is_empty()
        assert len(result.entities) == 1
        assert result.entities[0].name == "ICU排班"
        assert result.entities[0].type == "系统"
        assert len(result.relations) == 1
        assert len(result.rules) == 1
        assert result.rules[0].severity == "error"

    @pytest.mark.asyncio
    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_without_business_knowledge(self, mock_anthropic: MagicMock) -> None:
        """Test extraction from text with only technical details returns empty result."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''```json
{"entities": [], "relations": [], "rules": []}
```''')]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("TODO: refactor this function later")

        assert result.is_empty()
        assert result.count_total() == 0

    @pytest.mark.asyncio
    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_domain_hint(self, mock_anthropic: MagicMock) -> None:
        """Test that domain_hint is included in the prompt and affects extraction."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''```json
{
  "entities": [
    {
      "name": "排班规则",
      "type": "概念",
      "domain": "医疗排班",
      "confidence": 0.85,
      "description": "医生排班的相关规则"
    }
  ],
  "relations": [],
  "rules": []
}
```''')]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("排班系统需要支持三班倒", domain_hint="医疗排班")

        # Verify domain hint was used
        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "医疗排班" in prompt

        # Verify extracted items have the domain
        assert len(result.entities) == 1
        assert result.entities[0].domain == "医疗排班"

    @pytest.mark.asyncio
    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_malformed_json(self, mock_anthropic: MagicMock) -> None:
        """Test graceful fallback when API returns malformed JSON."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("Some text")

        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    @pytest.mark.asyncio
    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_api_error(self, mock_anthropic: MagicMock) -> None:
        """Test graceful fallback when API call fails."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("Some text")

        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    def test_parse_response_with_json_code_block(self) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        response_text = '''```json
{
  "entities": [
    {
      "name": "测试实体",
      "type": "概念",
      "domain": "test",
      "confidence": 0.8,
      "description": "测试"
    }
  ],
  "relations": [],
  "rules": []
}
```'''
        result = _parse_response(response_text, "test")

        assert len(result.entities) == 1
        assert result.entities[0].name == "测试实体"

    def test_parse_response_with_plain_json(self) -> None:
        """Test parsing plain JSON without markdown wrapping."""
        response_text = '{"entities": [], "relations": [], "rules": []}'
        result = _parse_response(response_text)

        assert result.is_empty()

    def test_prompt_template_file_exists(self) -> None:
        """Test that the prompt template file exists and has required content."""
        prompts_dir = Path(__file__).resolve().parent.parent / "src" / "ai_nexus" / "prompts"
        prompt_file = prompts_dir / "extraction_prompt.md"
        assert prompt_file.exists(), f"Prompt file not found: {prompt_file}"
        content = prompt_file.read_text(encoding="utf-8")
        assert "实体" in content or "Entities" in content
        assert "关系" in content or "Relations" in content
        assert "规则" in content or "Rules" in content

    def test_cold_start_prompt_template_file_exists(self) -> None:
        """Test that the cold_start prompt template file exists."""
        prompts_dir = Path(__file__).resolve().parent.parent / "src" / "ai_nexus" / "prompts"
        prompt_file = prompts_dir / "cold_start_prompt.md"
        assert prompt_file.exists(), f"Cold start prompt file not found: {prompt_file}"

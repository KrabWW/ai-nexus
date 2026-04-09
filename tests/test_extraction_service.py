"""Tests for ExtractionService.

Tests cover:
- Text with business knowledge → structured output
- Text without business knowledge → empty result
- Domain hint parameter affects extraction
- Malformed API response → graceful fallback
"""

from unittest.mock import MagicMock, patch

from ai_nexus.extraction.extraction_service import EXTRACTION_PROMPT, ExtractionService
from ai_nexus.models.extraction import (
    ExtractionResult,
)


class TestExtractionService:
    """Test suite for ExtractionService."""

    def test_init_with_api_key(self) -> None:
        """Test service initialization with API key."""
        service = ExtractionService(api_key="test-key")
        assert service._model == "claude-sonnet-4-20250514"

    def test_init_with_custom_model(self) -> None:
        """Test service initialization with custom model."""
        service = ExtractionService(api_key="test-key", model="claude-opus-4-20250514")
        assert service._model == "claude-opus-4-20250514"

    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_business_knowledge(self, mock_anthropic: MagicMock) -> None:
        """Test extraction from text containing business knowledge."""
        # Mock Claude API response
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

    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_without_business_knowledge(self, mock_anthropic: MagicMock) -> None:
        """Test extraction from text with only technical details returns empty result."""
        # Mock Claude API response with empty arrays
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

    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_malformed_json(self, mock_anthropic: MagicMock) -> None:
        """Test graceful fallback when API returns malformed JSON."""
        # Mock Claude API response with invalid JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("Some text")

        # Should return empty result instead of raising
        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_api_error(self, mock_anthropic: MagicMock) -> None:
        """Test graceful fallback when API call fails."""
        mock_client = MagicMock()
        # Mock an exception directly without using anthropic.APIError
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic.return_value = mock_client

        service = ExtractionService(api_key="test-key")
        result = await service.extract("Some text")

        # Should return empty result instead of raising
        assert isinstance(result, ExtractionResult)
        assert result.is_empty()

    @patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic")
    async def test_extract_with_empty_text(self, mock_anthropic: MagicMock) -> None:
        """Test extraction with empty input text."""
        service = ExtractionService(api_key="test-key")

        # Empty string
        result = await service.extract("")
        assert result.is_empty()

        # Whitespace only
        result = await service.extract("   \n\t  ")
        assert result.is_empty()

        # None-like
        result = await service.extract("  ")
        assert result.is_empty()

        # Verify API was not called
        mock_anthropic.return_value.messages.create.assert_not_called()

    def test_parse_response_with_json_code_block(self) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        service = ExtractionService(api_key="test-key")
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
        result = service._parse_response(response_text, "test")

        assert len(result.entities) == 1
        assert result.entities[0].name == "测试实体"

    def test_parse_response_with_plain_json(self) -> None:
        """Test parsing plain JSON without markdown wrapping."""
        service = ExtractionService(api_key="test-key")
        response_text = '{"entities": [], "relations": [], "rules": []}'
        result = service._parse_response(response_text)

        assert result.is_empty()

    def test_extract_sync_method(self) -> None:
        """Test synchronous extract method."""
        with patch("ai_nexus.extraction.extraction_service.anthropic.Anthropic") as mock_anthropic:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='''```json
{
  "entities": [
    {
      "name": "同步测试",
      "type": "概念",
      "domain": "test",
      "confidence": 0.7,
      "description": "测试同步方法"
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
            result = service.extract_sync("测试文本")

            assert len(result.entities) == 1
            assert result.entities[0].name == "同步测试"

    def test_prompt_template_exists(self) -> None:
        """Test that EXTRACTION_PROMPT template is defined."""
        assert EXTRACTION_PROMPT
        assert "{text}" in EXTRACTION_PROMPT
        assert "{domain_hint_section}" in EXTRACTION_PROMPT
        assert "实体" in EXTRACTION_PROMPT
        assert "关系" in EXTRACTION_PROMPT
        assert "规则" in EXTRACTION_PROMPT

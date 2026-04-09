"""ExtractionService — AI-powered knowledge extraction using Claude API.

Provides stateless extraction of business entities, relations, and rules
from arbitrary text input using Anthropic's Claude API.
"""

import json
import logging

import anthropic

from ai_nexus.models.extraction import (
    ExtractedEntity,
    ExtractedItem,
    ExtractedRelation,
    ExtractedRule,
    ExtractionResult,
    SourceType,
)

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个业务知识提取专家。请从以下文本中提取所有业务相关的实体、关系和规则。

## 提取要求

### 实体 (Entities)
提取所有业务实体，类型包括：人物、地点、机构、概念、系统
每个实体需要：
- name: 实体名称
- type: 实体类型（人物/地点/机构/概念/系统）
- domain: 业务领域
- confidence: 置信度（0-1之间的小数）
- description: 详细说明

### 关系 (Relations)
提取实体间的关系，包括方向和关系类型
每个关系需要：
- name: 格式为 "源实体 → 关系类型 → 目标实体"
- type: 关系类型
- domain: 业务领域
- confidence: 置信度（0-1之间的小数）
- description: 详细说明

### 规则 (Rules)
提取所有业务规则和约束
每个规则需要：
- name: 规则名称
- severity: 严重程度（error/warning/info/critical）
- domain: 业务领域
- confidence: 置信度（0-1之间的小数）
- description: 规则详细说明
{domain_hint_section}

## 输出格式
严格输出 JSON，格式如下：
```json
{{
  "entities": [
    {{
      "name": "实体名称",
      "type": "概念",
      "domain": "业务领域",
      "confidence": 0.9,
      "description": "详细说明"
    }}
  ],
  "relations": [
    {{
      "name": "源实体 → 关系类型 → 目标实体",
      "type": "关系类型",
      "domain": "业务领域",
      "confidence": 0.8,
      "description": "详细说明"
    }}
  ],
  "rules": [
    {{
      "name": "规则名称",
      "severity": "error",
      "domain": "业务领域",
      "confidence": 0.95,
      "description": "规则详细说明"
    }}
  ]
}}
```

如果文本中不包含业务知识（只有技术实现细节、代码注释、或无关内容），返回空数组：
```json
{{"entities": [], "relations": [], "rules": []}}
```

## 待提取文本
{text}
"""


class ExtractionService:
    """Service for extracting business knowledge from text using Claude API.

    This service is stateless and can be safely reused across requests.
    All extraction logic is handled by the Claude API with structured prompts.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        """Initialize the extraction service.

        Args:
            api_key: Anthropic API key for Claude access
            model: Claude model to use for extraction (default: claude-sonnet-4-20250514)
        """
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def extract(self, text: str, domain_hint: str | None = None) -> ExtractionResult:
        """Extract business knowledge from the given text.

        Args:
            text: The input text to extract knowledge from
            domain_hint: Optional business domain hint to improve extraction accuracy

        Returns:
            ExtractionResult containing extracted entities, relations, and rules.
            Returns empty result if no business knowledge is found or if parsing fails.
        """
        if not text or not text.strip():
            return ExtractionResult()

        # Build prompt with optional domain hint
        domain_hint_section = ""
        if domain_hint:
            domain_hint_section = (
                f"\n\n### 领域提示\n本文本属于「{domain_hint}」领域，"
                f"提取时请优先考虑该领域的专业术语和规则。"
            )

        prompt = EXTRACTION_PROMPT.format(
            text=text,
            domain_hint_section=domain_hint_section,
        )

        try:
            # Call Claude API
            message = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract response text
            response_text = message.content[0].text

            # Parse JSON response
            return self._parse_response(response_text, domain_hint)

        except anthropic.APIError as e:
            logger.warning("Claude API error during extraction: %s", e)
            return ExtractionResult()
        except json.JSONDecodeError as e:
            logger.warning("Failed to decode JSON from Claude response: %s", e)
            return ExtractionResult()
        except Exception as e:
            logger.error("Unexpected error during extraction: %s", e)
            return ExtractionResult()

    @staticmethod
    def _determine_source_type(confidence: float) -> SourceType:
        """Determine source type based on confidence score.

        Args:
            confidence: AI confidence score (0.0 to 1.0)

        Returns:
            EXTRACTED for high confidence (>= 0.75)
            INFERRED for medium confidence (>= 0.5)
            AMBIGUOUS for low confidence (< 0.5)
        """
        if confidence >= 0.75:
            return SourceType.EXTRACTED
        if confidence >= 0.5:
            return SourceType.INFERRED
        return SourceType.AMBIGUOUS

    def _parse_response(
        self,
        response_text: str,
        domain_hint: str | None = None,
    ) -> ExtractionResult:
        """Parse Claude's JSON response into an ExtractionResult.

        Attempts to fix common JSON issues before parsing.
        Returns empty result if parsing fails.

        Args:
            response_text: Raw text response from Claude API
            domain_hint: Optional domain to use as default

        Returns:
            Parsed ExtractionResult or empty result on failure
        """
        try:
            # Try to extract JSON from markdown code blocks
            json_text = response_text.strip()
            if json_text.startswith("```json"):
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif json_text.startswith("```"):
                json_text = json_text.split("```")[1].split("```")[0].strip()

            data = json.loads(json_text)

            # Validate and build ExtractionResult
            entities = []
            for e in data.get("entities", []):
                conf = float(e.get("confidence", 0.5))
                entities.append(
                    ExtractedEntity(
                        name=e.get("name", ""),
                        type=e.get("type", "概念"),
                        domain=e.get("domain", domain_hint or "general"),
                        confidence=conf,
                        source_type=self._determine_source_type(conf),
                        description=e.get("description", ""),
                    )
                )

            relations = []
            for r in data.get("relations", []):
                conf = float(r.get("confidence", 0.5))
                # Create ExtractedRelation, parsing name format if present
                item = ExtractedItem(
                    name=r.get("name", ""),
                    type=r.get("type", r.get("relation_type", "related_to")),
                    domain=r.get("domain", domain_hint or "general"),
                    confidence=conf,
                    source_type=self._determine_source_type(conf),
                    description=r.get("description", ""),
                )
                relations.append(ExtractedRelation.from_name_format(item.name, item))

            rules = []
            for r in data.get("rules", []):
                conf = float(r.get("confidence", 0.5))
                rules.append(
                    ExtractedRule(
                        name=r.get("name", ""),
                        severity=r.get("severity", "warning"),
                        domain=r.get("domain", domain_hint or "general"),
                        confidence=conf,
                        source_type=self._determine_source_type(conf),
                        description=r.get("description", ""),
                        conditions=r.get("conditions"),
                    )
                )

            return ExtractionResult(entities=entities, relations=relations, rules=rules)

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(
                "Failed to parse extraction response: %s. Response: %s",
                e,
                response_text[:200],
            )
            return ExtractionResult()

    def extract_sync(self, text: str, domain_hint: str | None = None) -> ExtractionResult:
        """Synchronous version of extract for non-async contexts.

        Args:
            text: The input text to extract knowledge from
            domain_hint: Optional business domain hint

        Returns:
            ExtractionResult containing extracted knowledge
        """
        if not text or not text.strip():
            return ExtractionResult()

        # Build prompt with optional domain hint
        domain_hint_section = ""
        if domain_hint:
            domain_hint_section = (
                f"\n\n### 领域提示\n本文本属于「{domain_hint}」领域，"
                f"提取时请优先考虑该领域的专业术语和规则。"
            )

        prompt = EXTRACTION_PROMPT.format(
            text=text,
            domain_hint_section=domain_hint_section,
        )

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text
            return self._parse_response(response_text, domain_hint)

        except anthropic.APIError as e:
            logger.warning("Claude API error during extraction: %s", e)
            return ExtractionResult()
        except json.JSONDecodeError as e:
            logger.warning("Failed to decode JSON from Claude response: %s", e)
            return ExtractionResult()
        except Exception as e:
            logger.error("Unexpected error during extraction: %s", e)
            return ExtractionResult()

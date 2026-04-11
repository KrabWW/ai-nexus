"""ExtractionService — AI-powered knowledge extraction using Claude API.

Loads prompt templates from markdown files and calls Anthropic Claude
to extract business entities, relations, and rules from text.
"""

import json
import logging
from pathlib import Path

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

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON."""
    stripped = text.strip()
    if stripped.startswith("```json"):
        return stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    if stripped.startswith("```"):
        return stripped.split("```", 1)[1].split("```", 1)[0].strip()
    return stripped


def _extract_text(message: object) -> str:
    """Extract text from an Anthropic message, skipping ThinkingBlocks."""
    for block in message.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _determine_source_type(confidence: float) -> SourceType:
    """Map confidence score to SourceType."""
    if confidence >= 0.75:
        return SourceType.EXTRACTED
    if confidence >= 0.5:
        return SourceType.INFERRED
    return SourceType.AMBIGUOUS


def _parse_response(
    response_text: str,
    domain_hint: str | None = None,
) -> ExtractionResult:
    """Parse Claude JSON response into ExtractionResult."""
    try:
        data = json.loads(_strip_json_fences(response_text))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse extraction response: %s", response_text[:200])
        return ExtractionResult()

    try:
        entities = [
            ExtractedEntity(
                name=e.get("name", ""),
                type=e.get("type", "概念"),
                domain=e.get("domain", domain_hint or "general"),
                confidence=float(e.get("confidence", 0.5)),
                source_type=_determine_source_type(float(e.get("confidence", 0.5))),
                description=e.get("description", ""),
            )
            for e in data.get("entities", [])
        ]

        relations = []
        for r in data.get("relations", []):
            conf = float(r.get("confidence", 0.5))
            item = ExtractedItem(
                name=r.get("name", ""),
                type=r.get("type", r.get("relation_type", "related_to")),
                domain=r.get("domain", domain_hint or "general"),
                confidence=conf,
                source_type=_determine_source_type(conf),
                description=r.get("description", ""),
            )
            relations.append(ExtractedRelation.from_name_format(item.name, item))

        rules = [
            ExtractedRule(
                name=r.get("name", ""),
                severity=r.get("severity", "warning"),
                domain=r.get("domain", domain_hint or "general"),
                confidence=float(r.get("confidence", 0.5)),
                source_type=_determine_source_type(float(r.get("confidence", 0.5))),
                description=r.get("description", ""),
                conditions=r.get("conditions"),
            )
            for r in data.get("rules", [])
        ]

        return ExtractionResult(entities=entities, relations=relations, rules=rules)

    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Failed to build extraction models: %s", exc)
        return ExtractionResult()


class ExtractionService:
    """Service for extracting business knowledge from text via Claude API.

    Stores repository references for later use by ingest_candidate()
    and manages LLM configuration for extraction calls.
    """

    def __init__(
        self,
        entity_repo: object | None = None,
        relation_repo: object | None = None,
        rule_repo: object | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._entity_repo = entity_repo
        self._relation_repo = relation_repo
        self._rule_repo = rule_repo
        self._api_key = api_key or ""
        self._base_url = base_url or ""
        self._model = model or "claude-sonnet-4-20250514"
        self._max_tokens = max_tokens or 4096

    def _get_client(self) -> anthropic.Anthropic | None:
        """Return an Anthropic client, or None if no API key is configured."""
        if not self._api_key:
            return None
        kwargs: dict = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return anthropic.Anthropic(**kwargs)

    async def extract(
        self, text: str, domain_hint: str | None = None
    ) -> ExtractionResult:
        """Extract business knowledge from text using Claude.

        Args:
            text: Input text to extract knowledge from.
            domain_hint: Optional business domain for better accuracy.

        Returns:
            ExtractionResult with entities, relations, and rules.
            Returns empty result on missing key, API failure, or bad JSON.
        """
        if not text or not text.strip():
            return ExtractionResult()

        client = self._get_client()
        if client is None:
            logger.warning("No API key configured; returning empty extraction result")
            return ExtractionResult()

        prompt_template = _load_prompt("extraction_prompt.md")
        prompt = prompt_template.replace("{{DOMAIN_HINT}}", domain_hint or "").replace(
            "{{TEXT}}", text
        )

        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = _extract_text(message)
            return _parse_response(response_text, domain_hint)
        except Exception as exc:
            logger.warning("Extraction API call failed: %s", exc)
            return ExtractionResult()

    async def cold_start(
        self,
        domain: str,
        description: str,
        existing_entities: list | None = None,
    ) -> ExtractionResult:
        """Generate an initial knowledge framework for a new domain.

        Args:
            domain: Business domain name.
            description: Domain description for context.
            existing_entities: Optional list of existing entity names.

        Returns:
            ExtractionResult with suggested entities, relations, and rules.
        """
        client = self._get_client()
        if client is None:
            logger.warning("No API key configured; returning empty cold-start result")
            return ExtractionResult()

        prompt_template = _load_prompt("cold_start_prompt.md")
        existing_str = (
            json.dumps(existing_entities, ensure_ascii=False)
            if existing_entities
            else "[]"
        )
        prompt = (
            prompt_template.replace("{{DOMAIN}}", domain)
            .replace("{{DESCRIPTION}}", description)
            .replace("{{EXISTING_ENTITIES}}", existing_str)
        )

        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = _extract_text(message)
            return _parse_response(response_text, domain)
        except Exception as exc:
            logger.warning("Cold-start API call failed: %s", exc)
            return ExtractionResult()

    async def ingest_candidate(self, candidate_data: dict) -> dict:
        """Ingest an approved candidate into the knowledge graph.

        Parses candidate_data as an ExtractionResult and upserts entities,
        rules, and relations into their respective repos.

        Args:
            candidate_data: Dict matching ExtractionResult schema with
                entities, relations, and rules lists.

        Returns:
            Summary dict with counts of created/updated items and their IDs.
        """
        result = ExtractionResult.model_validate(candidate_data)
        summary: dict = {
            "entities_created": 0,
            "entities_updated": 0,
            "rules_created": 0,
            "rules_updated": 0,
            "relations_created": 0,
            "entity_ids": [],
            "rule_ids": [],
        }

        # --- Entities ---
        if self._entity_repo is not None:
            for ent in result.entities:
                existing = await self._entity_repo.search(ent.name, domain=ent.domain, limit=10)
                exact = [e for e in existing if e.name == ent.name]
                if exact:
                    entity = exact[0]
                    if ent.description:
                        from ai_nexus.models.entity import EntityUpdate
                        await self._entity_repo.update(
                            entity.id,
                            EntityUpdate(description=ent.description),
                        )
                    summary["entities_updated"] += 1
                    summary["entity_ids"].append(entity.id)
                else:
                    from ai_nexus.models.entity import EntityCreate
                    created = await self._entity_repo.create(
                        EntityCreate(
                            name=ent.name,
                            type=ent.type,
                            description=ent.description,
                            domain=ent.domain,
                            status="approved",
                            source="extraction",
                        )
                    )
                    summary["entities_created"] += 1
                    summary["entity_ids"].append(created.id)

        # --- Rules ---
        if self._rule_repo is not None:
            for rule in result.rules:
                existing = await self._rule_repo.search(rule.name, domain=rule.domain, limit=10)
                exact = [r for r in existing if r.name == rule.name]
                if exact:
                    r = exact[0]
                    from ai_nexus.models.rule import RuleUpdate
                    await self._rule_repo.update(
                        r.id,
                        RuleUpdate(
                            description=rule.description,
                            severity=rule.severity,
                        ),
                    )
                    summary["rules_updated"] += 1
                    summary["rule_ids"].append(r.id)
                else:
                    from ai_nexus.models.rule import RuleCreate
                    created = await self._rule_repo.create(
                        RuleCreate(
                            name=rule.name,
                            description=rule.description,
                            domain=rule.domain,
                            severity=rule.severity,
                            conditions=rule.conditions,
                            status="approved",
                            source="extraction",
                            confidence=rule.confidence,
                        )
                    )
                    summary["rules_created"] += 1
                    summary["rule_ids"].append(created.id)

        # --- Relations ---
        if self._relation_repo is not None and self._entity_repo is not None:
            for rel in result.relations:
                # Parse source/target from name if not already set
                source_name = rel.source_name
                target_name = rel.target_name
                relation_type = rel.relation_type
                if not source_name and " → " in rel.name:
                    parts = rel.name.split(" → ")
                    if len(parts) == 3:
                        source_name, relation_type, target_name = parts

                if not source_name or not target_name:
                    continue

                src_entities = await self._entity_repo.search(
                    source_name, domain=rel.domain, limit=10
                )
                src_exact = [e for e in src_entities if e.name == source_name]
                tgt_entities = await self._entity_repo.search(
                    target_name, domain=rel.domain, limit=10
                )
                tgt_exact = [e for e in tgt_entities if e.name == target_name]
                if src_exact and tgt_exact:
                    from ai_nexus.models.relation import RelationCreate
                    await self._relation_repo.create(
                        RelationCreate(
                            source_entity_id=src_exact[0].id,
                            relation_type=relation_type or rel.relation_type or rel.type,
                            target_entity_id=tgt_exact[0].id,
                            description=rel.description,
                            status="approved",
                            source="extraction",
                        )
                    )
                    summary["relations_created"] += 1

        return summary

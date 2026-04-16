"""ExtractionService — AI-powered knowledge extraction using Claude API.

Loads prompt templates from markdown files and calls Anthropic Claude
to extract business entities, relations, and rules from text.
"""

import asyncio
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
            rel = ExtractedRelation.from_name_format(item.name, item)
            # Override domains if explicitly provided in the response
            if "source_domain" in r:
                rel.source_domain = r["source_domain"]
            if "target_domain" in r:
                rel.target_domain = r["target_domain"]
            relations.append(rel)

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

    _RETRYABLE_ERRORS = (
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
    )

    async def _call_llm(self, prompt: str, *, max_retries: int = 3) -> str | None:
        """Call Claude API with exponential backoff retry.

        Retries on transient errors (connection, timeout, rate limit, server).
        Returns response text or None on persistent failure.
        """
        client = self._get_client()
        if client is None:
            return None

        for attempt in range(max_retries):
            try:
                message = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _extract_text(message)
            except self._RETRYABLE_ERRORS as exc:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "LLM call failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "LLM call failed after %d attempts: %s", max_retries, exc,
                    )
            except Exception as exc:
                logger.error("Non-retryable LLM error: %s", exc)
                break
        return None

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

        prompt_template = _load_prompt("extraction_prompt.md")
        prompt = prompt_template.replace("{{DOMAIN_HINT}}", domain_hint or "").replace(
            "{{TEXT}}", text
        )

        response_text = await self._call_llm(prompt)
        if response_text is None:
            return ExtractionResult()
        return _parse_response(response_text, domain_hint)

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

        response_text = await self._call_llm(prompt)
        if response_text is None:
            return ExtractionResult()
        return _parse_response(response_text, domain)

    async def ingest_candidate(
        self, candidate_data: dict, approved_temp_ids: set[str] | None = None,
    ) -> dict:
        """Ingest an approved candidate into the knowledge graph.

        Parses candidate_data as an ExtractionResult and upserts entities,
        rules, and relations into their respective repos.

        All database operations are wrapped in a transaction for atomicity.

        Args:
            candidate_data: Dict matching ExtractionResult schema with
                entities, relations, and rules lists.
            approved_temp_ids: Set of temp_id strings to approve.
                None means approve all (backward compat).

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

        # Filter items by approved_temp_ids when per-item approval is used
        if approved_temp_ids is not None:
            result.entities = [
                e for e in result.entities
                if not e.temp_id or e.temp_id in approved_temp_ids
            ]
            result.rules = [
                r for r in result.rules
                if not r.temp_id or r.temp_id in approved_temp_ids
            ]
            result.relations = [
                r for r in result.relations
                if not r.temp_id or r.temp_id in approved_temp_ids
            ]

        # Get database instance from any repo for transaction
        db = None
        if self._entity_repo is not None:
            db = self._entity_repo._db
        elif self._relation_repo is not None:
            db = self._relation_repo._db
        elif self._rule_repo is not None:
            db = self._rule_repo._db

        # Wrap all operations in a transaction if we have a database
        if db is not None:
            async with db.transaction():
                return await self._ingest_candidate_impl(result, summary)
        else:
            return await self._ingest_candidate_impl(result, summary)

    async def _ingest_candidate_impl(self, result: ExtractionResult, summary: dict) -> dict:
        """Internal implementation of ingest_candidate operations.

        This method contains the actual logic for ingesting entities, rules,
        and relations. It is called within a transaction context by
        ingest_candidate.
        """
        # --- Entities ---
        entity_cache: dict[tuple[str, str], int] = {}  # (name, domain) -> id
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
                    entity_cache[(ent.name, ent.domain)] = entity.id
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
                    entity_cache[(ent.name, ent.domain)] = created.id

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
            # Use entity_cache built during entity creation (works inside transaction)
            # For entities not in cache (e.g. pre-existing), do batch DB lookup
            summary["relations_pending"] = 0
            for rel in result.relations:
                source_name = rel.source_name
                target_name = rel.target_name
                relation_type = rel.relation_type

                if not source_name and " → " in rel.name:
                    parts = rel.name.split(" → ")
                    if len(parts) == 3:
                        source_name = parts[0]
                        target_name = parts[2]
                        relation_type = relation_type or parts[1]

                if not source_name or not target_name:
                    continue

                src_domain = rel.source_domain or rel.domain
                tgt_domain = rel.target_domain or rel.domain

                src_id = entity_cache.get((source_name, src_domain))
                tgt_id = entity_cache.get((target_name, tgt_domain))

                if src_id and tgt_id:
                    from ai_nexus.models.relation import RelationCreate
                    await self._relation_repo.create(
                        RelationCreate(
                            source_entity_id=src_id,
                            relation_type=relation_type or rel.type,
                            target_entity_id=tgt_id,
                            description=rel.description,
                            status="approved",
                            source="extraction",
                        )
                    )
                    summary["relations_created"] += 1
                else:
                    # Entity not found - write to pending_relations
                    await self._relation_repo.create_pending(
                        source_name=source_name,
                        source_domain=src_domain,
                        target_name=target_name,
                        target_domain=tgt_domain,
                        relation_type=relation_type or rel.type,
                        domain=rel.domain,
                        description=rel.description,
                        conditions=None,
                    )
                    summary["relations_pending"] += 1

        return summary

    async def detect_conflicts(self, candidate_data: dict) -> dict[str, list[dict]]:
        """Check candidate items against existing knowledge for duplicates.

        Args:
            candidate_data: Dict with "entities" and "rules" lists.

        Returns:
            Dict with "duplicates" list containing matching existing items.
        """
        conflicts: dict[str, list[dict]] = {"duplicates": []}
        entities = candidate_data.get("entities", [])
        rules = candidate_data.get("rules", [])

        for ent in entities:
            if self._entity_repo is None:
                break
            existing = await self._entity_repo.search(
                ent.get("name", ""), domain=ent.get("domain"), limit=1,
            )
            if existing:
                conflicts["duplicates"].append({
                    "temp_id": ent.get("temp_id", ""),
                    "existing_name": existing[0].name,
                    "existing_id": existing[0].id,
                    "type": "entity",
                })

        for rule in rules:
            if self._rule_repo is None:
                break
            existing = await self._rule_repo.search(
                rule.get("name", ""), domain=rule.get("domain"), limit=1,
            )
            if existing:
                conflicts["duplicates"].append({
                    "temp_id": rule.get("temp_id", ""),
                    "existing_name": existing[0].name,
                    "existing_id": existing[0].id,
                    "type": "rule",
                })

        return conflicts

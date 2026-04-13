"""Extraction models for AI-powered knowledge extraction.

Provides Pydantic models for structured knowledge extraction results
from the Claude API, including entities, relations, and rules.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    """Credibility label for extraction source.

    EXTRACTED: Directly extracted from text with high confidence
    INFERRED: Inferred by AI with moderate confidence
    AMBIGUOUS: Low confidence, needs human confirmation
    """

    EXTRACTED = "extracted"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class ExtractedItem(BaseModel):
    """Base model for an extracted knowledge item.

    Attributes:
        name: Human-readable name of the item
        type: Type classification (e.g., "人物", "地点", "机构", "概念", "系统" for entities;
            relation type for relations)
        domain: Business domain this item belongs to
        confidence: AI confidence score (0.0 to 1.0)
        source_type: Credibility label indicating how the item was derived
        description: Detailed explanation of the item
    """

    name: str
    type: str
    domain: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source_type: SourceType = Field(default=SourceType.INFERRED)
    description: str = ""


class ExtractedEntity(ExtractedItem):
    """Extracted entity with entity-specific fields.

    Extends ExtractedItem with entity-specific metadata.
    """

    pass


class ExtractedRelation(ExtractedItem):
    """Extracted relation between entities.

    Attributes:
        source_name: Name of the source entity
        source_domain: Domain of the source entity
        target_name: Name of the target entity
        target_domain: Domain of the target entity
        relation_type: Type of relationship (e.g., "depends_on", "owns", "related_to")
    """

    source_name: str = ""
    source_domain: str = ""
    target_name: str = ""
    target_domain: str = ""
    relation_type: str = ""

    @classmethod
    def from_name_format(cls, name: str, item: "ExtractedItem") -> "ExtractedRelation":
        """Create an ExtractedRelation from a name-formatted string.

        Parses names in the format "源实体 → 关系类型 → 目标实体".

        Args:
            name: The relation name in format "源实体 → 关系类型 → 目标实体"
            item: The base ExtractedItem to copy fields from

        Returns:
            An ExtractedRelation with parsed source, target, and relation_type
        """
        parts = name.split(" → ")
        if len(parts) == 3:
            return cls(
                source_name=parts[0],
                source_domain=item.domain,  # Use item's domain as source domain
                relation_type=parts[1],
                target_name=parts[2],
                target_domain=item.domain,  # Use item's domain as target domain
                name=item.name,
                type=item.type,
                domain=item.domain,
                confidence=item.confidence,
                description=item.description,
            )
        return cls(
            source_name="",
            source_domain=item.domain,
            relation_type=item.type,
            target_name="",
            target_domain=item.domain,
            name=item.name,
            type=item.type,
            domain=item.domain,
            confidence=item.confidence,
            description=item.description,
        )


class ExtractedRule(BaseModel):
    """Extracted business rule.

    Attributes:
        name: Human-readable name of the rule
        severity: Impact level ("error", "warning", "info")
        domain: Business domain this rule applies to
        confidence: AI confidence score (0.0 to 1.0)
        source_type: Credibility label indicating how the rule was derived
        description: Detailed explanation of the rule
        conditions: Optional JSON structure defining rule logic
    """

    name: str
    severity: str = Field(default="warning", pattern="^(error|warning|info|critical)$")
    domain: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source_type: SourceType = Field(default=SourceType.INFERRED)
    description: str = ""
    conditions: dict | None = None


class ExtractionResult(BaseModel):
    """Complete extraction result from Claude API.

    Contains lists of extracted entities, relations, and rules.
    Empty lists indicate no business knowledge was found.

    Attributes:
        entities: List of extracted entities
        relations: List of extracted relations
        rules: List of extracted rules
    """

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    rules: list[ExtractedRule] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if the extraction result contains any knowledge."""
        return not self.entities and not self.relations and not self.rules

    def count_total(self) -> int:
        """Return total count of all extracted items."""
        return len(self.entities) + len(self.relations) + len(self.rules)

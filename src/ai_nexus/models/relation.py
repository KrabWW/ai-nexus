"""Relation models for AI Nexus knowledge graph.

Relations represent connections between entities in the knowledge graph.
Each relation has a type (e.g., "depends_on", "owns", "related_to") and
can include conditions and weights for knowledge reasoning.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class RelationBase(BaseModel):
    """Base relation model with common fields.

    Attributes:
        source_entity_id: ID of the entity this relation originates from
        relation_type: Type of relationship (e.g., "depends_on", "owns")
        target_entity_id: ID of the entity this relation points to
        description: Optional explanation of the relationship
        conditions: Optional JSON metadata for conditional logic
        weight: Importance or confidence weight (default 1.0)
        status: Approval status ("approved", "pending", "rejected")
        source: Origin of this relation ("manual", "ai_extracted", "inferred")
    """

    source_entity_id: int
    relation_type: str
    target_entity_id: int
    description: str | None = None
    conditions: dict | None = Field(default=None, description="JSON metadata for conditional logic")
    weight: float = 1.0
    status: str = "approved"
    source: str = "manual"


class RelationCreate(RelationBase):
    """Model for creating a new relation.

    Inherits all fields from RelationBase with defaults applied.
    Used when inserting new relations into the knowledge graph.
    """

    pass


class Relation(RelationBase):
    """Complete relation model with database-generated fields.

    Used when returning relations from the database.
    Includes auto-generated ID and timestamps.
    """

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

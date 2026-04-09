"""Entity models for AI Nexus knowledge graph.

Entities represent business concepts, objects, or actors in the knowledge graph.
Each entity has a type, domain, and optional attributes for flexible representation.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class EntityBase(BaseModel):
    """Base entity model with common fields.

    Attributes:
        name: Human-readable name of the entity
        type: Entity type (e.g., "person", "organization", "concept")
        description: Optional detailed description
        attributes: Flexible JSON metadata for type-specific properties
        domain: Business domain this entity belongs to
        status: Approval status ("approved", "pending", "rejected")
        source: Origin of this entity ("manual", "ai_extracted", "imported")
    """

    name: str
    type: str
    description: str | None = None
    attributes: dict | None = Field(default=None, description="JSON metadata stored as dict")
    domain: str
    status: str = "approved"
    source: str = "manual"


class EntityCreate(EntityBase):
    """Model for creating a new entity.

    Inherits all fields from EntityBase with defaults applied.
    Used when inserting new entities into the knowledge graph.
    """

    pass


class EntityUpdate(BaseModel):
    """Model for updating an existing entity.

    All fields are optional to support partial updates.
    Only provided fields will be updated in the database.
    """

    name: str | None = None
    type: str | None = None
    description: str | None = None
    attributes: dict | None = None
    domain: str | None = None
    status: str | None = None


class Entity(EntityBase):
    """Complete entity model with database-generated fields.

    Used when returning entities from the database.
    Includes auto-generated ID and timestamps.
    """

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

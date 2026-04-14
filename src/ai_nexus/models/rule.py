"""Rule models for AI Nexus knowledge governance.

Rules encode business logic, constraints, and validation rules
that apply to entities and relationships within the knowledge graph.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class RuleBase(BaseModel):
    """Base rule model with common fields.

    Attributes:
        name: Human-readable name of the rule
        description: Detailed explanation of the rule's purpose
        domain: Business domain this rule applies to
        severity: Impact level ("info", "warning", "error", "critical")
        conditions: JSON structure defining rule logic/predicates
        related_entity_ids: List of entity IDs this rule references
        status: Approval status ("pending", "approved", "rejected")
        source: Origin of this rule ("ai_extracted", "manual", "imported")
        confidence: AI confidence score for extracted rules (0.0 to 1.0)
    """

    name: str
    description: str
    domain: str
    severity: str = "warning"
    conditions: dict | None = Field(default=None, description="JSON structure defining rule logic")
    related_entity_ids: list[int] | None = Field(default=None, description="Referenced entity IDs")
    status: str = "pending"
    source: str = "ai_extracted"
    confidence: float = 0.0


class RuleCreate(RuleBase):
    """Model for creating a new rule.

    Inherits all fields from RuleBase with defaults applied.
    Used when inserting new rules into the knowledge graph.
    """

    pass


class RuleUpdate(BaseModel):
    """Model for updating an existing rule.

    All fields are optional to support partial updates.
    Only provided fields will be updated in the database.
    """

    name: str | None = None
    description: str | None = None
    domain: str | None = None
    severity: str | None = None
    conditions: dict | None = None
    related_entity_ids: list[int] | None = None
    status: str | None = None
    confidence: float | None = None


class Rule(RuleBase):
    """Complete rule model with database-generated fields.

    Used when returning rules from the database.
    Includes auto-generated ID and timestamps.
    """

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RuleRepoBinding(BaseModel):
    """Model representing a rule's binding to a specific repository branch.

    Attributes:
        id: Database-generated binding ID
        rule_id: ID of the rule this binding belongs to
        repo_url: Normalized repository URL (e.g., "github.com/org/repo")
        branch_pattern: Glob pattern for branch matching (e.g., "*", "main", "feature/*")
        created_at: Timestamp when this binding was created
    """

    id: int
    rule_id: int
    repo_url: str
    branch_pattern: str = "*"
    created_at: datetime | None = None


class RuleRepoBindingCreate(BaseModel):
    """Model for creating a new rule-repository binding.

    Used when adding a binding to a rule. The repo_url will be
    normalized before storage to ensure SSH/HTTPS URLs match.
    """

    repo_url: str
    branch_pattern: str = "*"

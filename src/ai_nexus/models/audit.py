"""Audit logging models for AI Nexus knowledge governance.

Provides models for tracking changes to knowledge graph entities
and for handling development workflow hook requests.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogCreate(BaseModel):
    """Model for creating a new audit log entry.

    Used when recording changes to knowledge graph entities.
    """
    table_name: str
    record_id: int
    action: str  # "create"|"update"|"delete"|"submit_candidate"|"approve"|"reject"
    old_value: dict | None = None
    new_value: dict | None = None
    reviewer: str | None = None


class AuditLog(BaseModel):
    """Audit log entry for knowledge graph changes.

    Tracks all modifications to entities, relations, and rules
    for compliance review and change history.

    Attributes:
        id: Auto-generated log entry ID
        table_name: Database table that was modified
        record_id: ID of the affected record
        action: Type of change ("create", "update", "delete")
        old_value: Previous state as JSON dict (for updates/deletes)
        new_value: New state as JSON dict (for creates/updates)
        reviewer: Optional reviewer who approved/rejected the change
        created_at: Timestamp of the change
    """

    id: int
    table_name: str
    record_id: int
    action: str
    old_value: dict | None = None
    new_value: dict | None = None
    reviewer: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class KnowledgeCandidate(BaseModel):
    """Candidate knowledge awaiting review.

    Used for AI-extracted or imported knowledge that requires
    human approval before being added to the knowledge graph.

    Attributes:
        type: Candidate type ("entity" or "rule")
        data: The candidate data as a dict
        source: Origin of this candidate
        confidence: AI confidence score (0.0 to 1.0)
    """

    type: str = Field(description="Candidate type: 'entity' or 'rule'")
    data: dict
    source: str
    confidence: float = 0.5


class HookRequest(BaseModel):
    """Request model for development workflow hooks.

    Used by pre_plan and pre_commit hooks to query relevant
    business context and validate changes against knowledge rules.

    Attributes:
        task_description: Description of the planned work (for pre_plan)
        keywords: Optional keywords for semantic search
        diff: Optional code diff (for pre_commit validation)
        affected_files: List of files being changed (for pre_commit)
    """

    task_description: str = Field(description="Description of planned work for pre_plan hook")
    keywords: list[str] | None = Field(
        default=None, description="Search keywords for context lookup"
    )
    diff: str | None = Field(
        default=None, description="Code diff for pre_commit validation"
    )
    affected_files: list[str] | None = Field(
        default=None, description="Files affected by the change"
    )

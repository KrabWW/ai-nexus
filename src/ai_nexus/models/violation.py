"""Violation event models for AI Nexus data flywheel.

Tracks rule violations detected by pre-commit hooks, including
resolution status and timing information for confidence boosting.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ViolationEventCreate(BaseModel):
    """Model for creating a new violation event.

    Used when recording a rule violation detected by pre-commit hooks.
    """

    rule_id: str = Field(description="ID or name of the violated rule")
    change_description: str = Field(
        description="Description of the change that caused the violation"
    )
    resolution: str = Field(
        default="pending",
        description="Resolution status: pending, fixed, suppressed, ignored",
    )


class ViolationEventUpdate(BaseModel):
    """Model for updating an existing violation event.

    All fields are optional to support partial updates.
    """

    resolution: str | None = Field(
        default=None,
        description="Resolution status: pending, fixed, suppressed, ignored",
    )


class ViolationEvent(BaseModel):
    """Violation event model with database-generated fields.

    Represents a single rule violation detected during development,
    tracked for confidence boosting and pattern detection.
    """

    id: int
    rule_id: str
    change_description: str
    resolution: str
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class ViolationStats(BaseModel):
    """Aggregated violation statistics for a rule.

    Used for the GET /api/violations/stats endpoint.
    """

    rule_id: str
    violation_count: int = Field(description="Number of violations in the time period")
    fixed_count: int = Field(description="Number of violations that were fixed")
    fix_rate: float = Field(
        description="Percentage of violations that were fixed (0.0 to 1.0)"
    )
    avg_fix_time_hours: float | None = Field(
        default=None, description="Average time to fix in hours"
    )

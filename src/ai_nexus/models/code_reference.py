"""Code reference models for AI Nexus code anchoring.

Maps business rules to specific code locations (file:line ranges)
with immutable commit SHA anchoring and code snippets.
"""

from datetime import datetime

from pydantic import BaseModel


class CodeReferenceCreate(BaseModel):
    """Model for creating a new code reference."""

    rule_id: int
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    snippet: str | None = None
    repo_url: str | None = None
    commit_sha: str
    branch: str = "main"
    reference_type: str = "violation"  # violation | risk | implementation
    source: str = "pre_commit"  # pre_commit | ast_scan | manual


class CodeReference(BaseModel):
    """Code reference with database-generated fields."""

    id: int
    rule_id: int
    file_path: str
    line_start: int | None
    line_end: int | None
    snippet: str | None
    repo_url: str | None
    commit_sha: str
    branch: str
    reference_type: str
    source: str
    detected_at: datetime | None = None

    model_config = {"from_attributes": True}


class CodeReferenceWithRule(CodeReference):
    """Code reference joined with rule name/severity for display."""

    rule_name: str
    rule_severity: str

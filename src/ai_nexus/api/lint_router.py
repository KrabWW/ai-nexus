"""Lint API router for knowledge health reports."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ai_nexus.api.dependencies import (
    get_audit_repo,
    get_entity_repo,
    get_rule_repo,
)
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.lint_service import LintService

router = APIRouter(prefix="/api/lint")

RuleRepoInj = Annotated[RuleRepo, Depends(get_rule_repo)]
EntityRepoInj = Annotated[EntityRepo, Depends(get_entity_repo)]
AuditRepoInj = Annotated[AuditRepo, Depends(get_audit_repo)]


@router.get("/report")
async def get_lint_report(
    rule_repo: RuleRepoInj,
    entity_repo: EntityRepoInj,
    audit_repo: AuditRepoInj,
    format: str = Query("json", description="Response format: 'json' or 'markdown'"),
):
    """Generate a knowledge health lint report.

    Returns:
        - JSON format: Structured report with conflicts, dead_rules, coverage_gaps
        - Markdown format: Human-readable report suitable for team communication

    The report includes:
        - **Conflicts**: Potentially contradictory rules within the same domain
        - **Dead Rules**: Approved rules not referenced in audit logs for 30+ days
        - **Coverage Gaps**: Domains with entities but no governing rules
    """
    lint_service = LintService(rule_repo, entity_repo, audit_repo)
    report = await lint_service.generate_report()

    if format == "markdown":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=report.to_markdown(),
            media_type="text/markdown; charset=utf-8",
        )

    return {
        "conflicts": [
            {
                "rule_1_id": c.rule_1_id,
                "rule_1_name": c.rule_1_name,
                "rule_2_id": c.rule_2_id,
                "rule_2_name": c.rule_2_name,
                "domain": c.domain,
                "reason": c.reason,
            }
            for c in report.conflicts
        ],
        "dead_rules": [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "domain": r.domain,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "days_since_creation": r.days_since_creation,
            }
            for r in report.dead_rules
        ],
        "coverage_gaps": [
            {
                "domain": g.domain,
                "entity_count": g.entity_count,
                "entities": g.entities,
            }
            for g in report.coverage_gaps
        ],
        "generated_at": report.generated_at.isoformat(),
    }

"""REST API 路由：违规事件管理 + 统计。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ai_nexus.models.violation import (
    ViolationEvent,
    ViolationEventCreate,
    ViolationEventUpdate,
)
from ai_nexus.repos.violation_repo import ViolationRepo
from ai_nexus.services.flywheel_service import FlywheelService

router = APIRouter(prefix="/api/violations")


def get_violation_repo(request: Request) -> ViolationRepo:
    return request.app.state.violation_repo


def get_flywheel_service(request: Request) -> FlywheelService:
    return request.app.state.flywheel_service


ViolationRepoInj = Annotated[ViolationRepo, Depends(get_violation_repo)]
FlywheelSvcInj = Annotated[FlywheelService, Depends(get_flywheel_service)]


@router.post("/events", response_model=ViolationEvent, status_code=status.HTTP_201_CREATED)
async def record_violation(data: ViolationEventCreate, flywheel_svc: FlywheelSvcInj):
    """Record a new violation event from pre-commit hook."""
    return await flywheel_svc.record_violation(data)


@router.put("/events/{event_id}", response_model=ViolationEvent)
async def resolve_violation(
    event_id: int,
    data: ViolationEventUpdate,
    flywheel_svc: FlywheelSvcInj,
):
    """Resolve a violation event and potentially boost rule confidence."""
    result = await flywheel_svc.resolve_violation(event_id, data.resolution or "pending")
    if not result:
        raise HTTPException(status_code=404, detail="Violation event not found")
    return result


@router.get("/events/{event_id}", response_model=ViolationEvent)
async def get_violation_event(event_id: int, repo: ViolationRepoInj):
    """Get a specific violation event by ID."""
    event = await repo.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Violation event not found")
    return event


@router.get("/events", response_model=list[ViolationEvent])
async def list_violation_events(
    repo: ViolationRepoInj,
    rule_id: str | None = None,
    days: int = 30,
    limit: int = 100,
):
    """List violation events, optionally filtered by rule_id."""
    if rule_id:
        return await repo.list_by_rule(rule_id, limit=limit)
    return await repo.list_recent(days=days, limit=limit)


@router.get("/stats")
async def get_violation_stats(
    flywheel_svc: FlywheelSvcInj,
    days: int = 30,
):
    """Get violation statistics for the last N days."""
    stats = await flywheel_svc.get_violation_stats(days=days)
    return {
        "period_days": days,
        "stats": [s.model_dump() for s in stats],
    }


@router.post("/detect-patterns")
async def detect_violation_patterns(
    flywheel_svc: FlywheelSvcInj,
    days: int = 30,
):
    """Detect violation patterns that may need new rules.

    Returns patterns that occurred 3 or more times in the specified period.
    """
    patterns = await flywheel_svc.detect_violation_patterns(days=days)
    return {
        "period_days": days,
        "patterns": patterns,
        "count": len(patterns),
    }


@router.post("/generate-rule-candidate")
async def generate_rule_candidate(
    flywheel_svc: FlywheelSvcInj,
    pattern: str,
    domain: str = "flywheel",
):
    """Generate a new rule candidate from a detected pattern.

    Creates a rule with pending status for human review.
    """
    rule = await flywheel_svc.generate_rule_candidate(pattern, source_domain=domain)
    if not rule:
        raise HTTPException(
            status_code=500, detail="Failed to generate rule candidate"
        )
    return {
        "message": "Rule candidate generated",
        "rule_id": rule.id,
        "rule": rule.model_dump(),
    }

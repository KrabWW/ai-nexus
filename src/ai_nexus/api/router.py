"""REST API 路由：知识图谱 CRUD + 统一搜索。"""

import hashlib
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ai_nexus.api.dependencies import (
    get_audit_repo,
    get_code_reference_repo,
    get_extraction_service,
    get_graph_service,
    get_query_service,
)
from ai_nexus.models.audit import AuditLog, AuditLogCreate
from ai_nexus.models.code_reference import CodeReference, CodeReferenceCreate
from ai_nexus.models.entity import Entity, EntityCreate, EntityUpdate
from ai_nexus.models.rule import Rule, RuleCreate, RuleUpdate
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.code_reference_repo import CodeReferenceRepo
from ai_nexus.services.extraction_service import ExtractionService
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

GraphSvc = Annotated[GraphService, Depends(get_graph_service)]
QuerySvc = Annotated[QueryService, Depends(get_query_service)]
AuditRepoInj = Annotated[AuditRepo, Depends(get_audit_repo)]
ExtractionSvc = Annotated[ExtractionService, Depends(get_extraction_service)]
CodeRefRepoInj = Annotated[CodeReferenceRepo, Depends(get_code_reference_repo)]


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


# --- Entities ---

@router.post("/entities", response_model=Entity, status_code=status.HTTP_201_CREATED)
async def create_entity(data: EntityCreate, svc: GraphSvc):
    return await svc._entities.create(data)


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: int, svc: GraphSvc):
    entity = await svc._entities.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.put("/entities/{entity_id}", response_model=Entity)
async def update_entity(entity_id: int, data: EntityUpdate, svc: GraphSvc):
    updated = await svc._entities.update(entity_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Entity not found")
    return updated


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(entity_id: int, svc: GraphSvc):
    deleted = await svc._entities.delete(entity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.get("/entities", response_model=PaginatedResponse)
async def list_entities(
    svc: GraphSvc,
    domain: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items = await svc._entities.list(domain=domain, limit=limit, offset=offset)
    total = await svc._entities.count(domain=domain)
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/entities/batch", response_model=dict, status_code=status.HTTP_201_CREATED)
async def batch_create_entities(items: list[EntityCreate], svc: GraphSvc):
    db = svc._entities._db
    created = []
    async with db.transaction():
        for item in items:
            entity = await svc._entities.create(item)
            created.append(entity.id)
    return {"created": len(created), "ids": created}


# --- Rules ---

@router.post("/rules", response_model=Rule, status_code=status.HTTP_201_CREATED)
async def create_rule(data: RuleCreate, svc: GraphSvc):
    return await svc._rules.create(data)


@router.get("/rules/{rule_id}", response_model=Rule)
async def get_rule(rule_id: int, svc: GraphSvc):
    rule = await svc._rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=Rule)
async def update_rule(rule_id: int, data: RuleUpdate, svc: GraphSvc):
    updated = await svc._rules.update(rule_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found")
    return updated


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, svc: GraphSvc):
    deleted = await svc._rules.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.get("/rules", response_model=PaginatedResponse)
async def list_rules(
    svc: GraphSvc,
    domain: str | None = None,
    severity: str | None = None,
    status_filter: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items = await svc._rules.list(
        domain=domain, severity=severity, status=status_filter, limit=limit, offset=offset
    )
    total = await svc._rules.count(domain=domain, severity=severity, status=status_filter)
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/rules/batch", response_model=dict, status_code=status.HTTP_201_CREATED)
async def batch_create_rules(items: list[RuleCreate], svc: GraphSvc):
    db = svc._rules._db
    created = []
    async with db.transaction():
        for item in items:
            rule = await svc._rules.create(item)
            created.append(rule.id)
    return {"created": len(created), "ids": created}

class SearchBody(BaseModel):
    query: str
    type: str = "rules"
    domain: str | None = None
    limit: int = 10


@router.post("/search")
async def search(body: SearchBody, query_svc: QuerySvc, graph_svc: GraphSvc):
    if body.type == "entities":
        results = await graph_svc.search_entities(body.query, domain=body.domain, limit=body.limit)
        return {"results": [e.model_dump() for e in results], "type": "entities"}
    else:
        results = await query_svc.query_rules(body.query, domain=body.domain, limit=body.limit)
        return {"results": [r.model_dump() for r in results], "type": "rules"}


class ReindexBody(BaseModel):
    force: bool = False


@router.post("/search/reindex")
async def reindex(body: ReindexBody | None = None):
    """触发知识库重建索引。
    在 Phase 0 中仅返回确认信息，完整的索引重建将在后续阶段实现。
    """
    if body is None:
        body = ReindexBody()
    return {
        "status": "triggered",
        "force": body.force,
        "message": "索引重建已触发，完整功能将在后续阶段实现",
    }


# --- 审核工作流 ---

@router.post("/audit/candidates", response_model=AuditLog, status_code=status.HTTP_201_CREATED)
async def submit_candidate(data: AuditLogCreate, repo: AuditRepoInj):
    return await repo.create(data)


@router.get("/audit/pending", response_model=list[AuditLog])
async def list_pending(repo: AuditRepoInj):
    return await repo.list_pending()


class ReviewAction(BaseModel):
    reviewer: str = "system"


@router.post("/audit/{record_id}/approve")
async def approve_candidate(
    record_id: int, action: ReviewAction, repo: AuditRepoInj, extraction_svc: ExtractionSvc,
):
    log = await repo.create(AuditLogCreate(
        table_name="knowledge_audit_log",
        record_id=record_id,
        action="approve",
        reviewer=action.reviewer,
    ))
    ingested = None
    original = await repo.get_by_id(record_id)
    if original and original.action == "submit_candidate" and original.new_value:
        ingested = await extraction_svc.ingest_candidate(original.new_value)
    return {"status": "approved", "record_id": record_id, "log_id": log.id, "ingested": ingested}


@router.post("/audit/{record_id}/reject")
async def reject_candidate(record_id: int, action: ReviewAction, repo: AuditRepoInj):
    log = await repo.create(AuditLogCreate(
        table_name="knowledge_audit_log",
        record_id=record_id,
        action="reject",
        reviewer=action.reviewer,
    ))
    return {"status": "rejected", "record_id": record_id, "log_id": log.id}


# --- 开发流程 Hook ---

class PrePlanRequest(BaseModel):
    task_description: str
    keywords: list[str] | None = None


class PreCommitRequest(BaseModel):
    change_description: str
    affected_entities: list[str] | None = None
    diff_summary: str | None = None
    diff_content: str | None = None
    commit_sha: str | None = None
    branch: str | None = None
    repo_url: str | None = None


class StructuralScanRequest(BaseModel):
    file_paths: list[str]
    patterns: list[str] | None = None


@router.post("/hooks/pre-plan")
async def pre_plan_hook(body: PrePlanRequest, graph_svc: GraphSvc):
    ctx = await graph_svc.get_business_context(body.task_description, keywords=body.keywords)
    return ctx


@router.post("/hooks/pre-commit")
async def pre_commit_hook(
    body: PreCommitRequest,
    query_svc: QuerySvc,
    code_ref_repo: CodeRefRepoInj,
):
    from ai_nexus.services.ast_analyzer import extract_keywords_from_path, keywords_overlap
    from ai_nexus.services.diff_parser import extract_snippet, parse_unified_diff

    keywords = body.affected_entities or [body.change_description]
    errors = []
    warnings = []
    infos = []
    matched_rules: list[Any] = []
    for kw in keywords:
        rules = await query_svc.query_rules(kw, limit=5)
        for rule in rules:
            if rule.status == "approved":
                violation = {
                    "rule": rule.name,
                    "rule_id": rule.id,
                    "description": rule.description,
                    "severity": rule.severity or "info",
                }
                if rule.severity == "critical":
                    errors.append(violation)
                elif rule.severity == "warning":
                    warnings.append(violation)
                else:
                    infos.append(violation)
                matched_rules.append(rule)

    # Code reference capture (only when diff + commit_sha provided)
    code_refs_created = 0
    if body.diff_content and body.commit_sha:
        try:
            file_diffs = parse_unified_diff(body.diff_content)
            for rule in matched_rules:
                for file_diff in file_diffs:
                    file_kw = extract_keywords_from_path(file_diff.file_path)
                    if keywords_overlap(file_kw, rule):
                        for hunk in file_diff.hunks:
                            await code_ref_repo.create(
                                CodeReferenceCreate(
                                    rule_id=rule.id,
                                    file_path=file_diff.file_path,
                                    line_start=hunk.line_start,
                                    line_end=hunk.line_end,
                                    snippet=extract_snippet(hunk.content),
                                    repo_url=body.repo_url,
                                    commit_sha=body.commit_sha,
                                    branch=body.branch or "main",
                                    reference_type="violation"
                                    if rule.severity == "critical"
                                    else "risk",
                                    source="pre_commit",
                                )
                            )
                            code_refs_created += 1
        except Exception as e:
            logger.warning("Code reference capture failed: %s", e, exc_info=True)

    return {
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "passed": len(errors) == 0,
        "code_references_created": code_refs_created,
    }


# --- Cold Start ---

class ColdStartRequest(BaseModel):
    domain: str
    description: str
    keywords: list[str] | None = None


@router.post("/cold-start")
async def cold_start(body: ColdStartRequest, extraction_svc: ExtractionSvc, repo: AuditRepoInj):
    # Get existing entity names in the domain
    existing_entities: list[str] = []
    # We use the repo's internal db to query entities directly
    entity_rows = await repo._db.fetchall(
        "SELECT name FROM entities WHERE domain = ?",
        (body.domain,),
    )
    if entity_rows:
        existing_entities = [r[0] for r in entity_rows]

    result = await extraction_svc.cold_start(
        body.domain,
        body.description,
        existing_entities or None,
    )

    # Submit to audit log if there are candidates
    audit_id = None
    candidates = result.model_dump()
    if result.entities or result.relations or result.rules:
        log = await repo.create(AuditLogCreate(
            table_name="extraction",
            record_id=0,
            action="submit_candidate",
            new_value=candidates,
            reviewer="cold_start",
        ))
        audit_id = log.id

    return {
        "audit_id": audit_id,
        "candidates": candidates,
        "message": "候选项已提交，请在审核页面确认" if audit_id else "未提取到有效知识",
    }


# --- Post-Task Hook ---

class PostTaskRequest(BaseModel):
    task_description: str
    summary: str | None = None
    keywords: list[str] | None = None
    idempotency_key: str | None = None


@router.post("/hooks/post-task")
async def post_task_hook(body: PostTaskRequest, extraction_svc: ExtractionSvc, repo: AuditRepoInj):
    import json as _json

    task_text = body.summary or body.task_description
    task_hash = hashlib.md5(task_text.encode()).hexdigest()

    # Idempotency check: look for existing submission with same hash
    existing = await repo._db.fetchall(
        "SELECT id, table_name, record_id, action, old_value, new_value, reviewer, created_at "
        "FROM knowledge_audit_log "
        "WHERE action = 'submit_candidate' AND reviewer = 'post_task_hook'",
    )
    for row in existing:
        # row: (id, table_name, record_id, action, old_value, new_value, reviewer, created_at)
        old_val = _json.loads(row[4]) if row[4] else {}
        if old_val.get("hash") == task_hash:
            candidates = _json.loads(row[5]) if row[5] else {}
            return {
                "submitted": True,
                "audit_id": row[0],
                "candidates": candidates,
                "idempotent": True,
            }

    result = await extraction_svc.extract(task_text)
    candidates = result.model_dump()

    has_content = bool(result.entities or result.relations or result.rules)
    audit_id = None

    if has_content:
        log = await repo.create(AuditLogCreate(
            table_name="extraction",
            record_id=0,
            action="submit_candidate",
            old_value={"hash": task_hash},
            new_value=candidates,
            reviewer="post_task_hook",
        ))
        audit_id = log.id

    return {
        "submitted": has_content,
        "audit_id": audit_id,
        "candidates": candidates if has_content else None,
    }


# --- Code References ---


@router.get("/code-references", response_model=PaginatedResponse)
async def list_code_references(
    code_ref_repo: CodeRefRepoInj,
    rule_id: int | None = None,
    file_path: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List code references, optionally filtered by rule or file."""
    if rule_id is not None:
        items = await code_ref_repo.list_by_rule(rule_id, limit=limit)
    elif file_path is not None:
        items = await code_ref_repo.list_by_file(file_path, limit=limit)
    else:
        items = []
    return PaginatedResponse(items=items, total=len(items), limit=limit, offset=offset)


@router.get("/code-references/{ref_id}", response_model=CodeReference)
async def get_code_reference(ref_id: int, code_ref_repo: CodeRefRepoInj):
    """Get a single code reference by ID."""
    ref = await code_ref_repo.get(ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Code reference not found")
    return ref


@router.post("/code-references", response_model=CodeReference, status_code=status.HTTP_201_CREATED)
async def create_code_reference(data: CodeReferenceCreate, code_ref_repo: CodeRefRepoInj):
    """Manually create a code reference."""
    return await code_ref_repo.create(data)


@router.delete("/code-references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_code_reference(ref_id: int, code_ref_repo: CodeRefRepoInj):
    """Delete a code reference."""
    deleted = await code_ref_repo.delete(ref_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Code reference not found")


@router.post("/structural-scan")
async def structural_scan(body: StructuralScanRequest):
    """Scan files for structural patterns using ast-grep or Python ast fallback."""
    from ai_nexus.services.structural_scanner import StructuralScanner

    scanner = StructuralScanner()
    results = await scanner.scan_files(body.file_paths, patterns=body.patterns)

    output = []
    for r in results:
        entry: dict[str, Any] = {
            "file_path": r.file_path,
            "language": r.language,
            "symbols": [
                {
                    "name": s.name,
                    "type": s.symbol_type,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                }
                for s in r.symbols
            ],
        }
        if r.pattern_matches:
            entry["pattern_matches"] = [
                {
                    "pattern": m.pattern,
                    "line_start": m.line_start,
                    "line_end": m.line_end,
                    "text": m.text[:200],
                }
                for m in r.pattern_matches
            ]
        if r.error:
            entry["error"] = r.error
        output.append(entry)

    return {"results": output, "total": len(output)}


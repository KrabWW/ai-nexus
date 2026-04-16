"""Web Console router — 知识图谱管理界面。

提供基于 Jinja2 模板的 Web 管理界面，用于管理实体、规则、关系等。
"""

import json as _json
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ai_nexus.api.dependencies import (
    get_audit_repo,
    get_code_reference_repo,
    get_entity_repo,
    get_extraction_service,
    get_graph_service,
    get_relation_repo,
    get_rule_repo,
)
from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.models.entity import EntityCreate, EntityUpdate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.models.rule import RuleCreate, RuleUpdate
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.code_reference_repo import CodeReferenceRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService

router = APIRouter(prefix="/console", tags=["console"])
templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True

# UTC → 本地时间 (CST UTC+8) Jinja2 过滤器
_CST = timezone(timedelta(hours=8))

def _localtime(value: str | None) -> str:
    if not value:
        return ""
    try:
        s = str(value).strip()
        dt = datetime.fromisoformat(s) if "T" in s else datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(_CST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)

templates.env.filters["localtime"] = _localtime
templates.env.filters["tojson_cn"] = lambda v: _json.dumps(v, indent=2, ensure_ascii=False)

GraphSvc = Annotated[GraphService, Depends(get_graph_service)]
EntityRepoInj = Annotated[EntityRepo, Depends(get_entity_repo)]
RuleRepoInj = Annotated[RuleRepo, Depends(get_rule_repo)]
RelationRepoInj = Annotated[RelationRepo, Depends(get_relation_repo)]
AuditRepoInj = Annotated[AuditRepo, Depends(get_audit_repo)]
ExtractionSvcInj = Annotated[ExtractionService, Depends(get_extraction_service)]
CodeRefRepoInj = Annotated[CodeReferenceRepo, Depends(get_code_reference_repo)]


# --- Base Dashboard ---

@router.get("/")
async def dashboard(request: Request, graph_svc: GraphSvc, audit_repo: AuditRepoInj):
    """主控制台仪表板，显示系统概览。"""
    entities = await graph_svc._entities.list(limit=10)
    rules = await graph_svc._rules.list(limit=10)
    relations = await graph_svc._relations.list(limit=10)
    pending_audits = await audit_repo.list_pending()

    return templates.TemplateResponse(request, "dashboard.html",{
            "request": request,
            "entities": entities,
            "rules": rules,
            "relations": relations,
            "pending_audits": pending_audits,
            "active_page": "dashboard",
        },
    )


# --- Entity Management ---

@router.get("/entities")
async def list_entities(
    request: Request,
    entity_repo: EntityRepoInj,
    domain: str | None = None,
    search: str | None = None,
    limit: int = 100,
):
    """实体列表页面，支持搜索和领域过滤。"""
    if search:
        entities = await entity_repo.search(search, domain=domain, limit=limit)
    else:
        entities = await entity_repo.list(domain=domain, limit=limit)

    # 获取所有领域用于过滤器
    all_entities = await entity_repo.list(limit=1000)
    domains = sorted(set(e.domain for e in all_entities))

    return templates.TemplateResponse(request, "entities/list.html",{
            "request": request,
            "entities": entities,
            "domains": domains,
            "selected_domain": domain,
            "search_query": search,
            "active_page": "entities",
        },
    )


@router.get("/entities/new")
async def new_entity_form(request: Request):
    """新建实体表单页面。"""
    return templates.TemplateResponse(
        request,
        "entities/form.html",
        {"active_page": "entities", "entity": None},
    )


@router.post("/entities")
async def create_entity(
    request: Request,
    entity_repo: EntityRepoInj,
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(default=""),
    domain: str = Form(...),
    entity_status: str = Form(default="approved"),
    source: str = Form(default="manual"),
):
    """创建新实体。"""
    data = EntityCreate(
        name=name,
        type=type,
        description=description if description else None,
        domain=domain,
        status=entity_status,
        source=source,
    )
    await entity_repo.create(data)
    return RedirectResponse(url="/console/entities", status_code=303)


@router.get("/entities/{entity_id}/edit")
async def edit_entity_form(
    entity_id: int,
    request: Request,
    entity_repo: EntityRepoInj,
):
    """编辑实体表单页面。"""
    entity = await entity_repo.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return templates.TemplateResponse(
        request,
        "entities/form.html",
        {"active_page": "entities", "entity": entity},
    )


@router.post("/entities/{entity_id}/edit")
async def update_entity(
    entity_id: int,
    entity_repo: EntityRepoInj,
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(default=""),
    domain: str = Form(...),
    entity_status: str = Form(default="approved"),
):
    """更新实体。"""
    data = EntityUpdate(
        name=name,
        type=type,
        description=description if description else None,
        domain=domain,
        status=entity_status,
    )
    await entity_repo.update(entity_id, data)
    return RedirectResponse(url="/console/entities", status_code=303)


@router.post("/entities/{entity_id}/delete")
async def delete_entity(
    entity_id: int,
    entity_repo: EntityRepoInj,
):
    """删除实体。"""
    await entity_repo.delete(entity_id)
    return RedirectResponse(url="/console/entities", status_code=303)


@router.get("/entities/deduplicate")
async def deduplicate_entities_form(
    request: Request,
    entity_repo: EntityRepoInj,
):
    """实体去重管理页面，显示重复实体预览。"""
    duplicates = await entity_repo.find_duplicates()

    # 获取每个重复组的详细信息
    duplicate_groups = []
    for dup in duplicates:
        entities = await entity_repo.get_by_ids(dup["ids"])
        # 按创建时间排序，最早的在前
        entities_sorted = sorted(entities, key=lambda e: e.created_at or "")
        duplicate_groups.append({
            "name": dup["name"],
            "domain": dup["domain"],
            "count": dup["count"],
            "ids": dup["ids"],
            "entities": entities_sorted,
            "keep_id": entities_sorted[0].id,  # 默认保留最早的
        })

    return templates.TemplateResponse(request, "entities/deduplicate.html",{
            "request": request,
            "duplicate_groups": duplicate_groups,
            "active_page": "entities",
        },
    )


@router.post("/entities/deduplicate")
async def deduplicate_entities_execute(
    request: Request,
    entity_repo: EntityRepoInj,
    keep_ids: str = Form(...),
    remove_ids: str = Form(...),
):
    """执行实体去重合并操作。"""
    import json

    keep_id_list = json.loads(keep_ids)
    remove_id_list = json.loads(remove_ids)

    # 逐对执行合并
    merged_count = 0
    for keep_id, remove_id in zip(keep_id_list, remove_id_list, strict=True):
        if keep_id and remove_id:
            try:
                await entity_repo.merge_entities(keep_id, [remove_id])
                merged_count += 1
            except Exception:
                # 合并失败，记录错误但继续处理其他项
                pass

    return templates.TemplateResponse(
        request,
        "entities/deduplicate.html",
        {
            "request": request,
            "duplicate_groups": [],
            "active_page": "entities",
            "success_message": f"成功合并 {merged_count} 个重复实体",
        },
    )


# --- Rule Management ---

@router.get("/rules")
async def list_rules(
    request: Request,
    rule_repo: RuleRepoInj,
    domain: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    limit: int = 100,
):
    """规则列表页面，支持搜索和过滤。"""
    if search:
        rules = await rule_repo.search(search, domain=domain, severity=severity, limit=limit)
    else:
        rules = await rule_repo.list(domain=domain, severity=severity, limit=limit)

    # 获取所有领域和严重级别用于过滤器
    all_rules = await rule_repo.list(limit=1000)
    domains = sorted(set(r.domain for r in all_rules))
    severities = sorted(set(r.severity for r in all_rules))

    # 获取每个规则的绑定数量
    rules_with_counts = []
    for rule in rules:
        bindings = await rule_repo.list_bindings(rule.id)
        rule_with_count = rule.model_dump()
        rule_with_count["binding_count"] = len(bindings)
        from ai_nexus.models.rule import Rule
        rules_with_counts.append(Rule(**rule_with_count))

    return templates.TemplateResponse(request, "rules/list.html",{
            "request": request,
            "rules": rules_with_counts,
            "domains": domains,
            "severities": severities,
            "selected_domain": domain,
            "selected_severity": severity,
            "search_query": search,
            "active_page": "rules",
        },
    )


@router.get("/rules/new")
async def new_rule_form(request: Request):
    """新建规则表单页面。"""
    return templates.TemplateResponse(
        request,
        "rules/form.html",
        {"active_page": "rules", "rule": None},
    )


@router.post("/rules")
async def create_rule(
    rule_repo: RuleRepoInj,
    name: str = Form(...),
    description: str = Form(...),
    domain: str = Form(...),
    severity: str = Form(default="warning"),
    rule_status: str = Form(default="pending"),
    source: str = Form(default="manual"),
    confidence: float = Form(default=0.0),
    conditions: str = Form(default=""),
    related_entity_ids: str = Form(default=""),
):
    """创建新规则。"""
    import json

    data = RuleCreate(
        name=name,
        description=description,
        domain=domain,
        severity=severity,
        status=rule_status,
        source=source,
        confidence=confidence,
        conditions=json.loads(conditions) if conditions else None,
        related_entity_ids=[
            int(x.strip()) for x in related_entity_ids.split(",") if x.strip()
        ]
        if related_entity_ids
        else None,
    )
    await rule_repo.create(data)
    return RedirectResponse(url="/console/rules", status_code=303)


@router.get("/rules/{rule_id}/detail")
async def rule_detail(
    rule_id: int,
    request: Request,
    rule_repo: RuleRepoInj,
    code_ref_repo: CodeRefRepoInj,
):
    """规则详情页面，显示关联的代码锚定引用。"""
    rule = await rule_repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    code_refs = await code_ref_repo.list_by_rule(rule_id)
    bindings = await rule_repo.list_bindings(rule_id)
    return templates.TemplateResponse(
        request,
        "rules/detail.html",
        {
            "request": request,
            "rule": rule,
            "code_refs": code_refs,
            "bindings": bindings,
            "active_page": "rules",
        },
    )


@router.get("/rules/{rule_id}/edit")
async def edit_rule_form(
    rule_id: int,
    request: Request,
    rule_repo: RuleRepoInj,
):
    """编辑规则表单页面。"""
    rule = await rule_repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return templates.TemplateResponse(
        request,
        "rules/form.html",
        {"active_page": "rules", "rule": rule},
    )


@router.post("/rules/{rule_id}/edit")
async def update_rule(
    rule_id: int,
    rule_repo: RuleRepoInj,
    name: str = Form(...),
    description: str = Form(...),
    domain: str = Form(...),
    severity: str = Form(default="warning"),
    rule_status: str = Form(default="pending"),
    confidence: float = Form(default=0.0),
    conditions: str = Form(default=""),
    related_entity_ids: str = Form(default=""),
):
    """更新规则。"""
    import json

    data = RuleUpdate(
        name=name,
        description=description,
        domain=domain,
        severity=severity,
        status=rule_status,
        confidence=confidence,
        conditions=json.loads(conditions) if conditions else None,
        related_entity_ids=[
            int(x.strip()) for x in related_entity_ids.split(",") if x.strip()
        ]
        if related_entity_ids
        else None,
    )
    await rule_repo.update(rule_id, data)
    return RedirectResponse(url="/console/rules", status_code=303)


@router.post("/rules/{rule_id}/delete")
async def delete_rule(
    rule_id: int,
    rule_repo: RuleRepoInj,
):
    """删除规则。"""
    await rule_repo.delete(rule_id)
    return RedirectResponse(url="/console/rules", status_code=303)


@router.post("/rules/{rule_id}/bindings")
async def add_binding(
    rule_id: int,
    rule_repo: RuleRepoInj,
    repo_url: str = Form(...),
    branch_pattern: str = Form(default="*"),
):
    """添加规则仓库绑定。"""
    from ai_nexus.models.rule import RuleRepoBindingCreate

    # 验证规则存在
    rule = await rule_repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # 添加绑定
    data = RuleRepoBindingCreate(repo_url=repo_url, branch_pattern=branch_pattern)
    await rule_repo.add_binding(rule_id, data)

    return RedirectResponse(url=f"/console/rules/{rule_id}/detail", status_code=303)


@router.post("/rules/{rule_id}/bindings/{binding_id}/delete")
async def delete_binding(
    rule_id: int,
    binding_id: int,
    rule_repo: RuleRepoInj,
):
    """删除规则仓库绑定。"""
    # 验证规则存在
    rule = await rule_repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # 删除绑定
    deleted = await rule_repo.remove_binding(binding_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Binding not found")

    return RedirectResponse(url=f"/console/rules/{rule_id}/detail", status_code=303)


# --- Relation Management ---

@router.get("/relations")
async def list_relations(
    request: Request,
    relation_repo: RelationRepoInj,
    entity_repo: EntityRepoInj,
    limit: int = 100,
):
    """关系列表页面，显示源和目标实体信息。"""
    relations = await relation_repo.list(limit=limit)

    # 获取所有实体用于显示名称
    all_entities = await entity_repo.list(limit=1000)
    entity_map = {e.id: e for e in all_entities}

    return templates.TemplateResponse(request, "relations/list.html",{
            "request": request,
            "relations": relations,
            "entity_map": entity_map,
            "active_page": "relations",
        },
    )


@router.get("/relations/new")
async def new_relation_form(
    request: Request,
    entity_repo: EntityRepoInj,
):
    """新建关系表单页面。"""
    entities = await entity_repo.list(limit=1000)
    return templates.TemplateResponse(request, "relations/form.html",{
            "request": request,
            "active_page": "relations",
            "entities": entities,
            "relation": None,
        },
    )


@router.post("/relations")
async def create_relation(
    relation_repo: RelationRepoInj,
    source_entity_id: int = Form(...),
    relation_type: str = Form(...),
    target_entity_id: int = Form(...),
    description: str = Form(default=""),
    weight: float = Form(default=1.0),
    relation_status: str = Form(default="approved"),
    source: str = Form(default="manual"),
):
    """创建新关系。"""
    data = RelationCreate(
        source_entity_id=source_entity_id,
        relation_type=relation_type,
        target_entity_id=target_entity_id,
        description=description if description else None,
        weight=weight,
        status=relation_status,
        source=source,
    )
    await relation_repo.create(data)
    return RedirectResponse(url="/console/relations", status_code=303)


@router.post("/relations/{relation_id}/delete")
async def delete_relation(
    relation_id: int,
    relation_repo: RelationRepoInj,
):
    """删除关系。"""
    await relation_repo.delete(relation_id)
    return RedirectResponse(url="/console/relations", status_code=303)


# --- Audit Workflow ---

@router.get("/audit")
async def audit_list(
    request: Request,
    audit_repo: AuditRepoInj,
    relation_repo: RelationRepoInj,
    extraction_svc: ExtractionSvcInj,
):
    """审核工作流页面，显示待审核候选和审核历史。"""
    pending = await audit_repo.list_pending()

    # Detect conflicts for each pending item
    pending_conflicts: dict[int, dict] = {}
    for item in pending:
        if item.new_value:
            conflicts = await extraction_svc.detect_conflicts(item.new_value)
            if conflicts["duplicates"]:
                pending_conflicts[item.id] = conflicts

    # 获取所有审核日志（包括已处理的）
    all_logs = await audit_repo._db.fetchall(
        """SELECT id, table_name, record_id, action, reviewer,
                  created_at
           FROM knowledge_audit_log
           ORDER BY created_at DESC
           LIMIT 50"""
    )

    audit_history = []
    for row in all_logs:
        audit_history.append(
            {
                "id": row[0],
                "table_name": row[1],
                "record_id": row[2],
                "action": row[3],
                "reviewer": row[4],
                "created_at": row[5],
            }
        )

    # 获取待处理关系数量
    pending_relations = await relation_repo.list_pending(limit=1000)
    pending_relations_count = len(pending_relations)

    return templates.TemplateResponse(request, "audit/list.html",{
            "request": request,
            "pending": pending,
            "pending_conflicts": pending_conflicts,
            "audit_history": audit_history,
            "pending_relations_count": pending_relations_count,
            "active_page": "audit",
        },
    )


@router.post("/audit/{record_id}/approve")
async def approve_audit_item(
    record_id: int,
    audit_repo: AuditRepoInj,
    extraction_svc: ExtractionSvcInj,
    reviewer: str = Form(default="console"),
    items_json: str = Form(default=""),
):
    """批准审核项，支持逐条审核。"""
    import json as _json

    from ai_nexus.models.audit import AuditLogCreate

    # Parse per-item actions if provided
    approved_temp_ids: set[str] | None = None
    if items_json and items_json.strip():
        try:
            items = _json.loads(items_json)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid items_json") from exc
        # Validate all temp_ids belong to this record
        prefix = f"{record_id}_"
        for item in items:
            tid = item.get("temp_id", "")
            if tid and not tid.startswith(prefix):
                raise HTTPException(
                    status_code=400,
                    detail=f"temp_id '{tid}' does not belong to record {record_id}",
                )
        approved_temp_ids = {
            item["temp_id"] for item in items if item.get("action") == "approve"
        }

    await audit_repo.create(
        AuditLogCreate(
            table_name="knowledge_audit_log",
            record_id=record_id,
            action="approve",
            reviewer=reviewer,
        )
    )
    original = await audit_repo.get_by_id(record_id)
    if original and original.action == "submit_candidate" and original.new_value:
        await extraction_svc.ingest_candidate(original.new_value, approved_temp_ids)
    return RedirectResponse(url="/console/audit", status_code=303)


@router.post("/audit/{record_id}/reject")
async def reject_audit_item(
    record_id: int,
    audit_repo: AuditRepoInj,
):
    """拒绝审核项。"""
    from ai_nexus.models.audit import AuditLogCreate

    await audit_repo.create(
        AuditLogCreate(
            table_name="knowledge_audit_log",
            record_id=record_id,
            action="reject",
            reviewer="console",
        )
    )
    return RedirectResponse(url="/console/audit", status_code=303)


# --- Knowledge Lint Dashboard ---

@router.get("/lint")
async def lint_dashboard(
    request: Request,
    rule_repo: RuleRepoInj,
    entity_repo: EntityRepoInj,
    audit_repo: AuditRepoInj,
):
    """知识健康检查仪表板，显示冲突、死规则和覆盖缺口。"""
    from ai_nexus.services.lint_service import LintService

    lint_service = LintService(rule_repo, entity_repo, audit_repo)
    report = await lint_service.generate_report()

    return templates.TemplateResponse(request, "lint/dashboard.html",{
            "request": request,
            "report": report,
            "active_page": "lint",
        },
    )


# --- Import Management ---

@router.get("/imports")
async def imports_page(request: Request):
    """导入管理页面，显示飞书导入和单文档导入。"""
    return templates.TemplateResponse(request, "imports/page.html", {
            "request": request,
            "active_page": "imports",
            "import_result": {
                "processed": request.query_params.get("processed"),
                "entities": request.query_params.get("entities"),
                "relations": request.query_params.get("relations"),
                "rules": request.query_params.get("rules"),
                "failed": request.query_params.get("failed"),
                "error": request.query_params.get("error"),
            },
        },
    )


@router.post("/imports/feishu")
async def trigger_feishu_import(
    request: Request,
    space_id: str = Form(...),
    domain_hint: str = Form(default=""),
):
    """触发飞书知识空间导入。"""
    import httpx

    payload = {
        "space_id": space_id,
        "domain_hint": domain_hint if domain_hint else None,
        "dry_run": False,
    }

    base_url = f"{request.url.scheme}://{request.url.netloc}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/ingest/feishu",
                json=payload,
                timeout=300.0,
            )
        if response.status_code == 200:
            data = response.json()
            params = urlencode({
                "processed": data.get("processed", 0),
                "entities": data.get("entities", 0),
                "relations": data.get("relations", 0),
                "rules": data.get("rules", 0),
            })
        else:
            params = urlencode({"failed": 1, "error": response.status_code})
    except Exception as exc:
        params = urlencode({"failed": 1, "error": str(exc)[:100]})

    return RedirectResponse(url=f"/console/imports?{params}", status_code=303)


@router.post("/imports/document")
async def trigger_document_import(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    domain_hint: str = Form(default=""),
):
    """触发单文档导入。"""
    import httpx

    payload = {
        "title": title,
        "content": content,
        "source": "manual",
        "domain_hint": domain_hint if domain_hint else None,
        "dry_run": False,
    }

    base_url = f"{request.url.scheme}://{request.url.netloc}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/ingest/document",
                json=payload,
                timeout=60.0,
            )
        if response.status_code == 200:
            data = response.json()
            params = urlencode({
                "processed": data.get("processed", 0),
                "entities": data.get("entities", 0),
                "relations": data.get("relations", 0),
                "rules": data.get("rules", 0),
            })
        else:
            params = urlencode({"failed": 1, "error": response.status_code})
    except Exception as exc:
        params = urlencode({"failed": 1, "error": str(exc)[:100]})

    return RedirectResponse(url=f"/console/imports?{params}", status_code=303)


# --- Knowledge Graph Visualization ---

@router.get("/graph")
async def graph_page(request: Request):
    """知识图谱 D3.js 可视化页面。"""
    return templates.TemplateResponse(request, "graph/page.html", {"active_page": "graph"})


# --- System Settings ---

@router.get("/settings")
async def settings_page(
    request: Request,
    graph_svc: GraphSvc,
):
    """系统设置页面，显示系统信息和连接状态。"""
    entities = await graph_svc._entities.list(limit=1000)
    rules = await graph_svc._rules.list(limit=1000)
    relations = await graph_svc._relations.list(limit=1000)

    # 统计信息
    entity_count = len(entities)
    rule_count = len(rules)
    relation_count = len(relations)

    domains = sorted(set(e.domain for e in entities))

    return templates.TemplateResponse(request, "settings/page.html",{
            "request": request,
            "entity_count": entity_count,
            "rule_count": rule_count,
            "relation_count": relation_count,
            "domains": domains,
            "active_page": "settings",
        },
    )

"""Web Console router — 知识图谱管理界面。

提供基于 Jinja2 模板的 Web 管理界面，用于管理实体、规则、关系等。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ai_nexus.api.dependencies import (
    get_audit_repo,
    get_entity_repo,
    get_graph_service,
    get_relation_repo,
    get_rule_repo,
)
from ai_nexus.models.entity import EntityCreate, EntityUpdate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.models.rule import RuleCreate, RuleUpdate
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService

router = APIRouter(prefix="/console", tags=["console"])
templates = Jinja2Templates(directory="templates")

GraphSvc = Annotated[GraphService, Depends(get_graph_service)]
EntityRepoInj = Annotated[EntityRepo, Depends(get_entity_repo)]
RuleRepoInj = Annotated[RuleRepo, Depends(get_rule_repo)]
RelationRepoInj = Annotated[RelationRepo, Depends(get_relation_repo)]
AuditRepoInj = Annotated[AuditRepo, Depends(get_audit_repo)]


# --- Base Dashboard ---

@router.get("/")
async def dashboard(request: Request, graph_svc: GraphSvc):
    """主控制台仪表板，显示系统概览。"""
    entities = await graph_svc._entities.list(limit=10)
    rules = await graph_svc._rules.list(limit=10)
    relations = await graph_svc._relations.list(limit=10)
    pending_audits = await graph_svc._audit_repo.list_pending()

    return templates.TemplateResponse(
        "dashboard.html",
        {
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

    return templates.TemplateResponse(
        "entities/list.html",
        {
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
        "entities/form.html",
        {"request": request, "active_page": "entities", "entity": None},
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
        "entities/form.html",
        {"request": request, "active_page": "entities", "entity": entity},
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

    return templates.TemplateResponse(
        "rules/list.html",
        {
            "request": request,
            "rules": rules,
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
        "rules/form.html",
        {"request": request, "active_page": "rules", "rule": None},
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
        "rules/form.html",
        {"request": request, "active_page": "rules", "rule": rule},
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

    return templates.TemplateResponse(
        "relations/list.html",
        {
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
    return templates.TemplateResponse(
        "relations/form.html",
        {
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
):
    """审核工作流页面，显示待审核候选和审核历史。"""
    pending = await audit_repo.list_pending()

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

    return templates.TemplateResponse(
        "audit/list.html",
        {
            "request": request,
            "pending": pending,
            "audit_history": audit_history,
            "active_page": "audit",
        },
    )


@router.post("/audit/{record_id}/approve")
async def approve_audit_item(
    record_id: int,
    audit_repo: AuditRepoInj,
):
    """批准审核项。"""
    from ai_nexus.models.audit import AuditLogCreate

    await audit_repo.create(
        AuditLogCreate(
            table_name="knowledge_audit_log",
            record_id=record_id,
            action="approve",
            reviewer="console",
        )
    )
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

    return templates.TemplateResponse(
        "lint/dashboard.html",
        {
            "request": request,
            "report": report,
            "active_page": "lint",
        },
    )


# --- Import Management ---

@router.get("/imports")
async def imports_page(request: Request):
    """导入管理页面，显示飞书导入和单文档导入。"""
    return templates.TemplateResponse(
        "imports/page.html",
        {
            "request": request,
            "active_page": "imports",
        },
    )


@router.post("/imports/feishu")
async def trigger_feishu_import(
    request: Request,
    space_id: str = Form(...),
    domain_hint: str = Form(default=""),
):
    """触发飞书知识空间导入。

    通过内部 HTTP 调用 ingest API 执行导入。
    """
    import httpx

    # 构建请求体
    payload = {
        "space_id": space_id,
        "domain_hint": domain_hint if domain_hint else None,
        "dry_run": False,
    }

    # 获取基础 URL
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/ingest/feishu",
            json=payload,
            timeout=300.0,  # 5分钟超时，因为导入可能需要较长时间
        )
        if response.status_code != 200:
            # 导入失败，可以在这里记录日志
            pass

    return RedirectResponse(url="/console/imports", status_code=303)


@router.post("/imports/document")
async def trigger_document_import(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    domain_hint: str = Form(default=""),
):
    """触发单文档导入。

    通过内部 HTTP 调用 ingest API 执行导入。
    """
    import httpx

    # 构建请求体
    payload = {
        "title": title,
        "content": content,
        "source": "manual",
        "domain_hint": domain_hint if domain_hint else None,
        "dry_run": False,
    }

    # 获取基础 URL
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/ingest/document",
            json=payload,
            timeout=60.0,
        )
        if response.status_code != 200:
            # 导入失败，可以在这里记录日志
            pass

    return RedirectResponse(url="/console/imports", status_code=303)


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

    return templates.TemplateResponse(
        "settings/page.html",
        {
            "request": request,
            "entity_count": entity_count,
            "rule_count": rule_count,
            "relation_count": relation_count,
            "domains": domains,
            "active_page": "settings",
        },
    )

"""REST API 路由：知识图谱 CRUD + 统一搜索。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ai_nexus.api.dependencies import get_graph_service, get_query_service
from ai_nexus.models.entity import Entity, EntityCreate, EntityUpdate
from ai_nexus.models.rule import Rule, RuleCreate, RuleUpdate
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService

router = APIRouter(prefix="/api")

GraphSvc = Annotated[GraphService, Depends(get_graph_service)]
QuerySvc = Annotated[QueryService, Depends(get_query_service)]


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


@router.get("/entities", response_model=list[Entity])
async def list_entities(svc: GraphSvc, domain: str | None = None, limit: int = 100):
    return await svc._entities.list(domain=domain, limit=limit)


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


@router.get("/rules", response_model=list[Rule])
async def list_rules(
    svc: GraphSvc,
    domain: str | None = None,
    severity: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
):
    return await svc._rules.list(
        domain=domain, severity=severity, status=status_filter, limit=limit
    )


# --- Unified Search ---

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

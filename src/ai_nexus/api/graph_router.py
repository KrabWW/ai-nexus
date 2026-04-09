"""Graph visualization API router.

Provides the web interface and data endpoints for knowledge graph visualization.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse

from ai_nexus.api.dependencies import (
    get_entity_repo,
    get_graph_service,
    get_relation_repo,
    get_rule_repo,
)
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService

router = APIRouter()

GraphSvc = Annotated[GraphService, Depends(get_graph_service)]
EntityRepoInj = Annotated[EntityRepo, Depends(get_entity_repo)]
RuleRepoInj = Annotated[RuleRepo, Depends(get_rule_repo)]
RelationRepoInj = Annotated[RelationRepo, Depends(get_relation_repo)]


@router.get("/graph", response_class=HTMLResponse)
async def get_graph_page(request: Request):
    """Serve the interactive graph visualization page."""
    static_path = (
        Path(__file__).parent.parent.parent.parent / "static" / "index.html"
    )
    return FileResponse(static_path)


@router.get("/api/graph/data")
async def get_graph_data(
    entity_repo: EntityRepoInj,
    rule_repo: RuleRepoInj,
    relation_repo: RelationRepoInj,
):
    """Return all entities, relations, and rules as graph JSON.

    The response format:
    {
        "nodes": [
            {"id": "entity:1", "name": "...", "type": "entity", "domain": "...", ...},
            {"id": "rule:1", "name": "...", "type": "rule", "domain": "...", "severity": "...", ...}
        ],
        "links": [
            {"source": "entity:1", "target": "entity:2", "type": "related_to"}
        ]
    }

    Node IDs are prefixed with type (entity: or rule:) to avoid collisions.
    """
    # Fetch all entities, rules, and relations
    entities = await entity_repo.list(limit=1000)
    rules = await rule_repo.list(status="approved", limit=1000)

    # Build entity nodes
    nodes = []
    entity_id_map = {}

    for entity in entities:
        node_id = f"entity:{entity.id}"
        entity_id_map[entity.id] = node_id
        nodes.append({
            "id": node_id,
            "name": entity.name,
            "type": "entity",
            "domain": entity.domain,
            "entity_type": entity.type,
            "description": entity.description,
            "attributes": entity.attributes,
            "status": entity.status,
        })

    # Build rule nodes
    rule_id_map = {}

    for rule in rules:
        node_id = f"rule:{rule.id}"
        rule_id_map[rule.id] = node_id
        nodes.append({
            "id": node_id,
            "name": rule.name,
            "type": "rule",
            "domain": rule.domain,
            "severity": rule.severity,
            "description": rule.description,
            "conditions": rule.conditions,
            "status": rule.status,
            "confidence": rule.confidence,
        })

    # Build links from relations
    links = []
    db = entity_repo._db

    rows = await db.fetchall(
        "SELECT source_entity_id, relation_type, target_entity_id "
        "FROM relations WHERE status = 'approved'"
    )

    for source_id, rel_type, target_id in rows:
        source_node = entity_id_map.get(source_id)
        target_node = entity_id_map.get(target_id)
        if source_node and target_node:
            links.append({
                "source": source_node,
                "target": target_node,
                "type": rel_type,
            })

    # Also create links between rules and their related entities
    for rule in rules:
        rule_node = rule_id_map.get(rule.id)
        if rule_node and rule.related_entity_ids:
            for entity_id in rule.related_entity_ids:
                entity_node = entity_id_map.get(entity_id)
                if entity_node:
                    links.append({
                        "source": rule_node,
                        "target": entity_node,
                        "type": "governs",
                    })

    return {
        "nodes": nodes,
        "links": links,
    }


@router.get("/static/{file_path:path}")
async def get_static_file(file_path: str):
    """Serve static files (CSS, JS)."""
    static_path = (
        Path(__file__).parent.parent.parent.parent / "static" / file_path
    )
    if static_path.exists():
        return FileResponse(static_path)
    return {"error": "File not found"}

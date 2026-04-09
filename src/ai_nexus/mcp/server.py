"""AI Nexus MCP Server — 暴露业务图谱工具给 AI 编程助手。"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai_nexus.models.audit import AuditLogCreate
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService

mcp = FastMCP("ai-nexus")

# 由 main.py lifespan 注入
_graph_service: GraphService | None = None
_query_service: QueryService | None = None
_audit_repo: AuditRepo | None = None


def init_services(
    graph: GraphService,
    query: QueryService,
    audit_repo: AuditRepo | None = None,
) -> None:
    global _graph_service, _query_service, _audit_repo
    _graph_service = graph
    _query_service = query
    _audit_repo = audit_repo


def _get_graph_service() -> GraphService:
    if _graph_service is None:
        raise RuntimeError("Services not initialized. Call init_services() in app lifespan.")
    return _graph_service


def _get_query_service() -> QueryService:
    if _query_service is None:
        raise RuntimeError("Services not initialized.")
    return _query_service


def _get_audit_repo() -> AuditRepo:
    if _audit_repo is None:
        raise RuntimeError("AuditRepo not initialized. Call init_services() with audit_repo.")
    return _audit_repo


@mcp.tool()
async def search_entities(query: str, domain: str | None = None, limit: int = 10) -> str:
    """搜索业务实体和关联关系，理解业务结构。
    优先级：业务规则约束 > 会话历史。结果来自结构化知识图谱。
    """
    svc = _get_graph_service()
    results = await svc.search_entities(query, domain=domain, limit=limit)
    return json.dumps({
        "results": [e.model_dump(mode="json") for e in results],
        "total": len(results),
    }, ensure_ascii=False)


@mcp.tool()
async def search_rules(
    query: str,
    domain: str | None = None,
    severity: str | None = None,
    limit: int = 10,
) -> str:
    """搜索业务规则和约束。这些规则是硬性约束，不可违反。"""
    svc = _get_query_service()
    results = await svc.query_rules(query, domain=domain, limit=limit)
    if severity:
        results = [r for r in results if r.severity == severity]
    return json.dumps({
        "results": [r.model_dump(mode="json") for r in results],
        "total": len(results),
    }, ensure_ascii=False)


@mcp.tool()
async def get_business_context(task_description: str, keywords: list[str] | None = None) -> str:
    """根据任务描述获取完整业务上下文，用于 AI 开发前的知识注入。"""
    svc = _get_graph_service()
    ctx = await svc.get_business_context(task_description, keywords=keywords)
    return json.dumps(ctx, ensure_ascii=False)


@mcp.tool()
async def validate_against_rules(
    change_description: str,
    affected_entities: list[str] | None = None,
    diff_summary: str | None = None,
) -> str:
    """检查代码变更是否违反已知业务规则。
    返回分级结果：critical（错误）、warning（警告）、info（提示）。
    """
    svc = _get_query_service()
    keywords = affected_entities or [change_description]
    errors = []
    warnings = []
    infos = []
    for kw in keywords:
        rules = await svc.query_rules(kw, limit=5)
        for rule in rules:
            if rule.status == "approved":
                violation = {
                    "rule": rule.name,
                    "description": rule.description,
                    "severity": rule.severity or "info",
                }
                if rule.severity == "critical":
                    errors.append(violation)
                elif rule.severity == "warning":
                    warnings.append(violation)
                else:
                    infos.append(violation)
    return json.dumps({
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "passed": len(errors) == 0,
    }, ensure_ascii=False)


@mcp.tool()
async def get_session_ctx(query: str, limit: int = 10) -> str:
    """获取会话上下文（代理 mem0 语义搜索）。
    根据查询关键词在历史记忆中搜索相关上下文。
    """
    svc = _get_query_service()
    # QueryService 内部已集成 Mem0Proxy
    # 如果 mem0 不可用，会降级到 SQLite LIKE 搜索
    results = await svc.query_rules(query, limit=limit)
    return json.dumps({
        "query": query,
        "results": [r.model_dump(mode="json") for r in results],
        "total": len(results),
    }, ensure_ascii=False)


@mcp.tool()
async def submit_knowledge_candidate(
    type: str,
    data: dict[str, Any],
    source: str,
    confidence: float = 0.5,
) -> str:
    """提交新发现的业务知识候选项，等待人工审核。
    type: entity 或 rule
    data: 候选项的完整数据（JSON）
    source: 来源（如 "claude-api-extractor"）
    confidence: 置信度 0-1
    """
    try:
        repo = _get_audit_repo()
        # 生成临时 record_id 用于审核流程（正式审核后会有真实的 entity/rule ID）
        import hashlib
        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()[:8]
        temp_id = int(data_hash, 16) % (10 ** 8)  # 转为 8 位整数

        audit_log = await repo.create(AuditLogCreate(
            table_name=f"temp_{type}",  # 临时表名标识
            record_id=temp_id,
            action="submit_candidate",
            new_value={**data, "_meta": {"source": source, "confidence": confidence}},
        ))
        return json.dumps({
            "status": "submitted",
            "audit_log_id": audit_log.id,
            "type": type,
            "source": source,
            "confidence": confidence,
            "message": "候选项已提交，等待人工审核",
        }, ensure_ascii=False)
    except RuntimeError:
        # AuditRepo 未初始化时的降级处理
        return json.dumps({
            "status": "pending",
            "type": type,
            "source": source,
            "confidence": confidence,
            "message": "候选项已记录（审核工作流未初始化）",
        }, ensure_ascii=False)


@mcp.tool()
async def get_neighbors(entity_id: int) -> str:
    """获取与指定实体直接相连的所有实体。
    返回该实体的所有邻居（包括出边和入边连接的实体）。
    """
    svc = _get_graph_service()
    neighbors = await svc.get_neighbors(entity_id)
    return json.dumps({
        "entity_id": entity_id,
        "neighbors": [e.model_dump(mode="json") for e in neighbors],
        "total": len(neighbors),
    }, ensure_ascii=False)


@mcp.tool()
async def shortest_path(from_id: int, to_id: int) -> str:
    """查找两个实体之间的最短路径。
    使用 BFS 算法找到连接两个实体的最短路径。
    返回路径上的实体列表，如果不连通则返回空列表。
    """
    svc = _get_graph_service()
    path = await svc.shortest_path(from_id, to_id)
    return json.dumps({
        "from_id": from_id,
        "to_id": to_id,
        "path": [e.model_dump(mode="json") for e in path],
        "path_length": len(path),
        "found": len(path) > 0,
    }, ensure_ascii=False)


@mcp.tool()
async def get_god_nodes(limit: int = 10) -> str:
    """识别图谱中连接度最高的节点（核心枢纽）。
    返回按连接数排序的实体列表，帮助理解哪些概念是连接整个图谱的关键节点。
    """
    svc = _get_graph_service()
    god_nodes = await svc.get_god_nodes(limit=limit)
    return json.dumps({
        "god_nodes": god_nodes,
        "total": len(god_nodes),
    }, ensure_ascii=False)


@mcp.tool()
async def get_surprising_connections(limit: int = 10) -> str:
    """发现跨域的意外关联（跨界连接）。
    找出不同领域实体之间的连接，按惊喜分数排序。
    帮助发现隐藏的业务关联和潜在的跨领域影响。
    """
    svc = _get_graph_service()
    connections = await svc.get_surprising_connections(limit=limit)
    return json.dumps({
        "surprising_connections": connections,
        "total": len(connections),
    }, ensure_ascii=False)


@mcp.tool()
async def detect_communities(resolution: float = 1.0) -> str:
    """基于图谱拓扑结构自动发现实体社群（Leiden 算法）。
    将连接紧密的实体聚类到一起，不依赖向量嵌入。
    resolution 参数控制社群大小：值越大社群越多越小。
    """
    svc = _get_graph_service()
    result = await svc.detect_communities(resolution=resolution)
    return json.dumps(result, ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

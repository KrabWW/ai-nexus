"""AI Nexus MCP Server — 暴露业务图谱工具给 AI 编程助手。"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService

mcp = FastMCP("ai-nexus")

# 由 main.py lifespan 注入
_graph_service: GraphService | None = None
_query_service: QueryService | None = None


def init_services(graph: GraphService, query: QueryService) -> None:
    global _graph_service, _query_service
    _graph_service = graph
    _query_service = query


def _get_graph_service() -> GraphService:
    if _graph_service is None:
        raise RuntimeError("Services not initialized. Call init_services() in app lifespan.")
    return _graph_service


def _get_query_service() -> QueryService:
    if _query_service is None:
        raise RuntimeError("Services not initialized.")
    return _query_service


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
    """检查代码变更是否违反已知业务规则。"""
    svc = _get_query_service()
    keywords = affected_entities or [change_description]
    violations = []
    for kw in keywords:
        rules = await svc.query_rules(kw, limit=5)
        for rule in rules:
            if rule.status == "approved" and rule.severity == "critical":
                violations.append({
                    "rule": rule.name,
                    "description": rule.description,
                    "severity": rule.severity,
                })
    return json.dumps({
        "violations": violations,
        "passed": len(violations) == 0,
    }, ensure_ascii=False)


@mcp.tool()
async def submit_knowledge_candidate(
    type: str,
    data: dict[str, Any],
    source: str,
    confidence: float = 0.5,
) -> str:
    """提交新发现的业务知识候选项，等待人工审核。"""
    # AuditRepo 在 Phase 1 审核工作流（Task 14）中完整实现
    # 这里先记录到 audit log，等 Task 14 补充完整审核逻辑
    return json.dumps({
        "status": "submitted",
        "type": type,
        "source": source,
        "confidence": confidence,
        "message": "候选项已提交，等待人工审核",
    }, ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

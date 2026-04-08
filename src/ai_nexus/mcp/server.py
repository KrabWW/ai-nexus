"""AI Nexus MCP Server — 暴露业务图谱工具给 AI 编程助手。

Phase 0: 框架搭建，验证 MCP 工具链。
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-nexus")


@mcp.tool()
async def search_entities(query: str, domain: str | None = None, limit: int = 10) -> str:
    """搜索业务实体和关联关系，理解业务结构。"""
    # Phase 0: 返回占位响应，验证工具链
    return json.dumps({
        "status": "ok",
        "message": "Phase 0: tool chain verified",
        "query": query,
        "results": [],
    }, ensure_ascii=False)


@mcp.tool()
async def search_rules(
    query: str,
    domain: str | None = None,
    severity: str | None = None,
    limit: int = 10,
) -> str:
    """搜索业务规则和约束，确保代码符合业务要求。"""
    return json.dumps({
        "status": "ok",
        "message": "Phase 0: tool chain verified",
        "query": query,
        "results": [],
    }, ensure_ascii=False)


@mcp.tool()
async def get_business_context(task_description: str, keywords: list[str] | None = None) -> str:
    """根据任务描述获取完整业务上下文，用于 AI 开发前的知识注入。"""
    return json.dumps({
        "status": "ok",
        "message": "Phase 0: tool chain verified",
        "task": task_description,
        "entities": [],
        "rules": [],
        "relations": [],
    }, ensure_ascii=False)


@mcp.tool()
async def validate_against_rules(
    change_description: str,
    affected_entities: list[str] | None = None,
    diff_summary: str | None = None,
) -> str:
    """检查代码变更是否违反已知业务规则。"""
    return json.dumps({
        "status": "ok",
        "violations": [],
        "message": "Phase 0: tool chain verified",
    }, ensure_ascii=False)


@mcp.tool()
async def submit_knowledge_candidate(
    type: str,
    data: dict[str, Any],
    source: str,
    confidence: float = 0.5,
) -> str:
    """提交新发现的业务知识候选项，等待人工审核。"""
    return json.dumps({
        "status": "ok",
        "message": "Phase 0: candidate submitted (placeholder)",
        "type": type,
        "source": source,
    }, ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

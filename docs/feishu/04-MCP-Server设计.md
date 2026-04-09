# 04-MCP Server设计（修订版）

> 来源：飞书知识库 | 最后编辑：2026-04-06

## 定位

MCP Server 是 AI Nexus 与 AI 编程助手之间的桥梁。只暴露业务图谱相关工具，不做通用检索（由 OpenViking 代理）。

## MCP 工具定义

### 1. search_entities — 搜索业务实体

搜索业务实体及其关联关系，帮助 AI 理解业务结构。

```json
{
  "name": "search_entities",
  "description": "搜索业务实体和关联关系，理解业务结构",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "搜索关键词" },
      "domain": { "type": "string", "description": "业务领域过滤" },
      "include_relations": { "type": "boolean", "default": true },
      "limit": { "type": "integer", "default": 10 }
    },
    "required": ["query"]
  }
}
```

### 2. search_rules — 搜索业务规则

搜索业务规则和约束，确保代码符合业务要求。

```json
{
  "name": "search_rules",
  "description": "搜索业务规则和约束，确保代码符合业务要求",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "搜索关键词" },
      "domain": { "type": "string", "description": "业务领域" },
      "severity": { "type": "string", "description": "严重级别: error/warning/info" },
      "limit": { "type": "integer", "default": 10 }
    },
    "required": ["query"]
  }
}
```

### 3. get_business_context — 获取业务上下文（给 pre_plan Hook 用）

根据任务描述，自动检索相关实体、关系和规则，返回完整的业务上下文。

```json
{
  "name": "get_business_context",
  "description": "根据任务描述获取完整业务上下文，用于 AI 开发前的知识注入",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task_description": { "type": "string", "description": "任务描述" },
      "keywords": { "type": "array", "items": { "type": "string" }, "description": "关键业务术语" }
    },
    "required": ["task_description"]
  }
}
```

### 4. validate_against_rules — 规则校验（给 pre_commit Hook 用）

检查代码变更描述是否违反已知业务规则。

```json
{
  "name": "validate_against_rules",
  "description": "检查代码变更是否违反已知业务规则",
  "inputSchema": {
    "type": "object",
    "properties": {
      "change_description": { "type": "string", "description": "变更描述" },
      "affected_entities": { "type": "array", "items": { "type": "string" }, "description": "涉及的实体名称" },
      "diff_summary": { "type": "string", "description": "代码 diff 摘要" }
    },
    "required": ["change_description"]
  }
}
```

### 5. submit_knowledge_candidate — 提交知识候选项

AI 或 Hook 自动发现新的业务知识时，提交为候选项等待人工审核。

```json
{
  "name": "submit_knowledge_candidate",
  "description": "提交新发现的业务知识候选项，等待人工审核",
  "inputSchema": {
    "type": "object",
    "properties": {
      "type": { "type": "string", "enum": ["entity", "relation", "rule"] },
      "data": { "type": "object", "description": "知识数据" },
      "source": { "type": "string", "description": "来源: commit/pr/log/manual" },
      "confidence": { "type": "number", "description": "置信度 0-1" }
    },
    "required": ["type", "data", "source"]
  }
}
```

## 与 mem0/OpenViking 的共存

AI Nexus 和 mem0/OpenViking 在 L2 知识治理层**平级共存**，不是包含关系。两者各自暴露 MCP Server，Claude Code 通过同一个 MCP 入口同时调用。

| 类别 | 工具 | 数据源 | 优先级 |
|------|------|--------|--------|
| AI Nexus 自有 | search_entities, search_rules, get_business_context, validate_against_rules, submit_knowledge_candidate | SQLite（图谱核心） | **约束** — 不可违反 |
| mem0 代理 | get_session_ctx | mem0 API（内含向量库） | **参考** — 可被覆盖 |
| OpenViking 代理 | search_documents, get_context | OpenViking API | **参考** — 可被覆盖 |

核心原则：**代理它，不是替代它。** AI Nexus 不做会话记忆功能，mem0 更新迭代自动跟着受益。

这个优先级要在 MCP 工具的 description 里写清楚，让 LLM 知道谁的权重更重。

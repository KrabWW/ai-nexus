# AI Nexus 用户指南

> 让 AI 像资深员工一样懂业务规则

## 1. 它是什么？

AI Nexus 是一个**业务知识治理层**。它把团队的业务规则、实体关系、约束条件结构化存储，然后通过 MCP 协议和 REST API 暴露给 AI 编程助手（Claude Code、Cursor、Copilot 等）。

简单说：**你在业务上踩过的坑，AI 下次不会再踩。**

## 2. 它有页面吗？

**没有传统前端页面。** AI Nexus 是一个纯后端 HTTP 服务，提供两种交互方式：

### 2.1 Swagger UI（内置交互式文档页）

启动服务后，浏览器访问：

```
http://localhost:8000/docs
```

这是 FastAPI 自动生成的交互式 API 文档页面，你可以：
- 查看所有 API 端点的参数和返回值
- 直接在页面上点 "Try it out" 测试每个接口
- 查看请求/响应示例

### 2.2 REST API（给人类用的接口）

通过 curl、Postman 或任何 HTTP 客户端调用。

### 2.3 MCP 协议（给 AI 用的接口）

AI 编程助手通过 MCP 协议调用，人类不需要直接操作。

## 3. 快速启动

### 3.1 安装依赖

```bash
pip install -e ".[dev]"
```

### 3.2 启动服务

```bash
uvicorn ai_nexus.main:app --reload
```

默认监听 `http://localhost:8000`，可通过环境变量覆盖：

```bash
AI_NEXUS_HOST=0.0.0.0 AI_NEXUS_PORT=9000 uvicorn ai_nexus.main:app --reload
```

### 3.3 验证

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

### 3.4 （可选）启动 mem0 语义检索后端

```bash
docker compose up -d mem0
```

不启动 mem0 也能用，系统会自动降级为 SQLite LIKE 查询。

## 4. 核心功能详解

### 4.1 业务实体管理

**实体**是业务世界里的"名词"：订单、用户、商品、支付通道等。

```bash
# 创建实体
curl -X POST http://localhost:8000/api/entities \
  -H "Content-Type: application/json" \
  -d '{
    "name": "订单",
    "type": "concept",
    "domain": "交易",
    "description": "用户下单产生的交易记录"
  }'

# 查看某个实体
curl http://localhost:8000/api/entities/1

# 列出所有实体（可按 domain 过滤）
curl "http://localhost:8000/api/entities?domain=交易"

# 更新实体
curl -X PUT http://localhost:8000/api/entities/1 \
  -H "Content-Type: application/json" \
  -d '{"description": "包含商品和支付信息的交易记录"}'

# 删除实体
curl -X DELETE http://localhost:8000/api/entities/1
```

### 4.2 业务规则管理

**规则**是业务上的"不可违反的约束"。

```bash
# 创建规则
curl -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "禁止直接删除订单",
    "description": "订单只能标记为取消状态，不能物理删除数据",
    "domain": "交易",
    "severity": "critical",
    "status": "approved"
  }'

# 列出规则（支持多维度过滤）
curl "http://localhost:8000/api/rules?domain=交易&severity=critical"

# severity 等级：
#   critical  — 必须遵守，违反会导致数据丢失或资金风险
#   warning   — 建议遵守，违反可能引发问题
#   info      — 参考信息
```

### 4.3 统一搜索

```bash
# 搜索实体
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "支付", "type": "entities"}'

# 搜索规则（默认）
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "退款", "type": "rules", "domain": "交易"}'
```

**搜索路由策略（自动，无需配置）：**

```
1. 先尝试结构化查询（SQLite 关键词匹配）
   ↓ 没命中
2. 走 mem0 语义检索（模糊匹配，需要 docker compose up mem0）
   ↓ mem0 不可用
3. 降级为 SQLite LIKE 模糊查询
```

### 4.4 知识审核工作流

新知识不会直接生效，需要经过审核：

```
提交候选项 → status='pending' → 人工审核
    ├── approve → 正式生效
    └── reject  → 驳回
```

```bash
# 提交知识候选项
curl -X POST http://localhost:8000/api/audit/candidates \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "rules",
    "record_id": 10,
    "action": "submit_candidate",
    "new_value": {"name": "退款须72小时内处理"}
  }'

# 查看待审核列表
curl http://localhost:8000/api/audit/pending

# 批准
curl -X POST http://localhost:8000/api/audit/10/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "张三"}'

# 驳回
curl -X POST http://localhost:8000/api/audit/10/reject \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "张三"}'
```

### 4.5 开发流程 Hook

这是 AI Nexus 最核心的能力——在开发流程中自动注入业务知识。

#### pre-plan：开发前注入业务上下文

在你开始写代码之前，AI 助手自动获取相关的业务规则和实体信息：

```bash
curl -X POST http://localhost:8000/api/hooks/pre-plan \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "实现订单退款功能",
    "keywords": ["订单", "退款", "支付"]
  }'
```

返回值示例：
```json
{
  "task": "实现订单退款功能",
  "entities": [
    {"id": 1, "name": "订单", "type": "concept", "domain": "交易"},
    {"id": 2, "name": "退款单", "type": "concept", "domain": "退款"}
  ],
  "rules": [
    {"id": 1, "name": "禁止直接删除订单", "severity": "critical"},
    {"id": 2, "name": "退款须72小时内处理", "severity": "warning"}
  ]
}
```

AI 助手拿到这些信息后，就知道：不能物理删除订单，退款有72小时时效。

#### pre-commit：提交前校验业务规则

在代码提交前，自动检查是否违反已知业务规则：

```bash
curl -X POST http://localhost:8000/api/hooks/pre-commit \
  -H "Content-Type: application/json" \
  -d '{
    "change_description": "删除了 orders 表的 delete 接口",
    "affected_entities": ["订单"],
    "diff_summary": "- router.delete('/orders/{id}')"
  }'
```

返回值示例：
```json
{
  "violations": [
    {
      "rule": "禁止直接删除订单",
      "description": "订单只能标记为取消状态，不能物理删除数据",
      "severity": "critical"
    }
  ],
  "passed": false
}
```

## 5. 它如何帮助 AI 编程？

### 5.1 通过 MCP 协议集成

AI Nexus 作为 MCP Server 运行，AI 编程助手（Claude Code、Cursor 等）可以直接调用以下 5 个工具：

| MCP 工具 | 作用 | 什么时候用 |
|----------|------|------------|
| `search_entities` | 搜索业务实体 | AI 需要了解业务概念时 |
| `search_rules` | 搜索业务规则 | AI 需要知道约束条件时 |
| `get_business_context` | 获取完整业务上下文 | AI 开始开发任务前（pre-plan） |
| `validate_against_rules` | 校验变更是否违反规则 | AI 准备提交代码前（pre-commit） |
| `submit_knowledge_candidate` | 提交新发现的知识 | AI 在开发中发现新的业务规则时 |

### 5.2 在 Claude Code 中配置

在 Claude Code 的 MCP 配置中添加 AI Nexus：

```json
{
  "mcpServers": {
    "ai-nexus": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

配置后，Claude Code 就能直接调用上述 5 个工具。

### 5.3 工作流程示例

```
场景：你让 Claude Code "实现订单退款功能"

1. [pre-plan] Claude Code 自动调用 get_business_context
   → 获取到："订单不能物理删除"、"退款须72小时内处理" 等规则
   → AI 在编码时就会遵守这些约束

2. [编码中] AI 遇到不确定的业务逻辑
   → 调用 search_entities("退款") 了解退款相关实体
   → 调用 search_rules("退款") 查看退款相关规则

3. [pre-commit] AI 准备提交代码
   → 自动调用 validate_against_rules 检查变更
   → 如果违反了 critical 规则，会收到警告并修正

4. [知识发现] AI 在开发中发现新的业务规律
   → 调用 submit_knowledge_candidate 提交候选规则
   → 人工审核后正式入库，下次所有 AI 都能受益
```

### 5.4 和 mem0 的关系

```
AI Nexus（你建的）        mem0（通用记忆）
├── 业务规则（约束）       ├── 会话历史（参考）
├── 实体关系（结构化）     ├── 文档知识（参考）
└── 优先级：高             └── 优先级：低

当两者冲突时，以 AI Nexus 的业务规则为准。
```

## 6. 架构概览

```
    AI 编码工具（Claude Code / Cursor / Copilot）
           │                │
           ▼                ▼
    ┌──────────────┐  ┌──────────┐
    │  AI Nexus    │  │  mem0    │
    │  规则+实体    │  │  记忆层  │
    │  MCP Server  │  │  MCP Svr │
    └──────┬───────┘  └──────────┘
           │
     ┌─────┴──────┐
     │  SQLite    │
     │  entities  │
     │  relations │
     │  rules     │
     │  audit_log │
     └────────────┘
```

## 7. API 速查表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/entities` | 创建实体 |
| GET | `/api/entities` | 列出实体 |
| GET | `/api/entities/{id}` | 获取实体 |
| PUT | `/api/entities/{id}` | 更新实体 |
| DELETE | `/api/entities/{id}` | 删除实体 |
| POST | `/api/rules` | 创建规则 |
| GET | `/api/rules` | 列出规则 |
| GET | `/api/rules/{id}` | 获取规则 |
| PUT | `/api/rules/{id}` | 更新规则 |
| DELETE | `/api/rules/{id}` | 删除规则 |
| POST | `/api/search` | 统一搜索 |
| POST | `/api/audit/candidates` | 提交知识候选 |
| GET | `/api/audit/pending` | 查看待审核 |
| POST | `/api/audit/{id}/approve` | 批准 |
| POST | `/api/audit/{id}/reject` | 驳回 |
| POST | `/api/hooks/pre-plan` | 开发前注入上下文 |
| POST | `/api/hooks/pre-commit` | 提交前规则校验 |

## 8. 配置项

所有配置通过环境变量覆盖，前缀为 `AI_NEXUS_`：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `AI_NEXUS_HOST` | `0.0.0.0` | 服务绑定地址 |
| `AI_NEXUS_PORT` | `8000` | 服务端口 |
| `AI_NEXUS_SQLITE_PATH` | `data/ai_nexus.db` | SQLite 数据库路径 |
| `AI_NEXUS_MEM0_API_URL` | `http://localhost:8080` | mem0 服务地址 |
| `AI_NEXUS_ANTHROPIC_API_KEY` | （空） | Claude API Key（AI 抽取用） |

也可以在项目根目录创建 `.env` 文件：

```bash
AI_NEXUS_SQLITE_PATH=data/ai_nexus.db
AI_NEXUS_MEM0_API_URL=http://localhost:8080
```

## 9. 当前状态

### 已完成（Phase 0 + Phase 1）

- 项目脚手架 + 分层目录结构
- SQLite 数据库 + 迁移机制
- Pydantic 数据模型（Entity / Relation / Rule / AuditLog）
- 4 个 Repo 层（单表 CRUD + 搜索）
- GraphService（图遍历查询 + 业务上下文组装）
- QueryService（三级查询路由：结构化 → mem0 → 降级）
- Mem0Proxy（httpx 代理 mem0 REST API）
- MCP Server 5 个工具（对接真实 Service）
- REST API 全部端点（CRUD + 搜索 + 审核 + Hook）
- 测试覆盖（pytest）

### 规划中

- **Phase 2** — Claude Code hooks 自动触发（pre-plan / pre-commit 脚本）
- **Phase 3** — Claude API 知识抽取引擎（从飞书文档自动抽取规则）
- **Phase 3** — 知识 Lint（冲突检测、死规则扫描）
- **Phase 3** — 数据飞轮（PR 违规事件回写图谱，自动加强规则置信度）

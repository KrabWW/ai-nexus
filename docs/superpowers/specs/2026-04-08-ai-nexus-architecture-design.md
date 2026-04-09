# AI Nexus 架构设计文档

> 日期: 2026-04-08 (v3 — 飞书文档对齐)
> 状态: Approved
> 阶段: Phase 0 → Phase 1

## 修订记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-04-08 | v1 | 初始设计 |
| 2026-04-08 | v2 | Phase 0 评审: mem0→Qdrant, MCP 集成修正 |
| 2026-04-09 | v3 | 飞书文档 + 架构全景图对齐: 去向量库, mem0 平级共存, 查询路由, 数据飞轮, 知识 Lint |

## 1. 项目定位

AI Nexus 是**业务知识治理层**，让 AI 像资深员工一样懂业务规则。

核心三件事：
1. **业务知识图谱** — 实体 + 关系 + 规则的结构化 CRUD
2. **开发流程 Hook** — pre_plan 注入业务上下文 + pre_commit 校验业务规则
3. **知识审核工作流** — AI 抽取知识候选项 + 人工审核入库

### 不做什么
- 不自建向量数据库层（语义检索是 mem0/OpenViking 的职责）
- 不做通用 Agent 记忆管理（mem0/OpenViking 的赛道）
- 不做文档库（飞书/Confluence 已经做了）
- 不做会话记忆（mem0 代理，不重复造轮子）

## 2. 五层全景架构

```
L3  ┌─────────────────────────────────────────────┐
    │  AI 编码工具层                                  │
    │  Claude Code / Cursor / Copilot                │
    │  同一 MCP 入口调用                              │
    └──────────────┬──────────────┬─────────────────┘
                   │              │
L2  ┌──────────────▼──────┐ ┌────▼──────────────────┐
    │   AI Nexus (你)      │ │ mem0 / OpenViking      │
    │   实体图谱+规则引擎    │◄►│ 通用记忆层              │
    │   AI 抽取+人工审核    │并存│ 会话历史+文档           │
    │   MCP Server 暴露    │ │ 语义向量检索            │
    │                     │ │ MCP Server 暴露        │
    └─────────────────────┘ └────────────────────────┘
               ▲                        ▲
L1  ┌──────────┴────────────────────────┤
    │  知识原料层                          │
    │  llm-wiki │ 飞书文档 │ 业务知识       │
    └────────────────────────────────────┘
                        │
L0  ┌────────────────┐  ┌▼──────────────────┐
    │ 图DB/关系型DB    │  │ 向量数据库          │
    │ SQLite (MVP)    │  │ mem0 内部管理       │
    │ PostgreSQL (后期)│  │ AI Nexus 不直接管理 │
    └─────────────────┘  └──────────────────┘
```

### 核心原则：代理它，不是替代它

- AI Nexus 和 mem0/OpenViking **平级共存**，通过各自的 MCP Server 暴露
- Claude Code 通过同一个 MCP 入口同时调用两者
- AI Nexus = 业务规则（**约束**，不可违反）
- mem0 = 会话记忆（**参考**，可被覆盖）
- 这个优先级要在 MCP 工具的 description 里写清楚

## 3. 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 部署模式 | 团队共享 HTTP 服务 | 团队共享知识库，多消费方接入 |
| 架构模式 | 分层单体 (FastAPI + MCP) | 单进程暴露 MCP + REST API，MVP 够用 |
| 结构化存储 | SQLite (MVP) → PostgreSQL (生产) | 轻量起步，后期可迁移 |
| 语义检索 | 代理 mem0（mem0 内部用向量库） | 不自建向量数据库，mem0 更新自动受益 |
| AI 抽取 | Claude API | 效果最好，成本可控 |
| Hook 触发 | Shell 脚本 → HTTP API | Claude Code hooks 调用共享服务 |
| 同步策略 | Service 层主动同步 | 审核通过时 service 直接写入 |
| 查询路由 | 内部自动路由 | 结构化→图遍历，模糊→mem0，调用方无感知 |

## 4. 目录结构

```
src/ai_nexus/
├── main.py                    # FastAPI app + MCP http_app
├── config.py                  # pydantic-settings
│
├── models/                    # Pydantic 数据模型
│   ├── entity.py
│   ├── relation.py
│   ├── rule.py
│   └── audit.py
│
├── db/                        # 数据库
│   ├── sqlite.py              # aiosqlite 连接管理
│   └── migrations/            # 编号 SQL 迁移文件
│
├── repos/                     # 单表 CRUD
│   ├── entity_repo.py
│   ├── relation_repo.py
│   ├── rule_repo.py
│   └── audit_repo.py
│
├── services/                  # 业务逻辑层
│   ├── graph_service.py       # 知识图谱（含同步 + 图遍历查询）
│   ├── query_service.py       # 统一查询（内部路由: 结构化→图遍历, 模糊→mem0）
│   ├── extraction_service.py  # Claude API 知识抽取
│   ├── hook_service.py        # pre_plan / pre_commit
│   └── lint_service.py        # 知识 Lint（冲突检测、死规则扫描）
│
├── proxy/                     # mem0/OpenViking 代理层
│   ├── mem0_proxy.py          # get_session_ctx 等代理工具
│   └── openviking_proxy.py    # OpenViking 代理（Phase 3+）
│
├── mcp/                       # MCP Server
│   └── server.py              # async MCP 工具（自有 + 代理）
│
├── api/                       # REST API
│   ├── router.py
│   └── dependencies.py
│
└── hooks/                     # Claude Code Hook 脚本
    ├── pre_plan.py
    └── pre_commit.py
```

### 分层原则

```
models (纯数据) → db (连接) → repos (单表 CRUD) → services (业务逻辑) → api/mcp (入口)
                                            ↗
                                      proxy (mem0/OpenViking 代理)
```

- `repos` 只操作单表，不知道业务语义
- `services` 组合多个 repo，实现业务逻辑（图遍历查询、同步）
- `proxy` 封装 mem0/OpenViking API 调用，暴露为 MCP 代理工具
- `query_service` 统一路由：结构化查询走 repos，模糊查询走 proxy.mem0
- `api` 和 `mcp` 是两个入口壳，都调用 service/proxy 层

## 5. 数据模型

### 5.1 SQLite 表结构（4 张核心表）

- `entities` — 业务实体（name, type, description, domain, attributes, status, source）
- `relations` — 实体关系（source_entity_id, relation_type, target_entity_id, conditions）
- `rules` — 业务规则（name, description, domain, severity, conditions, confidence）
- `knowledge_audit_log` — 审核日志（table_name, record_id, action, old_value, new_value, reviewer）

### 5.2 向量数据

AI Nexus **不直接管理向量数据**。语义检索通过代理调用 mem0 实现：
- mem0 内部使用向量数据库存储 embedding
- AI Nexus 只负责结构化图谱的图遍历查询
- MVP 阶段（几百条规则）纯 SQLite 图遍历够用，不需要语义召回
- 规模增长后通过 mem0 代理获得语义检索能力

## 6. 查询路由

```python
# query_service.py — 内部自动路由
async def query_rules(query: str, domain: str | None = None, limit: int = 10):
    """统一查询入口，自动路由到合适的检索方式。"""
    # 1. 先尝试结构化查询（图遍历）
    results = await graph_service.search_by_keywords(query, domain, limit)
    if results:
        return results

    # 2. 结构化没命中，走 mem0 语义检索（模糊匹配）
    if await mem0_proxy.is_available():
        mem0_results = await mem0_proxy.search(query, limit)
        # 从 mem0 结果中提取 ID，回 SQLite 取完整记录
        ids = [r.id for r in mem0_results]
        return await graph_service.get_by_ids(ids)

    # 3. mem0 不可用，降级为 SQLite LIKE
    return await graph_service.fallback_search(query, domain, limit)
```

调用方（MCP 工具、REST API、Hook）只调 `query_service`，不感知底层路由。

## 7. 核心数据流

### 7.1 知识审核 + 同步

```
提交候选项 → status='pending' → 人工审核
    ├── approve → status='approved' → 正式入库
    └── reject → 标记拒绝
```

MVP 阶段不需要向 mem0 同步（纯图遍历）。后期规模增长时，审核通过可选择性同步到 mem0。

### 7.2 pre_plan Hook

```
Claude Code hook → HTTP POST /api/hooks/pre-plan
    │
    ├── query_service 查相关实体/规则 → 图遍历
    ├── mem0_proxy.get_session_ctx → 会话历史（可选）
    │
    └── 合并注入（业务规则优先级 > 会话历史）
```

### 7.3 数据飞轮（Phase 3+）

```
PR 违规事件（冲突位置 + 触发规则 + 修正方式）
    │
    ▼
自动回写图谱 → 加强规则节点置信度
    │
    └── 或生成新的规则候选项 → 进入审核工作流

llm-wiki 是单向的（你喂它，它长大）
AI Nexus 可以是双向的（规则执行反过来喂养规则库）
```

### 7.4 知识 Lint（Phase 3+）

定期扫描图谱，检测：
- 互相冲突的规则
- 没有任何 PR 曾经触发过的规则节点（死规则 / 未覆盖的风险）
- 最近两周 PR 里违反了但没被系统捕获的案例

输出为周报推给团队负责人。

## 8. MCP 工具设计

### 8.1 AI Nexus 自有工具（5 个核心，async）

| 工具 | 输入 | 描述 |
|------|------|------|
| `search_entities` | query, domain?, limit? | 图遍历搜索业务实体 |
| `search_rules` | query, domain?, severity?, limit? | 图遍历搜索业务规则 |
| `get_business_context` | task_description, keywords? | 获取完整业务上下文（给 pre_plan） |
| `validate_against_rules` | change_description, affected_entities?, diff_summary? | 校验变更是否违反规则（给 pre_commit） |
| `submit_knowledge_candidate` | type, data, source, confidence? | 提交知识候选项 |

### 8.2 mem0 代理工具

| 工具 | 描述 | 优先级 |
|------|------|--------|
| `get_session_ctx` | 代理 mem0，获取项目会话记忆 | 参考（可被覆盖） |

### 8.3 OpenViking 代理工具（Phase 3+）

| 工具 | 描述 |
|------|------|
| `search_documents` | 代理 OpenViking，搜索背景文档 |
| `get_context` | 代理 OpenViking，获取分层上下文 |

## 9. MCP 集成

```python
# main.py
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

mcp = FastMCP("ai-nexus")
mcp_app = mcp.http_app(path="/")

app = FastAPI(
    title="AI Nexus",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
)
app.mount("/mcp", mcp_app)
```

MCP 工具改为 `async def`，可直接 await service/proxy 层。

## 10. 配置管理

```python
class Settings(BaseSettings):
    # 服务
    host: str = "0.0.0.0"
    port: int = 8000

    # SQLite
    sqlite_path: str = "data/ai_nexus.db"

    # mem0 代理
    mem0_api_url: str = "http://localhost:8080"

    # OpenViking 代理（Phase 3+）
    openviking_url: str = "http://localhost:1933"

    # Claude API
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="AI_NEXUS_", env_file=".env")
```

## 11. 迁移机制

```
src/ai_nexus/db/migrations/
├── 001_init_schema.sql
├── 002_xxx.sql
└── ...
```

- 启动时检查 `schema_version` 表，执行未执行的编号 SQL 文件
- 每个 SQL 文件在一个事务内执行，成功后记录版本号

## 12. REST API

```
# 知识图谱 CRUD
GET/POST       /api/entities
GET/PUT/DELETE /api/entities/{id}
GET/POST       /api/relations
DELETE         /api/relations/{id}
GET/POST       /api/rules
GET/PUT/DELETE /api/rules/{id}

# 知识审核
GET  /api/audit/pending
POST /api/audit/{id}/approve
POST /api/audit/{id}/reject

# 开发 Hook
POST /api/hooks/pre-plan
POST /api/hooks/pre-commit

# 统一查询
POST /api/search

# 运维
POST /api/search/reindex
```

## 13. 依赖

| 操作 | 包 |
|------|-----|
| 保留 | `fastapi`, `uvicorn`, `mcp`, `aiosqlite`, `pydantic`, `httpx`, `anthropic`, `pydantic-settings` |
| 移除 | `qdrant-client`, `fastembed`, `mem0ai`（AI Nexus 不直接依赖 mem0 SDK，通过 httpx 调 API） |
| 新增 | 无（语义检索通过 httpx 代理调 mem0 REST API） |

## 14. 测试策略

| 层 | 测试方式 |
|----|---------|
| `models` | 单元测试，验证序列化/校验 |
| `repos` | 集成测试，真实 SQLite (:memory:) |
| `proxy` | 单元测试 mock mem0 API |
| `services` | 单元测试 mock repo + proxy，验证路由和降级逻辑 |
| `api` | FastAPI TestClient |
| `mcp` | MCP client 测试 |

## 15. 运维

### mem0 部署（语义检索后端）
```bash
docker compose up -d mem0  # mem0 内部自带向量数据库
```

### 健康检查
- `GET /health` — FastAPI 服务
- `mem0_proxy.is_available()` — mem0 可用性

## 16. MVP 路线图

### Phase 0（当前）: 基础设施
- [x] 项目脚手架 + 目录结构
- [x] MCP Server 5 个占位工具
- [x] SQLite schema
- [x] Pydantic 数据模型
- [x] 配置管理 (pydantic-settings)
- [x] SQLite 连接管理 (aiosqlite)
- [x] 基础测试框架 (29 tests)
- [ ] **MCP 集成修正** (http_app + async tools + combine_lifespans)
- [ ] **移除 Qdrant/mem0 依赖**，改用 httpx 代理层
- [ ] **迁移机制** (编号 SQL + schema_version)
- [ ] **main.py 修正**

### Phase 1（4 周）: 业务知识图谱
- [ ] Entity/Relation/Rule CRUD repos
- [ ] Graph service（图遍历查询）
- [ ] Query service（内部路由 + 降级）
- [ ] MCP 工具对接真实数据
- [ ] mem0 代理层 (get_session_ctx)
- [ ] REST API CRUD endpoints
- [ ] 知识审核工作流

### Phase 2（3 周）: 开发流程 Hook
- [ ] pre_plan hook 实现
- [ ] pre_commit hook 实现
- [ ] Claude Code hooks 配置

### Phase 3（3 周）: 知识审核 + 增强
- [ ] Claude API 知识抽取引擎
- [ ] 编译管道（飞书文档 → 结构化 → 图谱节点）
- [ ] 知识 Lint（冲突检测、死规则扫描）
- [ ] 数据飞轮（PR 违规事件回写图谱）
- [ ] OpenViking 代理工具
- [ ] 端到端测试

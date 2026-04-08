# AI Nexus 架构设计文档

> 日期: 2026-04-08
> 状态: Approved (v2 — Phase 0 评审后修订)
> 阶段: Phase 0 → Phase 1

## 修订记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-04-08 | v1 | 初始设计 |
| 2026-04-08 | v2 | Phase 0 评审后修订: mem0→Qdrant, MCP 集成修正, 补充 embedding/同步/迁移/降级策略 |

## 1. 项目定位

AI Nexus 是**业务知识治理层**，让 AI 像资深员工一样懂业务规则。

核心三件事：
1. **业务知识图谱** — 实体 + 关系 + 规则的结构化 CRUD
2. **开发流程 Hook** — pre_plan 注入业务上下文 + pre_commit 校验业务规则
3. **知识审核工作流** — AI 抽取知识候选项 + 人工审核入库

### 不做什么
- 不自建向量数据库层（用 Qdrant/OpenViking）
- 不做通用 Agent 记忆管理
- 不做文档库（飞书/Confluence 已经做了）

## 2. 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 部署模式 | 团队共享 HTTP 服务 | 团队共享知识库，多消费方接入 |
| 架构模式 | 分层单体 (FastAPI + MCP) | 单进程暴露 MCP + REST API，MVP 阶段够用 |
| 向量搜索 | Qdrant (默认) + OpenViking (可选) | Qdrant 支持丰富元数据过滤，生产级可靠；OpenViking 留给未来 Agent 上下文场景 |
| Embedding | fastembed 本地模型 | 零外部依赖，无需 API key，MVP 阶段够用 |
| AI 抽取 | Claude API | 效果最好，API 成本可控 |
| Hook 触发 | Shell 脚本 → HTTP API | Claude Code hooks 调用共享服务 |
| 结构化存储 | SQLite (aiosqlite) | 轻量，单文件，适合知识图谱规模 |
| 同步策略 | Service 层主动同步 | 审核通过时 service 直接调用 search_provider.add()，简单直接 |
| 降级策略 | 向量不可用 → SQLite LIKE | 保证核心功能在向量服务宕机时仍可用 |

### v2 决策变更说明

| 变更 | v1 | v2 | 原因 |
|------|----|----|------|
| 向量搜索后端 | mem0 默认 | **Qdrant** 默认 | mem0 是会话记忆系统，不支持结构化元数据过滤 |
| MCP SSE 挂载 | `mcp.sse_app()` | **`mcp.http_app()`** + `combine_lifespans` | FastMCP 2.3.1+ API 变更 |
| MCP 工具 | 同步函数 | **async def** | service 层是 async，需直接 await |
| Embedding | 未定义 | **fastembed 本地模型** | 补充设计缺口 |
| 同步触发 | 未定义 | **Service 层主动同步** | 补充设计缺口 |
| 迁移机制 | 一句话 | **编号 SQL + schema_version 表** | 补充设计缺口 |
| 错误处理 | 无 | **降级为 SQLite LIKE** | 补充设计缺口 |

## 3. 目录结构

```
src/ai_nexus/
├── main.py                    # FastAPI app 入口 + MCP http_app 挂载
├── config.py                  # 配置管理（pydantic-settings）
│
├── models/                    # Pydantic 数据模型
│   ├── entity.py              # Entity, EntityCreate, EntityUpdate
│   ├── relation.py            # Relation, RelationCreate
│   ├── rule.py                # Rule, RuleCreate, RuleUpdate
│   └── audit.py               # AuditLog, KnowledgeCandidate, HookRequest
│
├── db/                        # 数据库连接管理
│   ├── sqlite.py              # SQLite 连接管理 (aiosqlite)
│   └── migrations/            # 编号 SQL 迁移文件
│       └── 001_init_schema.sql
│
├── repos/                     # 单表 CRUD（纯数据访问）
│   ├── entity_repo.py         # entities 表操作
│   ├── relation_repo.py       # relations 表操作
│   ├── rule_repo.py           # rules 表操作
│   └── audit_repo.py          # knowledge_audit_log 表操作
│
├── search/                    # 语义搜索（抽象 + 实现）
│   ├── provider.py            # SearchProvider 抽象接口
│   ├── qdrant_provider.py     # Qdrant + fastembed 实现（默认）
│   └── openviking_provider.py # OpenViking 实现（可选, Phase 3+）
│
├── services/                  # 业务逻辑层（组合 repo + search）
│   ├── graph_service.py       # 知识图谱业务逻辑（含同步）
│   ├── search_service.py      # 语义 + 结构化搜索（含降级）
│   ├── extraction_service.py  # Claude API 知识抽取
│   └── hook_service.py        # pre_plan / pre_commit 逻辑
│
├── mcp/                       # MCP Server 入口
│   └── server.py              # async MCP 工具定义（调用 service 层）
│
├── api/                       # REST API 入口
│   ├── router.py              # FastAPI router
│   └── dependencies.py        # 依赖注入（db sessions, search provider）
│
└── hooks/                     # Claude Code Hook 脚本
    ├── pre_plan.py            # 开发规划前注入业务上下文
    └── pre_commit.py          # 提交前校验业务规则
```

### 分层原则

```
models (纯数据) → db (连接) → repos (单表 CRUD) → services (业务逻辑) → api/mcp (入口)
                                            ↗
                                      search (语义搜索)
```

- `models` 无外部依赖，纯 Pydantic 定义
- `repos` 只操作单表，不知道业务语义
- `services` 组合多个 repo + search provider，实现业务逻辑
- `services` 负责同步: 审核通过时主动调用 search_provider.add()
- `api` 和 `mcp` 是两个入口壳，都调用 service 层，不直接操作 repo
- `search` 独立模块，通过抽象接口解耦

## 4. 数据模型

### 4.1 SQLite 表结构（4 张核心表）

- `entities` — 业务实体（name, type, description, domain, attributes, status, source）
- `relations` — 实体关系（source_entity_id, relation_type, target_entity_id, conditions）
- `rules` — 业务规则（name, description, domain, severity, conditions, confidence）
- `knowledge_audit_log` — 审核日志（table_name, record_id, action, old_value, new_value, reviewer）

### 4.2 Qdrant 向量数据

**Collection 策略**: 两个独立 collection

| Collection | 内容 | Payload 字段 |
|------------|------|-------------|
| `entities` | 实体描述 embedding | name, type, domain, status |
| `rules` | 规则描述 embedding | name, domain, severity, status |

**为什么分两个 collection**: 元数据 schema 不同，过滤条件不同，分开更清晰。

**Embedding 模型**: fastembed 默认 `all-MiniLM-L6-v2` (384维)，可配置切换为 `BAAI/bge-small-zh-v1.5` (512维，中文优化)。

**同步策略**:
- 实体/规则 `status` 变为 `approved` 时，service 层主动调用 `search_provider.add()`
- 更新时调用 `search_provider.add()` 覆盖旧向量
- 删除时调用 `search_provider.delete()`
- 启动时通过 `ensure_ready()` 确保 collection 存在
- 提供 `sync_all()` 用于全量重建索引

## 5. 核心数据流

### 5.1 语义搜索

```
查询 "支付超时规则"
    │
    ▼
search_service.search(query, domain, limit)
    │
    ├── search_provider.health()           → 检查 Qdrant 可用
    │   ├── 可用 → search_provider.search(query, filter={domain, status})
    │   │          → Qdrant 语义搜索 → top-K 候选 ID
    │   └── 不可用 → SQLite LIKE 降级搜索
    │
    ├── entity_repo.get_by_ids(ids)       → SQLite 取完整实体
    ├── rule_repo.get_by_ids(ids)         → SQLite 取完整规则
    └── 合并排序返回
```

### 5.2 知识审核 + 向量同步

```
AI 抽取 / 手动提交 → submit_knowledge_candidate()
    │
    ├── 写入 entities/rules 表 (status='pending')
    ├── 写入 audit_log
    │
    ▼ 人工审核
    │
    ├── POST /api/audit/{id}/approve
    │     → service 更新 status='approved'
    │     → service 调用 search_provider.add() 同步向量
    │     → 写入 audit_log
    │
    └── POST /api/audit/{id}/reject
          → 标记拒绝 + 记录原因
          → 不触发向量同步
```

### 5.3 pre_plan Hook

```
Claude Code hook 触发（开发者开始规划任务）
    │
    ▼
pre_plan.py → HTTP POST /api/hooks/pre-plan
    │   body: { "task_description": "添加微信支付退款功能" }
    ▼
hook_service.pre_plan(task_description)
    │
    ├── search_service.search_context(task_description)
    │     → 返回相关 entities + rules + relations
    │
    └── 格式化注入文本 → 返回给 Claude Code
```

### 5.4 pre_commit Hook

```
Claude Code hook 触发（提交前）
    │
    ▼
pre_commit.py → HTTP POST /api/hooks/pre-commit
    │   body: { "diff": "...", "affected_files": [...] }
    ▼
hook_service.pre_commit(diff, affected_files)
    │
    ├── extraction_service.analyze_diff(diff)  → 提取 affected_entities
    ├── rule_repo.get_related(affected_entities) → 查询相关规则
    ├── Claude API 校验变更是否违反规则
    │
    └── 返回 { "status": "pass" | "block", "violations": [...] }
```

## 6. API 设计

### 6.1 MCP 工具（5 个核心，async）

| 工具 | 输入 | 输出 | 描述 |
|------|------|------|------|
| `search_entities` | query, domain?, limit? | Entity[] | 语义搜索业务实体 |
| `search_rules` | query, domain?, severity?, limit? | Rule[] | 语义搜索业务规则 |
| `get_business_context` | task_description, keywords? | {entities, rules, relations} | 获取完整业务上下文 |
| `validate_against_rules` | change_description, affected_entities?, diff_summary? | {violations} | 校验变更是否违反规则 |
| `submit_knowledge_candidate` | type, data, source, confidence? | {id, status} | 提交知识候选项 |

> **MCP 工具返回类型**: FastMCP 工具返回 JSON 字符串 (`str`)。表中的 Entity[] 等表示 JSON 内的数据结构，实际返回是 `json.dumps(...)` 序列化后的字符串。

### 6.2 REST API

```
# 知识图谱 CRUD
GET    /api/entities              # 列表（支持过滤）
POST   /api/entities              # 创建
GET    /api/entities/{id}         # 详情
PUT    /api/entities/{id}         # 更新
DELETE /api/entities/{id}         # 删除

GET    /api/relations             # 列表
POST   /api/relations             # 创建
DELETE /api/relations/{id}        # 删除

GET    /api/rules                 # 列表（支持过滤）
POST   /api/rules                 # 创建
GET    /api/rules/{id}            # 详情
PUT    /api/rules/{id}            # 更新
DELETE /api/rules/{id}            # 删除

# 知识审核
GET    /api/audit/pending         # 待审核列表
POST   /api/audit/{id}/approve    # 通过（触发向量同步）
POST   /api/audit/{id}/reject     # 拒绝

# 开发 Hook
POST   /api/hooks/pre-plan        # pre_plan 触发
POST   /api/hooks/pre-commit      # pre_commit 触发

# 搜索
POST   /api/search                # 统一搜索入口

# 运维
POST   /api/search/reindex        # 全量重建向量索引
```

## 7. SearchProvider 抽象接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    id: str           # 对应 SQLite 记录的 ID
    score: float      # 相关度分数
    content: str      # 匹配的文本片段
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchProvider(ABC):
    """语义搜索抽象接口，支持 Qdrant / OpenViking 等后端。"""

    @abstractmethod
    async def add(self, id: str, content: str, metadata: dict[str, Any]) -> None:
        """添加或更新一条向量记录。"""

    @abstractmethod
    async def search(
        self, query: str, limit: int = 10, filter: dict[str, Any] | None = None
    ) -> list[SearchResult]:
        """语义搜索，返回相关结果。"""

    @abstractmethod
    async def delete(self, id: str) -> None:
        """删除一条向量记录。"""

    @abstractmethod
    async def health(self) -> bool:
        """检查后端是否可用。"""

    @abstractmethod
    async def sync_all(self, items: list[tuple[str, str, dict[str, Any]]]) -> None:
        """批量同步/重建索引。items: [(id, content, metadata), ...]"""

    @abstractmethod
    async def ensure_ready(self) -> None:
        """确保后端就绪（创建 collection 等）。启动时调用。"""
```

## 8. 配置管理

```python
# config.py — 使用 pydantic-settings
class Settings(BaseSettings):
    # 服务
    host: str = "0.0.0.0"
    port: int = 8000

    # SQLite
    sqlite_path: str = "data/ai_nexus.db"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_entities_collection: str = "entities"
    qdrant_rules_collection: str = "rules"

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"  # 或 "BAAI/bge-small-zh-v1.5"

    # OpenViking (可选)
    openviking_url: str = "http://localhost:1933"

    # Claude API
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="AI_NEXUS_", env_file=".env")
```

## 9. MCP 集成方案

```python
# main.py — FastAPI + MCP http_app
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from ai_nexus.config import Settings
from ai_nexus.db.sqlite import Database

settings = Settings()
mcp = FastMCP("ai-nexus")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """管理应用生命周期: 启动时初始化数据库和搜索后端。"""
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.init_schema()
    app.state.db = db
    yield
    await db.disconnect()


# 创建 MCP ASGI app
mcp_app = mcp.http_app(path="/")

# 合并 lifespans
app = FastAPI(
    title="AI Nexus",
    description="AI Business Knowledge OS",
    version="0.1.0",
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
)

# 挂载 MCP 端点
app.mount("/mcp", mcp_app)
```

### MCP 工具定义 (async)

```python
# mcp/server.py
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("ai-nexus")


@mcp.tool
async def search_entities(
    query: str, domain: str | None = None, limit: int = 10
) -> str:
    """语义搜索业务实体。"""
    # 从 app.state 获取 service，或通过依赖注入
    ...
```

## 10. 迁移机制

```
src/ai_nexus/db/migrations/
├── 001_init_schema.sql          # 初始 4 张表 + 索引
├── 002_xxx.sql                  # 未来变更
└── ...
```

**执行逻辑**:
1. 启动时检查 `schema_version` 表是否存在，不存在则创建
2. 查询已执行的版本号列表
3. 按编号顺序执行未执行的 `.sql` 文件
4. 每个 SQL 文件在一个事务内执行
5. 成功后记录版本号到 `schema_version` 表

```python
# db/migrations 执行逻辑 (伪代码)
async def run_migrations(db: Database):
    executed = await db.fetchall("SELECT version FROM schema_version")
    executed_versions = {row[0] for row in executed}
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = sql_file.stem.split("_")[0]
        if version not in executed_versions:
            sql = sql_file.read_text()
            await db.execute(sql)  # 事务内
            await db.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
```

## 11. 错误处理与降级

### 向量搜索降级

```python
# search_service.py
async def search(self, query: str, domain: str | None = None, limit: int = 10):
    if await self.search_provider.health():
        return await self.search_provider.search(query, limit, filter=build_filter(domain))
    # 降级: SQLite LIKE 查询
    return await self._fallback_search(query, domain, limit)

async def _fallback_search(self, query: str, domain: str | None, limit: int):
    """向量不可用时的降级搜索。"""
    pattern = f"%{query}%"
    sql = "SELECT * FROM entities WHERE description LIKE ? AND status = 'approved'"
    params: list = [pattern]
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    sql += " LIMIT ?"
    params.append(limit)
    rows = await self.db.fetchall(sql, tuple(params))
    return [entity_from_row(row) for row in rows]
```

### Hook 错误处理

- Hook 调用服务失败时，返回降级响应（空上下文/放行），不阻塞开发流程
- 记录失败日志用于排查

### 事务边界 & Repo 错误处理

- `repos` 层不管理事务，只执行单条 SQL
- `services` 层负责跨 repo 操作的一致性，需要时在 service 层管理事务
- `repos` 层抛异常（不返回 Result 类型），service 层捕获并处理
- 列表操作统一支持分页: `offset: int = 0, limit: int = 50`

### 认证

MVP 阶段不做认证。团队内网部署，信任所有调用方。
生产化时考虑 API key 或 OAuth。

## 12. 依赖

### 核心依赖
- `fastapi>=0.115.0` — HTTP 服务
- `uvicorn>=0.34.0` — ASGI 服务器
- `mcp>=1.0.0` — MCP Server (FastMCP)
- `aiosqlite>=0.20.0` — SQLite 异步操作
- `pydantic>=2.10.0` — 数据模型
- `pydantic-settings>=2.7.0` — 配置管理
- `httpx>=0.28.0` — HTTP 客户端
- `anthropic` — Claude API（extraction_service）
- `qdrant-client[fastembed]>=1.12.0` — Qdrant 向量数据库 + fastembed 本地 embedding

### 开发依赖
- `pytest>=8.0` + `pytest-asyncio>=0.24` — 测试
- `ruff>=0.8.0` — 代码检查
- `mypy>=1.13` — 类型检查

## 13. 测试策略

| 层 | 测试方式 |
|----|---------|
| `models` | 单元测试，验证序列化/校验 |
| `repos` | 集成测试，用真实 SQLite (:memory:) |
| `search` | 单元测试 mock SearchProvider；集成测试用真实 Qdrant (CI) |
| `services` | 单元测试 mock repo + search，验证同步和降级逻辑 |
| `api` | FastAPI TestClient，端到端 |
| `mcp` | MCP client 测试工具调用 |

关键原则：
- repos 层用真实 SQLite 内存数据库测试，不 mock
- services 层 mock repos 和 search，专注业务逻辑
- search_service 降级逻辑需要专门测试
- API 层用 TestClient 做集成测试
- MCP 工具用 FastMCP Client 测试 (或通过 TestClient 调用)
- 降级测试: mock search_provider.health() 返回 False，验证降级行为

## 15. 运维

### Qdrant 部署

```bash
# 开发环境: docker-compose
docker compose up -d qdrant

# Qdrant 默认端口
# - REST API: 6333
# - gRPC: 6334
```

### 健康检查

- `GET /health` — FastAPI 服务健康检查
- `search_provider.health()` — Qdrant 可用性检查 (内部调用)
- Docker 健康检查已在 docker-compose.yml 中配置

## 14. MVP 路线图

### Phase 0（当前）: 基础设施
- [x] 项目脚手架 + 目录结构
- [x] MCP Server 5 个占位工具
- [x] SQLite schema
- [x] Pydantic 数据模型
- [x] 配置管理 (pydantic-settings)
- [x] SQLite 连接管理 (aiosqlite)
- [x] SearchProvider 抽象接口
- [x] 基础测试框架 (29 tests)
- [ ] **MCP 集成修正** (http_app + async tools + combine_lifespans)
- [ ] **QdrantProvider 实现** (qdrant + fastembed)
- [ ] **迁移机制** (编号 SQL + schema_version)
- [ ] **main.py 修正**
- [ ] **依赖更新** (mem0ai → qdrant-client[fastembed])

### Phase 1（4 周）: 业务知识图谱
- [ ] Entity/Relation/Rule CRUD repos
- [ ] Graph service 业务逻辑（含同步）
- [ ] MCP 工具对接真实数据
- [ ] 语义搜索集成（含降级）
- [ ] REST API CRUD endpoints
- [ ] 知识审核工作流

### Phase 2（3 周）: 开发流程 Hook
- [ ] pre_plan hook 实现
- [ ] pre_commit hook 实现
- [ ] Claude Code hooks 配置
- [ ] Hook 脚本 (shell wrapper)

### Phase 3（3 周）: 知识审核工作流
- [ ] Claude API 知识抽取引擎
- [ ] 审核工作流 API
- [ ] 审核通过后向量同步
- [ ] OpenViking provider (可选)
- [ ] 端到端测试

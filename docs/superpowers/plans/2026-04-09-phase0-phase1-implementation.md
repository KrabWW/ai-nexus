# AI Nexus Phase 0 Fix + Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Phase 0 基础设施问题，并实现 Phase 1 业务知识图谱（Repo → Service → MCP/REST API 层）。

**Architecture:** 分层单体 FastAPI + MCP Server，SQLite 图遍历为主，mem0 httpx 代理为辅，查询路由在 QueryService 内部自动完成。

**Tech Stack:** Python 3.11+, FastAPI, mcp (FastMCP), aiosqlite, httpx, pydantic-settings, pytest + pytest-asyncio

---

## Pre-flight Checks

在开始前确认：

```bash
cd /Users/xielaoban/Documents/GitHub/ai-nexus
python -m pytest tests/ -q          # 了解当前通过/失败情况
ruff check src/                      # 了解当前 lint 状态
```

---

## Chunk 1: Phase 0 修复

### Task 1: 依赖清理 + 删除 search/ 目录

**目标：** 移除 mem0ai 依赖，删除遗留的 search/ 目录，修正 db/__init__.py 注释，清理 config.py

**Files:**
- Modify: `pyproject.toml`
- Delete: `src/ai_nexus/search/` (整目录)
- Modify: `src/ai_nexus/db/__init__.py`
- Modify: `src/ai_nexus/config.py`

- [ ] **Step 1: 写失败测试 — 验证 mem0ai 不在依赖里**

```python
# tests/test_phase0.py
import subprocess
import sys


def test_mem0ai_not_installed():
    """mem0ai 不应该是项目依赖。"""
    result = subprocess.run(
        [sys.executable, "-c", "import mem0"],
        capture_output=True,
    )
    assert result.returncode != 0, "mem0ai should not be importable as a project dep"


def test_search_module_removed():
    """search/ 模块不应该存在。"""
    result = subprocess.run(
        [sys.executable, "-c", "from ai_nexus.search import provider"],
        capture_output=True,
    )
    assert result.returncode != 0, "ai_nexus.search should be removed"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest tests/test_phase0.py -v
# Expected: FAIL (mem0ai still importable, search/ still exists)
```

- [ ] **Step 3: 从 pyproject.toml 移除 mem0ai**

在 `pyproject.toml` 的 `dependencies` 列表中删除 `"mem0ai>=0.1.0"` 这一行。

- [ ] **Step 4: 删除 search/ 目录**

```bash
rm -rf src/ai_nexus/search/
```

- [ ] **Step 5: 修正 db/__init__.py 注释**

将 `src/ai_nexus/db/__init__.py` 改为：

```python
"""数据库层：SQLite 访问。"""

from ai_nexus.db.sqlite import Database

__all__ = ["Database"]
```

- [ ] **Step 6: 清理 config.py — 移除 search_provider 字段**

从 `src/ai_nexus/config.py` 的 `Settings` 类中删除 `search_provider` 字段（保留 `mem0_api_url` 和 `openviking_url`）。同时更新 docstring 中对应的 Attributes 说明。

- [ ] **Step 7: 运行测试，确认通过**

```bash
pytest tests/test_phase0.py -v
# Expected: PASS
```

- [ ] **Step 8: 运行全量测试，确认没有回归**

```bash
pytest tests/ -v
ruff check src/
```

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/ai_nexus/db/__init__.py src/ai_nexus/config.py tests/test_phase0.py
git rm -r src/ai_nexus/search/
git commit -m "fix(phase0): remove mem0ai dep, delete search/ module, clean config"
```

---

### Task 2: 迁移机制 — 编号 SQL + schema_version 表

**目标：** 将硬编码的 SCHEMA 提取为编号 SQL 迁移文件，sqlite.py 启动时自动执行未执行的迁移。

**Files:**
- Create: `src/ai_nexus/db/migrations/001_init_schema.sql`
- Modify: `src/ai_nexus/db/sqlite.py`
- Create: `tests/test_migrations.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_migrations.py
import pytest
from ai_nexus.db.sqlite import Database


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.disconnect()


async def test_schema_version_table_exists(db: Database):
    """启动后 schema_version 表必须存在。"""
    await db.run_migrations()
    rows = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    assert len(rows) == 1


async def test_migration_001_applied(db: Database):
    """migration 001 执行后版本号为 1。"""
    await db.run_migrations()
    row = await db.fetchone("SELECT MAX(version) FROM schema_version")
    assert row is not None
    assert row[0] == 1


async def test_run_migrations_idempotent(db: Database):
    """多次运行迁移不会重复执行。"""
    await db.run_migrations()
    await db.run_migrations()
    rows = await db.fetchall("SELECT version FROM schema_version WHERE version = 1")
    assert len(rows) == 1


async def test_core_tables_exist_after_migration(db: Database):
    """迁移后 4 张核心表都存在。"""
    await db.run_migrations()
    tables = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = {row[0] for row in tables}
    assert {"entities", "relations", "rules", "knowledge_audit_log"} <= table_names
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_migrations.py -v
# Expected: FAIL — run_migrations method does not exist
```

- [ ] **Step 3: 创建 001_init_schema.sql**

```sql
-- src/ai_nexus/db/migrations/001_init_schema.sql
-- 4 张核心表 + 索引

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    attributes TEXT,
    domain TEXT NOT NULL,
    status TEXT DEFAULT 'approved',
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    target_entity_id INTEGER NOT NULL,
    description TEXT,
    conditions TEXT,
    weight REAL DEFAULT 1.0,
    status TEXT DEFAULT 'approved',
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_entity_id) REFERENCES entities(id),
    FOREIGN KEY (target_entity_id) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    domain TEXT NOT NULL,
    severity TEXT DEFAULT 'warning',
    conditions TEXT,
    related_entity_ids TEXT,
    status TEXT DEFAULT 'pending',
    source TEXT DEFAULT 'ai_extracted',
    confidence REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reviewer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_domain ON entities(domain);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_rules_domain ON rules(domain);
CREATE INDEX IF NOT EXISTS idx_rules_status ON rules(status);
```

- [ ] **Step 4: 在 sqlite.py 中添加 run_migrations 方法**

在 `Database` 类中添加（删除原有的硬编码 `SCHEMA` 常量和 `init_schema` 方法，改为 `run_migrations`）：

```python
# 删除文件顶部的 SCHEMA = """...""" 常量
# 删除 init_schema 方法
# 添加以下内容：

import re
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

async def run_migrations(self) -> None:
    """执行所有未应用的编号 SQL 迁移文件。

    - 自动创建 schema_version 表（如不存在）
    - 按文件名数字顺序执行未执行的迁移
    - 每个迁移在事务内执行，成功后记录版本号
    """
    if not self._conn:
        raise RuntimeError("Database not connected. Call connect() first.")

    # 创建 schema_version 表
    await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await self._conn.commit()

    # 查询已应用版本
    cursor = await self._conn.execute("SELECT version FROM schema_version")
    applied = {row[0] for row in await cursor.fetchall()}

    # 找到所有编号迁移文件并排序
    migration_files = sorted(
        _MIGRATIONS_DIR.glob("*.sql"),
        key=lambda p: int(re.match(r"^(\d+)", p.stem).group(1)),
    )

    for mf in migration_files:
        version = int(re.match(r"^(\d+)", mf.stem).group(1))
        if version in applied:
            continue
        sql = mf.read_text(encoding="utf-8")
        await self._conn.executescript(sql)
        await self._conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (version,)
        )
        await self._conn.commit()
```

注意：原 `init_schema` 仍然保留但改为调用 `run_migrations`，避免破坏现有测试：

```python
async def init_schema(self) -> None:
    """向后兼容：调用 run_migrations。"""
    await self.run_migrations()
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/test_migrations.py tests/test_sqlite.py -v
# Expected: ALL PASS
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_nexus/db/migrations/001_init_schema.sql src/ai_nexus/db/sqlite.py tests/test_migrations.py
git commit -m "feat(db): add numbered SQL migration runner with schema_version tracking"
```

---

### Task 3: main.py 修正 — streamable_http_app + combine_lifespans

**目标：** 将 `sse_app()` 替换为 `streamable_http_app()`，正确组合 DB lifespan 和 MCP lifespan。

**Files:**
- Modify: `src/ai_nexus/main.py`
- Create: `tests/test_app.py`

**背景：** mcp 1.27.0 中 `sse_app()` 依然可用但不是推荐的 HTTP transport；`streamable_http_app()` 是 MCP Streamable HTTP 规范的实现。`combine_lifespans` 来自 `mcp.server.fastmcp`（FastMCP 实例上有 `lifespan` property）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_app.py
from fastapi.testclient import TestClient
from ai_nexus.main import app


def test_health_check():
    """健康检查端点返回 ok。"""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_mcp_endpoint_exists():
    """MCP 挂载点 /mcp 可访问（不要求完整握手）。"""
    with TestClient(app) as client:
        resp = client.get("/mcp/")
        # 405/404/200 都可以，只要不是 500
        assert resp.status_code != 500
```

- [ ] **Step 2: 运行，记录当前状态**

```bash
pytest tests/test_app.py -v
```

- [ ] **Step 3: 修改 main.py**

将 `src/ai_nexus/main.py` 改为：

```python
"""AI Nexus FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_nexus.config import Settings
from ai_nexus.db.sqlite import Database
from ai_nexus.mcp.server import mcp

settings = Settings()


@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """初始化 SQLite 连接，运行迁移，关闭时断开连接。"""
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.run_migrations()
    app.state.db = db
    yield
    await db.disconnect()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    # MCP Streamable HTTP transport app
    mcp_http_app = mcp.streamable_http_app()

    # 组合两个 lifespan（DB + MCP）
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with db_lifespan(app):
            async with mcp_http_app.router.lifespan_context(app):
                yield

    app = FastAPI(
        title="AI Nexus",
        description="AI Business Knowledge OS",
        version="0.1.0",
        lifespan=combined_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/mcp", mcp_http_app)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

> **注意：** 如果 `mcp_http_app.router.lifespan_context` 不存在（取决于 mcp 版本），退回到只用 db_lifespan：`lifespan=db_lifespan`，并单独 `app.mount("/mcp", mcp.streamable_http_app())`。以实际 import 不报错为准。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_app.py -v
# Expected: PASS
```

- [ ] **Step 5: 全量测试**

```bash
pytest tests/ -v
ruff check src/
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_nexus/main.py tests/test_app.py
git commit -m "fix(main): switch to streamable_http_app, combine DB + MCP lifespans"
```

---

### Task 4: MCP 工具改 async

**目标：** 5 个 MCP 工具从 `def` 改为 `async def`，为后续 await service 层做准备。

**Files:**
- Modify: `src/ai_nexus/mcp/server.py`

- [ ] **Step 1: 写测试 — 验证工具是协程函数**

在 `tests/test_phase0.py` 中追加：

```python
import asyncio
import inspect
from ai_nexus.mcp.server import (
    search_entities,
    search_rules,
    get_business_context,
    validate_against_rules,
    submit_knowledge_candidate,
)


def test_mcp_tools_are_async():
    """所有 MCP 工具必须是 async def。"""
    tools = [
        search_entities,
        search_rules,
        get_business_context,
        validate_against_rules,
        submit_knowledge_candidate,
    ]
    for tool in tools:
        assert asyncio.iscoroutinefunction(tool), f"{tool.__name__} must be async"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_phase0.py::test_mcp_tools_are_async -v
# Expected: FAIL
```

- [ ] **Step 3: 将 5 个工具改为 async def**

在 `src/ai_nexus/mcp/server.py` 中，将所有 `def search_entities(...)` 等改为 `async def search_entities(...)`（保持函数体不变）。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_phase0.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/mcp/server.py tests/test_phase0.py
git commit -m "fix(mcp): convert all MCP tools to async def"
```

---

## Chunk 2: Repo 层

> Repo 层只操作单表，不知道业务语义。所有测试使用 `:memory:` SQLite。

### Task 5: EntityRepo

**Files:**
- Create: `src/ai_nexus/repos/__init__.py`
- Create: `src/ai_nexus/repos/entity_repo.py`
- Create: `tests/test_entity_repo.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_entity_repo.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate, EntityUpdate
from ai_nexus.repos.entity_repo import EntityRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield EntityRepo(db)
    await db.disconnect()


async def test_create_and_get(repo: EntityRepo):
    entity = await repo.create(EntityCreate(
        name="订单", type="concept", domain="交易"
    ))
    assert entity.id is not None
    assert entity.name == "订单"

    fetched = await repo.get(entity.id)
    assert fetched is not None
    assert fetched.name == "订单"


async def test_get_nonexistent_returns_none(repo: EntityRepo):
    assert await repo.get(99999) is None


async def test_update(repo: EntityRepo):
    entity = await repo.create(EntityCreate(name="用户", type="actor", domain="账户"))
    updated = await repo.update(entity.id, EntityUpdate(description="系统用户"))
    assert updated is not None
    assert updated.description == "系统用户"


async def test_delete(repo: EntityRepo):
    entity = await repo.create(EntityCreate(name="商品", type="object", domain="库存"))
    deleted = await repo.delete(entity.id)
    assert deleted is True
    assert await repo.get(entity.id) is None


async def test_list_by_domain(repo: EntityRepo):
    await repo.create(EntityCreate(name="A", type="t", domain="财务"))
    await repo.create(EntityCreate(name="B", type="t", domain="财务"))
    await repo.create(EntityCreate(name="C", type="t", domain="其他"))
    results = await repo.list(domain="财务")
    assert len(results) == 2


async def test_search_by_keyword(repo: EntityRepo):
    await repo.create(EntityCreate(name="支付订单", type="concept", domain="支付"))
    await repo.create(EntityCreate(name="退款单", type="concept", domain="支付"))
    await repo.create(EntityCreate(name="用户账户", type="actor", domain="账户"))
    results = await repo.search(keyword="订单")
    assert len(results) == 1
    assert results[0].name == "支付订单"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_entity_repo.py -v
# Expected: FAIL — module not found
```

- [ ] **Step 3: 实现 EntityRepo**

```python
# src/ai_nexus/repos/__init__.py
"""Repo 层：单表 CRUD。"""
```

```python
# src/ai_nexus/repos/entity_repo.py
"""EntityRepo — entities 表单表 CRUD。"""

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import Entity, EntityCreate, EntityUpdate


def _row_to_entity(row: tuple[Any, ...]) -> Entity:
    return Entity(
        id=row[0],
        name=row[1],
        type=row[2],
        description=row[3],
        attributes=json.loads(row[4]) if row[4] else None,
        domain=row[5],
        status=row[6],
        source=row[7],
        created_at=row[8],
        updated_at=row[9],
    )


class EntityRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: EntityCreate) -> Entity:
        cursor = await self._db.execute(
            """INSERT INTO entities (name, type, description, attributes, domain, status, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.name,
                data.type,
                data.description,
                json.dumps(data.attributes) if data.attributes else None,
                data.domain,
                data.status,
                data.source,
            ),
        )
        return await self.get(cursor.lastrowid)  # type: ignore[arg-type]

    async def get(self, entity_id: int) -> Entity | None:
        row = await self._db.fetchone(
            "SELECT id, name, type, description, attributes, domain, status, source, "
            "created_at, updated_at FROM entities WHERE id = ?",
            (entity_id,),
        )
        return _row_to_entity(row) if row else None

    async def update(self, entity_id: int, data: EntityUpdate) -> Entity | None:
        fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if not fields:
            return await self.get(entity_id)
        if "attributes" in fields and fields["attributes"] is not None:
            fields["attributes"] = json.dumps(fields["attributes"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [entity_id]
        await self._db.execute(
            f"UPDATE entities SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )
        return await self.get(entity_id)

    async def delete(self, entity_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM entities WHERE id = ?", (entity_id,)
        )
        return cursor.rowcount > 0

    async def list(self, domain: str | None = None, limit: int = 100) -> list[Entity]:
        if domain:
            rows = await self._db.fetchall(
                "SELECT id, name, type, description, attributes, domain, status, source, "
                "created_at, updated_at FROM entities WHERE domain = ? LIMIT ?",
                (domain, limit),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT id, name, type, description, attributes, domain, status, source, "
                "created_at, updated_at FROM entities LIMIT ?",
                (limit,),
            )
        return [_row_to_entity(r) for r in rows]

    async def search(self, keyword: str, domain: str | None = None, limit: int = 10) -> list[Entity]:
        pattern = f"%{keyword}%"
        if domain:
            rows = await self._db.fetchall(
                "SELECT id, name, type, description, attributes, domain, status, source, "
                "created_at, updated_at FROM entities "
                "WHERE (name LIKE ? OR description LIKE ?) AND domain = ? LIMIT ?",
                (pattern, pattern, domain, limit),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT id, name, type, description, attributes, domain, status, source, "
                "created_at, updated_at FROM entities "
                "WHERE name LIKE ? OR description LIKE ? LIMIT ?",
                (pattern, pattern, limit),
            )
        return [_row_to_entity(r) for r in rows]

    async def get_by_ids(self, ids: list[int]) -> list[Entity]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = await self._db.fetchall(
            f"SELECT id, name, type, description, attributes, domain, status, source, "
            f"created_at, updated_at FROM entities WHERE id IN ({placeholders})",
            tuple(ids),
        )
        return [_row_to_entity(r) for r in rows]
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_entity_repo.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/repos/ tests/test_entity_repo.py
git commit -m "feat(repo): add EntityRepo with CRUD + search + get_by_ids"
```

---

### Task 6: RelationRepo

**Files:**
- Create: `src/ai_nexus/repos/relation_repo.py`
- Create: `tests/test_relation_repo.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_relation_repo.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo


@pytest.fixture
async def repos():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    entity_repo = EntityRepo(db)
    relation_repo = RelationRepo(db)
    # 创建两个实体供关系使用
    e1 = await entity_repo.create(EntityCreate(name="订单", type="concept", domain="交易"))
    e2 = await entity_repo.create(EntityCreate(name="用户", type="actor", domain="交易"))
    yield relation_repo, e1, e2
    await db.disconnect()


async def test_create_and_get(repos):
    rel_repo, e1, e2 = repos
    rel = await rel_repo.create(RelationCreate(
        source_entity_id=e1.id,
        relation_type="belongs_to",
        target_entity_id=e2.id,
    ))
    assert rel.id is not None
    fetched = await rel_repo.get(rel.id)
    assert fetched is not None
    assert fetched.relation_type == "belongs_to"


async def test_get_by_entity(repos):
    rel_repo, e1, e2 = repos
    await rel_repo.create(RelationCreate(
        source_entity_id=e1.id, relation_type="rel_a", target_entity_id=e2.id
    ))
    results = await rel_repo.get_by_source(e1.id)
    assert len(results) == 1
    results = await rel_repo.get_by_target(e2.id)
    assert len(results) == 1


async def test_delete(repos):
    rel_repo, e1, e2 = repos
    rel = await rel_repo.create(RelationCreate(
        source_entity_id=e1.id, relation_type="rel_b", target_entity_id=e2.id
    ))
    assert await rel_repo.delete(rel.id) is True
    assert await rel_repo.get(rel.id) is None
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_relation_repo.py -v
```

- [ ] **Step 3: 实现 RelationRepo**

需要先确认 `src/ai_nexus/models/relation.py` 中有 `RelationCreate` 和 `Relation` 模型（查看现有文件，如缺少字段则补齐）。

```python
# src/ai_nexus/repos/relation_repo.py
"""RelationRepo — relations 表单表 CRUD。"""

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.relation import Relation, RelationCreate


def _row_to_relation(row: tuple[Any, ...]) -> Relation:
    return Relation(
        id=row[0],
        source_entity_id=row[1],
        relation_type=row[2],
        target_entity_id=row[3],
        description=row[4],
        conditions=json.loads(row[5]) if row[5] else None,
        weight=row[6],
        status=row[7],
        source=row[8],
        created_at=row[9],
        updated_at=row[10],
    )


_SELECT = (
    "SELECT id, source_entity_id, relation_type, target_entity_id, "
    "description, conditions, weight, status, source, created_at, updated_at FROM relations"
)


class RelationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: RelationCreate) -> Relation:
        cursor = await self._db.execute(
            "INSERT INTO relations (source_entity_id, relation_type, target_entity_id, "
            "description, conditions, weight, status, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.source_entity_id,
                data.relation_type,
                data.target_entity_id,
                data.description,
                json.dumps(data.conditions) if data.conditions else None,
                data.weight,
                data.status,
                data.source,
            ),
        )
        return await self.get(cursor.lastrowid)  # type: ignore[arg-type]

    async def get(self, relation_id: int) -> Relation | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (relation_id,))
        return _row_to_relation(row) if row else None

    async def get_by_source(self, source_entity_id: int) -> list[Relation]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE source_entity_id = ?", (source_entity_id,)
        )
        return [_row_to_relation(r) for r in rows]

    async def get_by_target(self, target_entity_id: int) -> list[Relation]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE target_entity_id = ?", (target_entity_id,)
        )
        return [_row_to_relation(r) for r in rows]

    async def delete(self, relation_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM relations WHERE id = ?", (relation_id,)
        )
        return cursor.rowcount > 0
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_relation_repo.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/repos/relation_repo.py tests/test_relation_repo.py
git commit -m "feat(repo): add RelationRepo"
```

---

### Task 7: RuleRepo

**Files:**
- Create: `src/ai_nexus/repos/rule_repo.py`
- Create: `tests/test_rule_repo.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_rule_repo.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import RuleCreate, RuleUpdate
from ai_nexus.repos.rule_repo import RuleRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield RuleRepo(db)
    await db.disconnect()


async def test_create_and_get(repo: RuleRepo):
    rule = await repo.create(RuleCreate(
        name="禁止直接删除订单",
        description="订单只能标记取消，不能物理删除",
        domain="交易",
        severity="critical",
        status="approved",
    ))
    assert rule.id is not None
    fetched = await repo.get(rule.id)
    assert fetched is not None
    assert fetched.name == "禁止直接删除订单"


async def test_update_status(repo: RuleRepo):
    rule = await repo.create(RuleCreate(
        name="规则X", description="描述", domain="测试", status="pending"
    ))
    updated = await repo.update(rule.id, RuleUpdate(status="approved"))
    assert updated is not None
    assert updated.status == "approved"


async def test_search_by_keyword(repo: RuleRepo):
    await repo.create(RuleCreate(name="支付规则A", description="支付相关", domain="支付", status="approved"))
    await repo.create(RuleCreate(name="库存规则B", description="库存相关", domain="库存", status="approved"))
    results = await repo.search(keyword="支付")
    assert len(results) == 1

async def test_list_by_domain_and_severity(repo: RuleRepo):
    await repo.create(RuleCreate(name="R1", description="d", domain="财务", severity="critical", status="approved"))
    await repo.create(RuleCreate(name="R2", description="d", domain="财务", severity="warning", status="approved"))
    results = await repo.list(domain="财务", severity="critical")
    assert len(results) == 1
    assert results[0].severity == "critical"


async def test_delete(repo: RuleRepo):
    rule = await repo.create(RuleCreate(name="临时规则", description="d", domain="测试", status="approved"))
    assert await repo.delete(rule.id) is True
    assert await repo.get(rule.id) is None
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_rule_repo.py -v
```

- [ ] **Step 3: 实现 RuleRepo**

```python
# src/ai_nexus/repos/rule_repo.py
"""RuleRepo — rules 表单表 CRUD。"""

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import Rule, RuleCreate, RuleUpdate


def _row_to_rule(row: tuple[Any, ...]) -> Rule:
    return Rule(
        id=row[0],
        name=row[1],
        description=row[2],
        domain=row[3],
        severity=row[4],
        conditions=json.loads(row[5]) if row[5] else None,
        related_entity_ids=json.loads(row[6]) if row[6] else None,
        status=row[7],
        source=row[8],
        confidence=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


_SELECT = (
    "SELECT id, name, description, domain, severity, conditions, related_entity_ids, "
    "status, source, confidence, created_at, updated_at FROM rules"
)


class RuleRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: RuleCreate) -> Rule:
        cursor = await self._db.execute(
            "INSERT INTO rules (name, description, domain, severity, conditions, "
            "related_entity_ids, status, source, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.name,
                data.description,
                data.domain,
                data.severity,
                json.dumps(data.conditions) if data.conditions else None,
                json.dumps(data.related_entity_ids) if data.related_entity_ids else None,
                data.status,
                data.source,
                data.confidence,
            ),
        )
        return await self.get(cursor.lastrowid)  # type: ignore[arg-type]

    async def get(self, rule_id: int) -> Rule | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (rule_id,))
        return _row_to_rule(row) if row else None

    async def update(self, rule_id: int, data: RuleUpdate) -> Rule | None:
        fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if not fields:
            return await self.get(rule_id)
        for json_field in ("conditions", "related_entity_ids"):
            if json_field in fields and fields[json_field] is not None:
                fields[json_field] = json.dumps(fields[json_field])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [rule_id]
        await self._db.execute(
            f"UPDATE rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )
        return await self.get(rule_id)

    async def delete(self, rule_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return cursor.rowcount > 0

    async def list(
        self,
        domain: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Rule]:
        where_parts = []
        params: list[Any] = []
        if domain:
            where_parts.append("domain = ?")
            params.append(domain)
        if severity:
            where_parts.append("severity = ?")
            params.append(severity)
        if status:
            where_parts.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(limit)
        rows = await self._db.fetchall(f"{_SELECT} {where} LIMIT ?", tuple(params))
        return [_row_to_rule(r) for r in rows]

    async def search(
        self,
        keyword: str,
        domain: str | None = None,
        severity: str | None = None,
        limit: int = 10,
    ) -> list[Rule]:
        pattern = f"%{keyword}%"
        params: list[Any] = [pattern, pattern]
        extra = ""
        if domain:
            extra += " AND domain = ?"
            params.append(domain)
        if severity:
            extra += " AND severity = ?"
            params.append(severity)
        params.append(limit)
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE (name LIKE ? OR description LIKE ?){extra} LIMIT ?",
            tuple(params),
        )
        return [_row_to_rule(r) for r in rows]

    async def get_by_ids(self, ids: list[int]) -> list[Rule]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE id IN ({placeholders})", tuple(ids)
        )
        return [_row_to_rule(r) for r in rows]
```

> **模型补全检查：** 运行前先看 `src/ai_nexus/models/rule.py`，确认有 `RuleCreate`、`RuleUpdate`、`Rule` 三个类。如果缺少 `RuleUpdate` 或 `RuleCreate` 的 `status` 字段，补上。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_rule_repo.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/repos/rule_repo.py tests/test_rule_repo.py
git commit -m "feat(repo): add RuleRepo with CRUD + search + list filters"
```

---

### Task 8: AuditRepo

**Files:**
- Create: `src/ai_nexus/repos/audit_repo.py`
- Create: `tests/test_audit_repo.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_audit_repo.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.audit import AuditLogCreate
from ai_nexus.repos.audit_repo import AuditRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    yield AuditRepo(db)
    await db.disconnect()


async def test_create_and_list(repo: AuditRepo):
    log = await repo.create(AuditLogCreate(
        table_name="entities",
        record_id=1,
        action="create",
        new_value={"name": "订单"},
        reviewer="admin",
    ))
    assert log.id is not None
    logs = await repo.list_by_record("entities", 1)
    assert len(logs) == 1
    assert logs[0].action == "create"


async def test_list_pending_candidates(repo: AuditRepo):
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=10, action="submit_candidate",
    ))
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=11, action="submit_candidate",
    ))
    await repo.create(AuditLogCreate(
        table_name="rules", record_id=10, action="approve", reviewer="admin"
    ))
    # record_id=10 has been approved; only record_id=11 is still pending
    pending = await repo.list_pending()
    assert len(pending) == 1
    assert pending[0].record_id == 11
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_audit_repo.py -v
```

- [ ] **Step 3: 检查 audit.py 模型**

查看 `src/ai_nexus/models/audit.py`，确认有 `AuditLogCreate` 和 `AuditLog`。如缺失，添加：

```python
# src/ai_nexus/models/audit.py（补充/调整）
from datetime import datetime
from pydantic import BaseModel


class AuditLogCreate(BaseModel):
    table_name: str
    record_id: int
    action: str  # "create"|"update"|"delete"|"submit_candidate"|"approve"|"reject"
    old_value: dict | None = None
    new_value: dict | None = None
    reviewer: str | None = None


class AuditLog(AuditLogCreate):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: 实现 AuditRepo**

```python
# src/ai_nexus/repos/audit_repo.py
"""AuditRepo — knowledge_audit_log 表 CRUD。"""

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.audit import AuditLog, AuditLogCreate


def _row_to_log(row: tuple[Any, ...]) -> AuditLog:
    return AuditLog(
        id=row[0],
        table_name=row[1],
        record_id=row[2],
        action=row[3],
        old_value=json.loads(row[4]) if row[4] else None,
        new_value=json.loads(row[5]) if row[5] else None,
        reviewer=row[6],
        created_at=row[7],
    )


_SELECT = (
    "SELECT id, table_name, record_id, action, old_value, new_value, reviewer, created_at "
    "FROM knowledge_audit_log"
)


class AuditRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: AuditLogCreate) -> AuditLog:
        cursor = await self._db.execute(
            "INSERT INTO knowledge_audit_log "
            "(table_name, record_id, action, old_value, new_value, reviewer) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                data.table_name,
                data.record_id,
                data.action,
                json.dumps(data.old_value) if data.old_value else None,
                json.dumps(data.new_value) if data.new_value else None,
                data.reviewer,
            ),
        )
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (cursor.lastrowid,))
        return _row_to_log(row)  # type: ignore[arg-type]

    async def list_by_record(self, table_name: str, record_id: int) -> list[AuditLog]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE table_name = ? AND record_id = ? ORDER BY created_at",
            (table_name, record_id),
        )
        return [_row_to_log(r) for r in rows]

    async def list_pending(self) -> list[AuditLog]:
        """返回已提交但未审核（无 approve/reject 记录）的候选项最新提交记录。"""
        rows = await self._db.fetchall(
            f"""
            {_SELECT}
            WHERE action = 'submit_candidate'
              AND record_id NOT IN (
                SELECT record_id FROM knowledge_audit_log
                WHERE action IN ('approve', 'reject')
              )
            ORDER BY created_at DESC
            """
        )
        return [_row_to_log(r) for r in rows]
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/test_audit_repo.py -v
# Expected: ALL PASS
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_nexus/repos/audit_repo.py src/ai_nexus/models/audit.py tests/test_audit_repo.py
git commit -m "feat(repo): add AuditRepo with create, list_by_record, list_pending"
```

---

## Chunk 3: Service + Proxy 层

### Task 9: GraphService

**目标：** 组合 EntityRepo + RelationRepo + RuleRepo，提供图遍历查询。

**Files:**
- Create: `src/ai_nexus/services/__init__.py`
- Create: `src/ai_nexus/services/graph_service.py`
- Create: `tests/test_graph_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_graph_service.py
import pytest
from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.relation import RelationCreate
from ai_nexus.models.rule import RuleCreate
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService


@pytest.fixture
async def svc():
    db = Database(":memory:")
    await db.connect()
    await db.run_migrations()
    entity_repo = EntityRepo(db)
    relation_repo = RelationRepo(db)
    rule_repo = RuleRepo(db)
    service = GraphService(entity_repo, relation_repo, rule_repo)
    yield service, entity_repo, relation_repo, rule_repo
    await db.disconnect()


async def test_search_entities_by_keyword(svc):
    service, entity_repo, _, _ = svc
    await entity_repo.create(EntityCreate(name="支付订单", type="concept", domain="支付"))
    await entity_repo.create(EntityCreate(name="用户账户", type="actor", domain="账户"))
    results = await service.search_entities("支付")
    assert len(results) == 1
    assert results[0].name == "支付订单"


async def test_search_rules_by_keyword(svc):
    service, _, _, rule_repo = svc
    await rule_repo.create(RuleCreate(
        name="禁止直接删单", description="订单只能标记", domain="交易", status="approved"
    ))
    results = await service.search_rules("删单")
    assert len(results) == 1


async def test_get_neighbors(svc):
    """get_neighbors 返回与指定实体直接相连的实体。"""
    service, entity_repo, relation_repo, _ = svc
    order = await entity_repo.create(EntityCreate(name="订单", type="concept", domain="交易"))
    user = await entity_repo.create(EntityCreate(name="用户", type="actor", domain="交易"))
    await relation_repo.create(RelationCreate(
        source_entity_id=order.id, relation_type="owned_by", target_entity_id=user.id
    ))
    neighbors = await service.get_neighbors(order.id)
    assert any(n.id == user.id for n in neighbors)


async def test_get_business_context(svc):
    """get_business_context 返回实体列表和规则列表。"""
    service, entity_repo, _, rule_repo = svc
    await entity_repo.create(EntityCreate(name="退款单", type="concept", domain="退款"))
    await rule_repo.create(RuleCreate(
        name="退款规则", description="退款须72h内", domain="退款", status="approved"
    ))
    ctx = await service.get_business_context("退款处理", keywords=["退款"])
    assert len(ctx["entities"]) >= 1
    assert len(ctx["rules"]) >= 1


async def test_fallback_search(svc):
    """fallback_search 用 LIKE 降级查询规则。"""
    service, _, _, rule_repo = svc
    await rule_repo.create(RuleCreate(
        name="库存警戒线", description="低于10件须补货", domain="库存", status="approved"
    ))
    results = await service.fallback_search("库存", domain=None)
    assert len(results) >= 1
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_graph_service.py -v
```

- [ ] **Step 3: 实现 GraphService**

```python
# src/ai_nexus/services/__init__.py
"""Service 层：业务逻辑。"""
```

```python
# src/ai_nexus/services/graph_service.py
"""GraphService — 知识图谱查询（图遍历 + 业务上下文组装）。"""

from ai_nexus.models.entity import Entity
from ai_nexus.models.rule import Rule
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo


class GraphService:
    def __init__(
        self,
        entity_repo: EntityRepo,
        relation_repo: RelationRepo,
        rule_repo: RuleRepo,
    ) -> None:
        self._entities = entity_repo
        self._relations = relation_repo
        self._rules = rule_repo

    async def search_entities(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Entity]:
        return await self._entities.search(query, domain=domain, limit=limit)

    async def search_rules(
        self,
        query: str,
        domain: str | None = None,
        severity: str | None = None,
        limit: int = 10,
    ) -> list[Rule]:
        return await self._rules.search(query, domain=domain, severity=severity, limit=limit)

    async def get_neighbors(self, entity_id: int) -> list[Entity]:
        """返回与 entity_id 直接相连的所有实体（出边 + 入边）。"""
        out_rels = await self._relations.get_by_source(entity_id)
        in_rels = await self._relations.get_by_target(entity_id)
        neighbor_ids = {r.target_entity_id for r in out_rels} | {r.source_entity_id for r in in_rels}
        neighbor_ids.discard(entity_id)
        if not neighbor_ids:
            return []
        return await self._entities.get_by_ids(list(neighbor_ids))

    async def get_by_ids(self, ids: list[int]) -> list[Rule]:
        return await self._rules.get_by_ids(ids)

    async def get_business_context(
        self,
        task_description: str,
        keywords: list[str] | None = None,
    ) -> dict:
        """组装业务上下文：搜索相关实体 + 规则。"""
        search_terms = keywords or [task_description]
        entities: list[Entity] = []
        rules: list[Rule] = []
        seen_entity_ids: set[int] = set()
        seen_rule_ids: set[int] = set()

        for term in search_terms:
            for e in await self._entities.search(term, limit=5):
                if e.id not in seen_entity_ids:
                    entities.append(e)
                    seen_entity_ids.add(e.id)
            for r in await self._rules.search(term, limit=5):
                if r.id not in seen_rule_ids:
                    rules.append(r)
                    seen_rule_ids.add(r.id)

        return {
            "task": task_description,
            "entities": [e.model_dump() for e in entities],
            "rules": [r.model_dump() for r in rules],
        }

    async def fallback_search(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Rule]:
        """降级：SQLite LIKE 查询规则（mem0 不可用时使用）。"""
        return await self._rules.search(query, domain=domain, limit=limit)
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_graph_service.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/services/ tests/test_graph_service.py
git commit -m "feat(service): add GraphService with entity/rule search + graph traversal"
```

---

### Task 10: Mem0Proxy

**目标：** 通过 httpx 代理调用 mem0 REST API，暴露 `is_available()`、`search()`。

**Files:**
- Create: `src/ai_nexus/proxy/__init__.py`
- Create: `src/ai_nexus/proxy/mem0_proxy.py`
- Create: `tests/test_mem0_proxy.py`

- [ ] **Step 1: 写测试（mock httpx）**

```python
# tests/test_mem0_proxy.py
from unittest.mock import AsyncMock, patch

import pytest

from ai_nexus.proxy.mem0_proxy import Mem0Proxy


@pytest.fixture
def proxy():
    return Mem0Proxy(base_url="http://localhost:8080")


async def test_is_available_when_up(proxy: Mem0Proxy):
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        assert await proxy.is_available() is True


async def test_is_available_when_down(proxy: Mem0Proxy):
    import httpx
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("refused")):
        assert await proxy.is_available() is False


async def test_search_returns_ids(proxy: Mem0Proxy):
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"id": 10, "score": 0.9},
            {"id": 20, "score": 0.7},
        ]
    }
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        ids = await proxy.search("支付规则", limit=5)
        assert ids == [10, 20]


async def test_search_returns_empty_when_down(proxy: Mem0Proxy):
    import httpx
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
        ids = await proxy.search("任意查询")
        assert ids == []
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_mem0_proxy.py -v
```

- [ ] **Step 3: 实现 Mem0Proxy**

```python
# src/ai_nexus/proxy/__init__.py
"""Proxy 层：外部服务代理。"""
```

```python
# src/ai_nexus/proxy/mem0_proxy.py
"""Mem0Proxy — 通过 httpx 代理调用 mem0 REST API。"""

import logging

import httpx

logger = logging.getLogger(__name__)


class Mem0Proxy:
    """代理 mem0 REST API，暴露 is_available + search。"""

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 3.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def is_available(self) -> bool:
        """检查 mem0 服务是否可达。"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def search(self, query: str, limit: int = 10) -> list[int]:
        """在 mem0 中语义搜索，返回命中的 record_id 列表。

        mem0 search API 预期返回格式：
        {"results": [{"id": <int>, "score": <float>}, ...]}

        如果 mem0 不可达，返回空列表（由上层降级处理）。
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/search",
                    json={"query": query, "limit": limit},
                )
                if resp.status_code != 200:
                    logger.warning("mem0 search returned %d", resp.status_code)
                    return []
                data = resp.json()
                return [r["id"] for r in data.get("results", [])]
        except Exception as e:
            logger.warning("mem0 search failed: %s", e)
            return []
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_mem0_proxy.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/ai_nexus/proxy/ tests/test_mem0_proxy.py
git commit -m "feat(proxy): add Mem0Proxy with httpx-based is_available + search"
```

---

### Task 11: QueryService

**目标：** 统一查询入口，内部自动路由：结构化→图遍历，模糊→mem0，降级→LIKE。

**Files:**
- Create: `src/ai_nexus/services/query_service.py`
- Create: `tests/test_query_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_query_service.py
from unittest.mock import AsyncMock

import pytest

from ai_nexus.models.rule import Rule
from ai_nexus.services.query_service import QueryService


def _make_rule(id: int, name: str) -> Rule:
    return Rule(id=id, name=name, description="d", domain="测试", status="approved")


@pytest.fixture
def mocks():
    graph_svc = AsyncMock()
    mem0_proxy = AsyncMock()
    return graph_svc, mem0_proxy


async def test_returns_graph_results_when_found(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = [_make_rule(1, "支付规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("支付")
    assert len(results) == 1
    graph_svc.search_rules.assert_called_once()
    mem0_proxy.is_available.assert_not_called()


async def test_falls_through_to_mem0_when_graph_empty(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = []
    mem0_proxy.is_available.return_value = True
    mem0_proxy.search.return_value = [42]
    graph_svc.get_by_ids.return_value = [_make_rule(42, "库存规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("库存")
    assert len(results) == 1
    assert results[0].id == 42


async def test_fallback_to_like_when_mem0_unavailable(mocks):
    graph_svc, mem0_proxy = mocks
    graph_svc.search_rules.return_value = []
    mem0_proxy.is_available.return_value = False
    graph_svc.fallback_search.return_value = [_make_rule(99, "退款规则")]
    svc = QueryService(graph_svc, mem0_proxy)
    results = await svc.query_rules("退款")
    assert len(results) == 1
    assert results[0].id == 99
    graph_svc.fallback_search.assert_called_once()
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_query_service.py -v
```

- [ ] **Step 3: 实现 QueryService**

```python
# src/ai_nexus/services/query_service.py
"""QueryService — 统一查询入口，内部自动路由。"""

from ai_nexus.models.rule import Rule
from ai_nexus.proxy.mem0_proxy import Mem0Proxy
from ai_nexus.services.graph_service import GraphService


class QueryService:
    def __init__(self, graph_service: GraphService, mem0_proxy: Mem0Proxy) -> None:
        self._graph = graph_service
        self._mem0 = mem0_proxy

    async def query_rules(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[Rule]:
        """统一规则查询，自动路由：
        1. 图遍历（关键词命中）→ 直接返回
        2. mem0 语义检索（模糊匹配）→ 回查 SQLite
        3. 降级：SQLite LIKE
        """
        results = await self._graph.search_rules(query, domain=domain, limit=limit)
        if results:
            return results

        if await self._mem0.is_available():
            ids = await self._mem0.search(query, limit=limit)
            if ids:
                return await self._graph.get_by_ids(ids)

        return await self._graph.fallback_search(query, domain=domain, limit=limit)
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_query_service.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: 全量测试**

```bash
pytest tests/ -v
ruff check src/
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_nexus/services/query_service.py tests/test_query_service.py
git commit -m "feat(service): add QueryService with 3-tier routing (graph → mem0 → fallback)"
```

---

## Chunk 4: MCP + REST API 层

### Task 12: MCP 工具对接真实 Service

**目标：** 将 5 个占位 MCP 工具替换为真实的 service/proxy 调用。

**Files:**
- Modify: `src/ai_nexus/mcp/server.py`
- Create: `tests/test_mcp_tools.py`

**设计：** MCP 工具通过 `request.app.state` 获取 db（FastMCP 在 HTTP 模式下有 request context）。为保持简洁，将 service 实例化从 main.py 的 lifespan 中注入到 `app.state`。

- [ ] **Step 1: 写测试**

```python
# tests/test_mcp_tools.py
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


def test_health_and_mcp_mount():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200


# MCP 工具的实际测试通过 mcp_server.py 函数直接调用
async def test_search_entities_tool_returns_json():
    from ai_nexus.mcp.server import search_entities

    with patch("ai_nexus.mcp.server._get_graph_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.search_entities.return_value = []
        mock_get.return_value = mock_svc
        result = await search_entities("订单")
        data = json.loads(result)
        assert "results" in data


async def test_search_rules_tool_returns_json():
    from ai_nexus.mcp.server import search_rules

    with patch("ai_nexus.mcp.server._get_graph_service") as mock_get:
        mock_svc = AsyncMock()
        mock_svc.search_rules.return_value = []
        mock_get.return_value = mock_svc
        result = await search_rules("支付规则")
        data = json.loads(result)
        assert "results" in data
```

- [ ] **Step 2: 运行，记录当前状态**

```bash
pytest tests/test_mcp_tools.py -v
```

- [ ] **Step 3: 修改 main.py — 在 lifespan 中初始化 service 并存入 app.state**

在 `db_lifespan` 中，db 初始化后追加 service 初始化：

```python
# 在 db_lifespan yield 前添加：
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService
from ai_nexus.proxy.mem0_proxy import Mem0Proxy

entity_repo = EntityRepo(db)
relation_repo = RelationRepo(db)
rule_repo = RuleRepo(db)
audit_repo = AuditRepo(db)
mem0_proxy = Mem0Proxy(base_url=settings.mem0_api_url)
graph_service = GraphService(entity_repo, relation_repo, rule_repo)
query_service = QueryService(graph_service, mem0_proxy)

app.state.graph_service = graph_service
app.state.query_service = query_service
app.state.audit_repo = audit_repo
```

- [ ] **Step 4: 修改 mcp/server.py — 工具调用真实 service**

FastMCP 在 HTTP 模式下工具函数无法直接访问 FastAPI `app.state`。解决方案：使用**模块级单例**，由 main.py lifespan 注入。

```python
# src/ai_nexus/mcp/server.py
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
```

- [ ] **Step 5: 在 main.py lifespan 中调用 init_services**

在 `app.state.graph_service = graph_service` 之后追加：

```python
from ai_nexus.mcp.server import init_services
init_services(graph_service, query_service)
```

- [ ] **Step 6: 运行测试**

```bash
pytest tests/test_mcp_tools.py tests/ -v
ruff check src/
```

- [ ] **Step 7: Commit**

```bash
git add src/ai_nexus/mcp/server.py src/ai_nexus/main.py tests/test_mcp_tools.py
git commit -m "feat(mcp): wire MCP tools to real GraphService + QueryService"
```

---

### Task 13: REST API CRUD + Search 端点

**Files:**
- Create: `src/ai_nexus/api/__init__.py`
- Create: `src/ai_nexus/api/dependencies.py`
- Create: `src/ai_nexus/api/router.py`
- Modify: `src/ai_nexus/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_create_entity(client):
    resp = client.post("/api/entities", json={
        "name": "订单", "type": "concept", "domain": "交易"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "订单"
    assert "id" in data


def test_get_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "用户", "type": "actor", "domain": "账户"
    })
    entity_id = create_resp.json()["id"]
    resp = client.get(f"/api/entities/{entity_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "用户"


def test_get_entity_not_found(client):
    resp = client.get("/api/entities/99999")
    assert resp.status_code == 404


def test_update_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "商品", "type": "object", "domain": "库存"
    })
    entity_id = create_resp.json()["id"]
    resp = client.put(f"/api/entities/{entity_id}", json={"description": "库存商品"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "库存商品"


def test_delete_entity(client):
    create_resp = client.post("/api/entities", json={
        "name": "临时实体", "type": "t", "domain": "测试"
    })
    entity_id = create_resp.json()["id"]
    resp = client.delete(f"/api/entities/{entity_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/entities/{entity_id}")
    assert resp.status_code == 404


def test_create_rule(client):
    resp = client.post("/api/rules", json={
        "name": "禁止删单",
        "description": "订单不能物理删除",
        "domain": "交易",
        "severity": "critical",
        "status": "approved",
    })
    assert resp.status_code == 201
    assert resp.json()["severity"] == "critical"


def test_search_rules(client):
    client.post("/api/rules", json={
        "name": "支付规则X",
        "description": "支付需要校验",
        "domain": "支付",
        "severity": "warning",
        "status": "approved",
    })
    resp = client.post("/api/search", json={"query": "支付", "type": "rules"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_api.py -v
```

- [ ] **Step 3: 实现 dependencies.py**

```python
# src/ai_nexus/api/__init__.py
"""REST API 层。"""
```

```python
# src/ai_nexus/api/dependencies.py
"""FastAPI 依赖注入：从 app.state 获取 service 实例。"""

from fastapi import Request

from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service


def get_audit_repo(request: Request) -> AuditRepo:
    return request.app.state.audit_repo
```

- [ ] **Step 4: 实现 router.py**

```python
# src/ai_nexus/api/router.py
"""REST API 路由：知识图谱 CRUD + 统一搜索。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

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
    return await svc._rules.list(domain=domain, severity=severity, status=status_filter, limit=limit)


# --- Unified Search ---

class SearchRequest:
    def __init__(self, query: str, type: str = "rules", domain: str | None = None, limit: int = 10):
        self.query = query
        self.type = type
        self.domain = domain
        self.limit = limit


from pydantic import BaseModel


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
```

- [ ] **Step 5: 在 main.py 中注册 router**

在 `create_app()` 中，`app.mount("/mcp", ...)` 之前加：

```python
from ai_nexus.api.router import router as api_router
app.include_router(api_router)
```

- [ ] **Step 6: 运行测试**

```bash
pytest tests/test_api.py -v
ruff check src/
```

- [ ] **Step 7: Commit**

```bash
git add src/ai_nexus/api/ src/ai_nexus/main.py tests/test_api.py
git commit -m "feat(api): add REST API CRUD for entities/rules + unified search endpoint"
```

---

### Task 14: 知识审核工作流 + Hook 端点

**Files:**
- Modify: `src/ai_nexus/api/router.py`
- Create: `tests/test_audit_api.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_audit_api.py
import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_submit_candidate_and_list_pending(client):
    # 提交候选规则
    resp = client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 999,
        "action": "submit_candidate",
        "new_value": {"name": "候选规则"},
    })
    assert resp.status_code == 201

    # 查看待审核列表
    resp = client.get("/api/audit/pending")
    assert resp.status_code == 200
    pending = resp.json()
    assert len(pending) >= 1


def test_approve_candidate(client):
    # 提交
    client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 888,
        "action": "submit_candidate",
    })
    # 审核通过
    resp = client.post("/api/audit/888/approve", json={"reviewer": "admin"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject_candidate(client):
    client.post("/api/audit/candidates", json={
        "table_name": "rules",
        "record_id": 777,
        "action": "submit_candidate",
    })
    resp = client.post("/api/audit/777/reject", json={"reviewer": "admin"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_pre_plan_hook(client):
    resp = client.post("/api/hooks/pre-plan", json={
        "task_description": "实现支付退款功能",
        "keywords": ["支付", "退款"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert "rules" in data


def test_pre_commit_hook(client):
    resp = client.post("/api/hooks/pre-commit", json={
        "change_description": "删除了 orders 表的 delete 接口",
        "affected_entities": ["订单"],
        "diff_summary": "- router.delete('/orders/{id}')",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "violations" in data
    assert "passed" in data
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_audit_api.py -v
```

- [ ] **Step 3: 在 router.py 中追加审核 + Hook 端点**

```python
# 追加到 src/ai_nexus/api/router.py

from ai_nexus.api.dependencies import get_audit_repo
from ai_nexus.models.audit import AuditLog, AuditLogCreate
from ai_nexus.repos.audit_repo import AuditRepo

AuditRepoInj = Annotated[AuditRepo, Depends(get_audit_repo)]


# --- 审核工作流 ---

@router.post("/audit/candidates", response_model=AuditLog, status_code=status.HTTP_201_CREATED)
async def submit_candidate(data: AuditLogCreate, repo: AuditRepoInj):
    return await repo.create(data)


@router.get("/audit/pending", response_model=list[AuditLog])
async def list_pending(repo: AuditRepoInj):
    return await repo.list_pending()


class ReviewAction(BaseModel):
    reviewer: str = "system"


@router.post("/audit/{record_id}/approve")
async def approve_candidate(record_id: int, action: ReviewAction, repo: AuditRepoInj):
    log = await repo.create(AuditLogCreate(
        table_name="knowledge_audit_log",
        record_id=record_id,
        action="approve",
        reviewer=action.reviewer,
    ))
    return {"status": "approved", "record_id": record_id, "log_id": log.id}


@router.post("/audit/{record_id}/reject")
async def reject_candidate(record_id: int, action: ReviewAction, repo: AuditRepoInj):
    log = await repo.create(AuditLogCreate(
        table_name="knowledge_audit_log",
        record_id=record_id,
        action="reject",
        reviewer=action.reviewer,
    ))
    return {"status": "rejected", "record_id": record_id, "log_id": log.id}


# --- 开发流程 Hook ---

class PrePlanRequest(BaseModel):
    task_description: str
    keywords: list[str] | None = None


class PreCommitRequest(BaseModel):
    change_description: str
    affected_entities: list[str] | None = None
    diff_summary: str | None = None


@router.post("/hooks/pre-plan")
async def pre_plan_hook(body: PrePlanRequest, graph_svc: GraphSvc):
    ctx = await graph_svc.get_business_context(body.task_description, keywords=body.keywords)
    return ctx


@router.post("/hooks/pre-commit")
async def pre_commit_hook(body: PreCommitRequest, query_svc: QuerySvc):
    keywords = body.affected_entities or [body.change_description]
    violations = []
    for kw in keywords:
        rules = await query_svc.query_rules(kw, limit=5)
        for rule in rules:
            if rule.status == "approved" and rule.severity == "critical":
                violations.append({
                    "rule": rule.name,
                    "description": rule.description,
                    "severity": rule.severity,
                })
    return {"violations": violations, "passed": len(violations) == 0}
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_audit_api.py -v
# Expected: ALL PASS
```

- [ ] **Step 5: 全量测试 + Lint**

```bash
pytest tests/ -v
ruff check src/
```

期望：全部通过，零 lint 错误。

- [ ] **Step 6: Commit**

```bash
git add src/ai_nexus/api/router.py tests/test_audit_api.py
git commit -m "feat(api): add audit workflow endpoints + pre-plan/pre-commit hooks"
```

---

## 完成检查清单

所有 Task 完成后，验证：

```bash
# 1. 全量测试通过
pytest tests/ -v --tb=short

# 2. 零 lint 错误
ruff check src/

# 3. 服务可以启动
python -m ai_nexus.main
# 访问 http://localhost:8000/health → {"status": "ok"}
# 访问 http://localhost:8000/docs → Swagger UI 显示所有端点
```

核对 MCP 工具列表（共 5 个）：
- [ ] `search_entities`
- [ ] `search_rules`
- [ ] `get_business_context`
- [ ] `validate_against_rules`
- [ ] `submit_knowledge_candidate`

核对 REST API 端点（最小集）：
- [ ] `GET/POST /api/entities`
- [ ] `GET/PUT/DELETE /api/entities/{id}`
- [ ] `GET/POST /api/rules`
- [ ] `GET/PUT/DELETE /api/rules/{id}`
- [ ] `POST /api/search`
- [ ] `GET /api/audit/pending`
- [ ] `POST /api/audit/candidates`
- [ ] `POST /api/audit/{id}/approve`
- [ ] `POST /api/audit/{id}/reject`
- [ ] `POST /api/hooks/pre-plan`
- [ ] `POST /api/hooks/pre-commit`

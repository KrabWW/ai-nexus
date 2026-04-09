"""Migration tests — TDD approach."""
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

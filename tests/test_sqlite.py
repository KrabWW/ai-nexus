"""Tests for SQLite database module."""

import pytest

from ai_nexus.db.sqlite import Database


@pytest.fixture
async def db():
    """Create a test database instance using in-memory SQLite."""
    db = Database(":memory:")
    await db.connect()
    await db.init_schema()
    yield db
    await db.disconnect()


@pytest.mark.asyncio
async def test_database_connection(db: Database):
    """Test database can connect and initialize schema."""
    assert db._conn is not None

    # Check that tables exist
    tables = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [row[0] for row in tables]
    assert "entities" in table_names
    assert "relations" in table_names
    assert "rules" in table_names
    assert "knowledge_audit_log" in table_names


@pytest.mark.asyncio
async def test_database_execute(db: Database):
    """Test execute method."""
    cursor = await db.execute(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        ("Test Entity", "test_type", "test_domain"),
    )
    assert cursor.lastrowid is not None


@pytest.mark.asyncio
async def test_database_fetchone(db: Database):
    """Test fetchone method."""
    await db.execute(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        ("Single Entity", "type1", "domain1"),
    )

    row = await db.fetchone(
        "SELECT name, type, domain FROM entities WHERE name = ?",
        ("Single Entity",),
    )

    assert row is not None
    assert row[0] == "Single Entity"
    assert row[1] == "type1"
    assert row[2] == "domain1"


@pytest.mark.asyncio
async def test_database_fetchall(db: Database):
    """Test fetchall method."""
    await db.execute(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        ("Entity 1", "type1", "domain1"),
    )
    await db.execute(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        ("Entity 2", "type1", "domain1"),
    )

    rows = await db.fetchall(
        "SELECT name FROM entities WHERE type = ? ORDER BY name",
        ("type1",),
    )

    assert len(rows) == 2
    assert rows[0][0] == "Entity 1"
    assert rows[1][0] == "Entity 2"


@pytest.mark.asyncio
async def test_database_executemany(db: Database):
    """Test executemany method."""
    params = [
        ("Batch 1", "batch_type", "batch_domain"),
        ("Batch 2", "batch_type", "batch_domain"),
        ("Batch 3", "batch_type", "batch_domain"),
    ]

    await db.executemany(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        params,
    )

    rows = await db.fetchall(
        "SELECT name FROM entities WHERE type = ? ORDER BY name",
        ("batch_type",),
    )

    assert len(rows) == 3


@pytest.mark.asyncio
async def test_database_not_connected():
    """Test error handling when database is not connected."""
    db = Database("/tmp/test_not_connected.db")

    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.execute("SELECT 1")

    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.fetchone("SELECT 1")

    with pytest.raises(RuntimeError, match="Database not connected"):
        await db.fetchall("SELECT 1")


@pytest.mark.asyncio
async def test_init_schema_idempotent(db: Database):
    """Test that init_schema can be called multiple times safely."""
    # First init already happened in fixture
    await db.init_schema()
    await db.init_schema()

    # Should still work
    await db.execute(
        "INSERT INTO entities (name, type, domain) VALUES (?, ?, ?)",
        ("Test", "test", "test"),
    )

"""Tests for Database.transaction() context manager."""

import pytest

from ai_nexus.db.sqlite import Database


@pytest.mark.asyncio
async def test_transaction_commit(tmp_path):
    """Test that transaction commits on success."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    async with db.transaction():
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        await db.execute("INSERT INTO test (value) VALUES (?)", ("test_value",))

    # After transaction, data should be visible
    rows = await db.fetchall("SELECT value FROM test")
    assert len(rows) == 1
    assert rows[0][0] == "test_value"

    await db.disconnect()


@pytest.mark.asyncio
async def test_transaction_rollback(tmp_path):
    """Test that transaction rolls back on exception."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    # Create table first
    await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

    try:
        async with db.transaction():
            await db.execute("INSERT INTO test (value) VALUES (?)", ("will_rollback",))
            raise ValueError("Simulated error")
    except ValueError:
        pass

    # After failed transaction, data should not exist
    rows = await db.fetchall("SELECT value FROM test")
    assert len(rows) == 0

    await db.disconnect()


@pytest.mark.asyncio
async def test_nested_transaction_raises(tmp_path):
    """Test that nested transactions raise RuntimeError."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    try:
        async with db.transaction():
            with pytest.raises(RuntimeError, match="Nested transactions not supported"):
                async with db.transaction():
                    pass
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_non_transaction_code_unaffected(tmp_path):
    """Test that non-transaction code still works with auto-commit."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    # Create table without transaction
    await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    await db.execute("INSERT INTO test (value) VALUES (?)", ("value1",))

    # Data should be immediately visible
    rows = await db.fetchall("SELECT value FROM test")
    assert len(rows) == 1
    assert rows[0][0] == "value1"

    await db.disconnect()


@pytest.mark.asyncio
async def test_transaction_isolation(tmp_path):
    """Test that transactions are isolated from each other."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

    # First transaction
    async with db.transaction():
        await db.execute("INSERT INTO test (value) VALUES (?)", ("txn1",))

    # Second transaction
    async with db.transaction():
        await db.execute("INSERT INTO test (value) VALUES (?)", ("txn2",))

    # Both should be committed
    rows = await db.fetchall("SELECT value FROM test ORDER BY value")
    assert len(rows) == 2
    assert rows[0][0] == "txn1"
    assert rows[1][0] == "txn2"

    await db.disconnect()

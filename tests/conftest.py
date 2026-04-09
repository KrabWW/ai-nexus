"""Shared test fixtures for AI Nexus."""

import pytest

from ai_nexus.db.sqlite import Database


@pytest.fixture
async def db():
    """Provide an in-memory SQLite database with schema initialized."""
    database = Database(":memory:")
    await database.connect()
    await database.init_schema()
    yield database
    await database.disconnect()

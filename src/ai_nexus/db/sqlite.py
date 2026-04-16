"""Async SQLite connection management using aiosqlite."""

import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import aiosqlite

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """Async SQLite database connection manager.

    Manages a single aiosqlite connection with WAL mode and foreign key support.
    """

    _txn: ContextVar["str | None"] = ContextVar("_txn", default=None)

    def __init__(self, db_path: str | Path) -> None:
        """Initialize database manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and configure settings.

        Enables:
        - WAL mode for better concurrency
        - Foreign key constraints
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def transaction(self):
        """Async transaction context manager.

        Begins a transaction, yields control, and commits on success.
        Rolls back on exception and re-raises it.

        Raises:
            RuntimeError: If called within an existing transaction (nested).
        """
        if self._txn.get() is not None:
            raise RuntimeError("Nested transactions not supported")
        token = self._txn.set("active")
        try:
            if not self._conn:
                raise RuntimeError("Database not connected. Call connect() first.")
            await self._conn.execute("BEGIN")
            yield
            await self._conn.commit()
        except Exception:
            if self._conn:
                await self._conn.rollback()
            raise
        finally:
            self._txn.reset(token)

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

    async def init_schema(self) -> None:
        """向后兼容：调用 run_migrations。"""
        await self.run_migrations()

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement to execute.
            params: Parameters for the SQL statement.

        Returns:
            aiosqlite cursor for the executed statement.

        Raises:
            RuntimeError: If database is not connected.
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        # Only auto-commit if not in a transaction
        if self._txn.get() is None:
            await self._conn.commit()
        return cursor

    async def fetchone(self, sql: str, params: tuple = ()) -> tuple[Any, ...] | None:
        """Fetch a single row from the database.

        Args:
            sql: SQL query to execute.
            params: Parameters for the SQL query.

        Returns:
            A single row as a tuple, or None if no rows match.

        Raises:
            RuntimeError: If database is not connected.
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[tuple[Any, ...]]:
        """Fetch all rows from the database.

        Args:
            sql: SQL query to execute.
            params: Parameters for the SQL query.

        Returns:
            A list of rows, where each row is a tuple.

        Raises:
            RuntimeError: If database is not connected.
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchall()

    async def executemany(self, sql: str, params: list[tuple]) -> aiosqlite.Cursor:
        """Execute a SQL statement with multiple parameter sets.

        Args:
            sql: SQL statement to execute.
            params: List of parameter tuples for the SQL statement.

        Returns:
            aiosqlite cursor for the executed statement.

        Raises:
            RuntimeError: If database is not connected.
        """
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.executemany(sql, params)
        # Only auto-commit if not in a transaction
        if self._txn.get() is None:
            await self._conn.commit()
        return cursor

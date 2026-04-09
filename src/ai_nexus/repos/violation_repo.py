"""ViolationRepo — violation_events 表 CRUD + 统计。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.violation import (
    ViolationEvent,
    ViolationEventCreate,
    ViolationEventUpdate,
    ViolationStats,
)


def _row_to_event(row: tuple[Any, ...]) -> ViolationEvent:
    return ViolationEvent(
        id=row[0],
        rule_id=row[1],
        change_description=row[2],
        resolution=row[3],
        created_at=datetime.fromisoformat(row[4]) if row[4] else None,
        resolved_at=datetime.fromisoformat(row[5]) if row[5] else None,
    )


_SELECT = (
    "SELECT id, rule_id, change_description, resolution, created_at, resolved_at "
    "FROM violation_events"
)


class ViolationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: ViolationEventCreate) -> ViolationEvent:
        cursor = await self._db.execute(
            "INSERT INTO violation_events (rule_id, change_description, resolution) "
            "VALUES (?, ?, ?)",
            (data.rule_id, data.change_description, data.resolution),
        )
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (cursor.lastrowid,))
        return _row_to_event(row)  # type: ignore[arg-type]

    async def get(self, event_id: int) -> ViolationEvent | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (event_id,))
        return _row_to_event(row) if row else None

    async def update(self, event_id: int, data: ViolationEventUpdate) -> ViolationEvent | None:
        if data.resolution is None:
            return await self.get(event_id)

        # If resolving, set resolved_at timestamp
        if data.resolution != "pending":
            await self._db.execute(
                "UPDATE violation_events SET resolution = ?, resolved_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (data.resolution, event_id),
            )
        else:
            await self._db.execute(
                "UPDATE violation_events SET resolution = ?, resolved_at = NULL "
                "WHERE id = ?",
                (data.resolution, event_id),
            )
        return await self.get(event_id)

    async def list_by_rule(
        self, rule_id: str, limit: int = 100
    ) -> list[ViolationEvent]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE rule_id = ? ORDER BY created_at DESC LIMIT ?",
            (rule_id, limit),
        )
        return [_row_to_event(r) for r in rows]

    async def list_recent(
        self, days: int = 30, resolution: str | None = None, limit: int = 1000
    ) -> list[ViolationEvent]:
        """List recent violation events within the specified days."""
        since = datetime.now() - timedelta(days=days)
        where_clause = "WHERE created_at >= ?"
        params: list[Any] = [since.isoformat()]

        if resolution:
            where_clause += " AND resolution = ?"
            params.append(resolution)

        params.append(limit)
        rows = await self._db.fetchall(
            f"{_SELECT} {where_clause} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_event(r) for r in rows]

    async def get_stats(self, days: int = 30) -> list[ViolationStats]:
        """Get violation statistics per rule for the last N days."""
        since = datetime.now() - timedelta(days=days)

        rows = await self._db.fetchall(
            """
            SELECT
                rule_id,
                COUNT(*) as violation_count,
                SUM(CASE WHEN resolution = 'fixed' THEN 1 ELSE 0 END) as fixed_count,
                AVG(CASE
                    WHEN resolution = 'fixed' AND resolved_at IS NOT NULL
                    THEN (julianday(resolved_at) - julianday(created_at)) * 24
                    ELSE NULL
                END) as avg_fix_time_hours
            FROM violation_events
            WHERE created_at >= ?
            GROUP BY rule_id
            ORDER BY violation_count DESC
            """,
            (since.isoformat(),),
        )

        stats: list[ViolationStats] = []
        for row in rows:
            rule_id, violation_count, fixed_count, avg_fix_time = row
            fix_rate = fixed_count / violation_count if violation_count > 0 else 0.0
            stats.append(
                ViolationStats(
                    rule_id=rule_id,
                    violation_count=violation_count,
                    fixed_count=fixed_count,
                    fix_rate=fix_rate,
                    avg_fix_time_hours=round(avg_fix_time, 2) if avg_fix_time else None,
                )
            )
        return stats

    async def count_similar_uncaught(
        self, change_description: str, days: int = 30, min_similarity: int = 3
    ) -> int:
        """Count similar uncaught violations for pattern detection.

        Uses simple keyword matching for similarity detection.
        """
        # Extract keywords from change description (simple approach)
        # In production, might use semantic similarity
        keywords = set(change_description.lower().split())

        if not keywords:
            return 0

        # Get recent events that weren't caught (passed validation but were flagged)
        since = datetime.now() - timedelta(days=days)
        rows = await self._db.fetchall(
            """
            SELECT change_description FROM violation_events
            WHERE created_at >= ? AND resolution IN ('ignored', 'suppressed')
            """,
            (since.isoformat(),),
        )

        similar_count = 0
        for (desc,) in rows:
            desc_words = set(desc.lower().split())
            overlap = len(keywords & desc_words)
            if overlap >= min_similarity:
                similar_count += 1

        return similar_count

"""RelationRepo — relations 表单表 CRUD。"""

from __future__ import annotations

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

    async def list(self, limit: int = 100) -> list[Relation]:
        """列出所有关系，用于控制台管理页面。"""
        rows = await self._db.fetchall(f"{_SELECT} LIMIT ?", (limit,))
        return [_row_to_relation(r) for r in rows]

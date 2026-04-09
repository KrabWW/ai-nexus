"""EntityRepo — entities 表单表 CRUD。"""

from __future__ import annotations

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

    async def list(
        self, domain: str | None = None, limit: int = 100
    ) -> list[Entity]:
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

    async def search(
        self, keyword: str, domain: str | None = None, limit: int = 10
    ) -> list[Entity]:
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

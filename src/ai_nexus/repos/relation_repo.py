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

    async def list_all(self, limit: int = 100000) -> list[Relation]:
        """获取所有关系（用于图谱批量加载）。"""
        rows = await self._db.fetchall(f"{_SELECT} LIMIT ?", (limit,))
        return [_row_to_relation(r) for r in rows]

    async def get_all_for_entities(self, entity_ids: list[int]) -> list[Relation]:
        """批量查询多个实体的所有关系（出边+入边）。"""
        if not entity_ids:
            return []
        placeholders = ",".join("?" * len(entity_ids))
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE source_entity_id IN ({placeholders}) "
            f"OR target_entity_id IN ({placeholders})",
            tuple(entity_ids) * 2,
        )
        return [_row_to_relation(r) for r in rows]

    async def create_pending(
        self,
        source_name: str,
        source_domain: str,
        target_name: str,
        target_domain: str,
        relation_type: str,
        domain: str,
        description: str = "",
        conditions: dict | None = None,
    ) -> int:
        """Create a pending relation for entities that don't exist yet.

        Args:
            source_name: Name of the source entity
            source_domain: Domain of the source entity
            target_name: Name of the target entity
            target_domain: Domain of the target entity
            relation_type: Type of relationship
            domain: Business domain for the relation
            description: Optional description
            conditions: Optional conditions as JSON

        Returns:
            ID of the created pending relation
        """
        cursor = await self._db.execute(
            """INSERT INTO pending_relations
               (source_name, source_domain, target_name, target_domain,
                relation_type, domain, description, conditions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_name,
                source_domain,
                target_name,
                target_domain,
                relation_type,
                domain,
                description,
                json.dumps(conditions) if conditions else None,
            ),
        )
        return cursor.lastrowid

    async def list_pending(self, limit: int = 100) -> list[dict]:
        """List all pending relations.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of pending relation dicts
        """
        rows = await self._db.fetchall(
            """SELECT id, source_name, source_domain, target_name, target_domain,
                      relation_type, domain, description, conditions, status,
                      retry_count, created_at, updated_at
               FROM pending_relations
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [
            {
                "id": r[0],
                "source_name": r[1],
                "source_domain": r[2],
                "target_name": r[3],
                "target_domain": r[4],
                "relation_type": r[5],
                "domain": r[6],
                "description": r[7],
                "conditions": json.loads(r[8]) if r[8] else None,
                "status": r[9],
                "retry_count": r[10],
                "created_at": r[11],
                "updated_at": r[12],
            }
            for r in rows
        ]

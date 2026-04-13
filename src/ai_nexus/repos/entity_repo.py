"""EntityRepo — entities 表单表 CRUD。"""

from __future__ import annotations

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.entity import Entity, EntityCreate, EntityUpdate
from ai_nexus.repos.rule_repo import _tokenize_query


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

    @staticmethod
    def _normalize_name(name: str) -> str:
        """标准化名称用于去重比较。

        Args:
            name: 原始名称

        Returns:
            标准化后的名称（trim + casefold）
        """
        return name.strip().casefold()

    async def create(self, data: EntityCreate) -> Entity:
        cursor = await self._db.execute(
            """INSERT INTO entities
               (name, type, description, attributes, domain, status, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.name.strip(),
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
        if "name" in fields and fields["name"] is not None:
            fields["name"] = fields["name"].strip()
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
        tokens = _tokenize_query(keyword)
        if not tokens:
            return []
        conditions: list[str] = []
        params: list[Any] = []
        for tok in tokens:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{tok}%", f"%{tok}%"])
        where = " AND ".join(conditions)
        if domain:
            where += " AND domain = ?"
            params.append(domain)
        params.append(limit)
        rows = await self._db.fetchall(
            "SELECT id, name, type, description, attributes, domain, status, source, "
            f"created_at, updated_at FROM entities WHERE ({where}) LIMIT ?",
            tuple(params),
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

    async def get_by_names(self, domain: str, names: list[str]) -> dict[str, Entity]:
        """Batch lookup entities by name within a domain.

        Args:
            domain: The business domain to search within
            names: List of entity names to look up

        Returns:
            Dict mapping entity name to Entity object for found entities.
            Entities not found are not included in the dict.
        """
        if not names:
            return {}
        placeholders = ",".join("?" * len(names))
        rows = await self._db.fetchall(
            f"SELECT id, name, type, description, attributes, domain, status, source, "
            f"created_at, updated_at FROM entities WHERE name IN ({placeholders}) AND domain = ?",
            tuple(names) + (domain,),
        )
        return {row[1]: _row_to_entity(row) for row in rows}

    async def find_duplicates(self) -> list[dict]:
        """查找所有重复实体（name+domain 组合出现多次的）。

        Returns:
            重复实体列表，每项包含 name, domain, count, ids
        """
        rows = await self._db.fetchall(
            """SELECT name, domain, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
               FROM entities
               GROUP BY LOWER(TRIM(name)), domain
               HAVING cnt > 1"""
        )
        return [
            {"name": r[0], "domain": r[1], "count": r[2], "ids": [int(x) for x in r[3].split(",")]}
            for r in rows
        ]

    async def merge_entities(self, keep_id: int, remove_ids: list[int]) -> Entity:
        """合并重复实体：保留 keep_id，删除 remove_ids，合并 attributes。

        Args:
            keep_id: 要保留的实体 ID
            remove_ids: 要删除的重复实体 ID 列表

        Returns:
            合并后的实体

        Raises:
            ValueError: 如果 keep_id 或 remove_ids 不存在
        """
        # 1. 验证实体存在
        keep_entity = await self.get(keep_id)
        if not keep_entity:
            raise ValueError(f"Entity {keep_id} not found")

        # 2. 获取所有要删除的实体
        remove_entities = []
        for eid in remove_ids:
            ent = await self.get(eid)
            if ent:
                remove_entities.append(ent)

        if not remove_entities:
            raise ValueError("No valid entities to merge")

        # 3. 合并 attributes（保留最早创建的为主，后续补充）
        merged_attrs = keep_entity.attributes or {}
        for ent in sorted(remove_entities, key=lambda e: e.created_at or ""):
            if ent.attributes:
                for k, v in ent.attributes.items():
                    if k not in merged_attrs:
                        merged_attrs[k] = v

        # 4. 更新保留实体的 attributes
        await self.update(keep_id, EntityUpdate(attributes=merged_attrs))

        # 5. 更新 relations 表中的引用
        for eid in remove_ids:
            await self._db.execute(
                "UPDATE relations SET source_entity_id = ? WHERE source_entity_id = ?",
                (keep_id, eid),
            )
            await self._db.execute(
                "UPDATE relations SET target_entity_id = ? WHERE target_entity_id = ?",
                (keep_id, eid),
            )

        # 6. 删除重复实体
        for eid in remove_ids:
            await self.delete(eid)

        # 7. 返回合并后的实体
        return await self.get(keep_id)  # type: ignore[return-value]

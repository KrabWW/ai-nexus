"""RuleRepo — rules 表单表 CRUD。"""

from __future__ import annotations

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import Rule, RuleCreate, RuleUpdate


def _row_to_rule(row: tuple[Any, ...]) -> Rule:
    return Rule(
        id=row[0],
        name=row[1],
        description=row[2],
        domain=row[3],
        severity=row[4],
        conditions=json.loads(row[5]) if row[5] else None,
        related_entity_ids=json.loads(row[6]) if row[6] else None,
        status=row[7],
        source=row[8],
        confidence=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


_SELECT = (
    "SELECT id, name, description, domain, severity, conditions, related_entity_ids, "
    "status, source, confidence, created_at, updated_at FROM rules"
)


class RuleRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: RuleCreate) -> Rule:
        cursor = await self._db.execute(
            "INSERT INTO rules (name, description, domain, severity, conditions, "
            "related_entity_ids, status, source, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.name,
                data.description,
                data.domain,
                data.severity,
                json.dumps(data.conditions) if data.conditions else None,
                json.dumps(data.related_entity_ids) if data.related_entity_ids else None,
                data.status,
                data.source,
                data.confidence,
            ),
        )
        return await self.get(cursor.lastrowid)  # type: ignore[arg-type]

    async def get(self, rule_id: int) -> Rule | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (rule_id,))
        return _row_to_rule(row) if row else None

    async def update(self, rule_id: int, data: RuleUpdate) -> Rule | None:
        fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if not fields:
            return await self.get(rule_id)
        for json_field in ("conditions", "related_entity_ids"):
            if json_field in fields and fields[json_field] is not None:
                fields[json_field] = json.dumps(fields[json_field])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [rule_id]
        await self._db.execute(
            f"UPDATE rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )
        return await self.get(rule_id)

    async def delete(self, rule_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return cursor.rowcount > 0

    async def list(
        self,
        domain: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Rule]:
        where_parts = []
        params: list[Any] = []
        if domain:
            where_parts.append("domain = ?")
            params.append(domain)
        if severity:
            where_parts.append("severity = ?")
            params.append(severity)
        if status:
            where_parts.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(limit)
        rows = await self._db.fetchall(f"{_SELECT} {where} LIMIT ?", tuple(params))
        return [_row_to_rule(r) for r in rows]

    async def search(
        self,
        keyword: str,
        domain: str | None = None,
        severity: str | None = None,
        limit: int = 10,
    ) -> list[Rule]:
        pattern = f"%{keyword}%"
        params: list[Any] = [pattern, pattern]
        extra = ""
        if domain:
            extra += " AND domain = ?"
            params.append(domain)
        if severity:
            extra += " AND severity = ?"
            params.append(severity)
        params.append(limit)
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE (name LIKE ? OR description LIKE ?){extra} LIMIT ?",
            tuple(params),
        )
        return [_row_to_rule(r) for r in rows]

    async def get_by_ids(self, ids: list[int]) -> list[Rule]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE id IN ({placeholders})", tuple(ids)
        )
        return [_row_to_rule(r) for r in rows]

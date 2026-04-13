"""AuditRepo — knowledge_audit_log 表 CRUD。"""

from __future__ import annotations

import json
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.audit import AuditLog, AuditLogCreate


def _row_to_log(row: tuple[Any, ...]) -> AuditLog:
    return AuditLog(
        id=row[0],
        table_name=row[1],
        record_id=row[2],
        action=row[3],
        old_value=json.loads(row[4]) if row[4] else None,
        new_value=json.loads(row[5]) if row[5] else None,
        reviewer=row[6],
        source_context=json.loads(row[7]) if row[7] else None,
        created_at=row[8],
    )


_SELECT = (
    "SELECT id, table_name, record_id, action, "
    "old_value, new_value, reviewer, source_context, created_at "
    "FROM knowledge_audit_log"
)


class AuditRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: AuditLogCreate) -> AuditLog:
        cursor = await self._db.execute(
            "INSERT INTO knowledge_audit_log "
            "(table_name, record_id, action, old_value, new_value, reviewer, source_context) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data.table_name,
                data.record_id,
                data.action,
                json.dumps(data.old_value) if data.old_value else None,
                json.dumps(data.new_value) if data.new_value else None,
                data.reviewer,
                json.dumps(data.source_context) if data.source_context else None,
            ),
        )
        log_id = cursor.lastrowid

        # Inject temp_id into new_value items for per-item review
        if data.new_value and isinstance(data.new_value, dict):
            new_value = data.new_value.copy()
            updated = False
            for key, items in [
                ("entities", new_value.get("entities", [])),
                ("relations", new_value.get("relations", [])),
                ("rules", new_value.get("rules", [])),
            ]:
                if isinstance(items, list):
                    for idx, item in enumerate(items):
                        if isinstance(item, dict) and "temp_id" not in item:
                            singular = {"entities": "entity", "rules": "rule", "relations": "relation"}.get(key, key)
                            item["temp_id"] = f"{log_id}_{singular}_{idx}"
                            updated = True
            if updated:
                await self._db.execute(
                    "UPDATE knowledge_audit_log SET new_value = ? WHERE id = ?",
                    (json.dumps(new_value), log_id),
                )

        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (log_id,))
        return _row_to_log(row)  # type: ignore[arg-type]

    async def list_by_record(self, table_name: str, record_id: int) -> list[AuditLog]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE table_name = ? AND record_id = ? ORDER BY created_at",
            (table_name, record_id),
        )
        return [_row_to_log(r) for r in rows]

    async def get_by_id(self, log_id: int) -> AuditLog | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (log_id,))
        return _row_to_log(row) if row else None

    async def list_pending(self) -> list[AuditLog]:
        """返回已提交但未审核（无 approve/reject 记录）的候选项最新提交记录。"""
        rows = await self._db.fetchall(
            f"""
            {_SELECT}
            WHERE action = 'submit_candidate'
              AND id NOT IN (
                SELECT record_id FROM knowledge_audit_log
                WHERE action IN ('approve', 'reject')
              )
            ORDER BY created_at DESC
            """
        )
        return [_row_to_log(r) for r in rows]

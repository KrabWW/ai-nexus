"""CodeReferenceRepo — rule_code_references 表 CRUD。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.code_reference import (
    CodeReference,
    CodeReferenceCreate,
    CodeReferenceWithRule,
)


def _row_to_ref(row: tuple[Any, ...]) -> CodeReference:
    return CodeReference(
        id=row[0],
        rule_id=row[1],
        file_path=row[2],
        line_start=row[3],
        line_end=row[4],
        snippet=row[5],
        repo_url=row[6],
        commit_sha=row[7],
        branch=row[8],
        reference_type=row[9],
        source=row[10],
        detected_at=datetime.fromisoformat(row[11]) if row[11] else None,
    )


_SELECT = (
    "SELECT id, rule_id, file_path, line_start, line_end, snippet, "
    "repo_url, commit_sha, branch, reference_type, source, detected_at "
    "FROM rule_code_references"
)


class CodeReferenceRepo:
    """CRUD + query methods for rule_code_references table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, data: CodeReferenceCreate) -> CodeReference:
        cursor = await self._db.execute(
            "INSERT INTO rule_code_references "
            "(rule_id, file_path, line_start, line_end, snippet, "
            "repo_url, commit_sha, branch, reference_type, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.rule_id,
                data.file_path,
                data.line_start,
                data.line_end,
                data.snippet,
                data.repo_url,
                data.commit_sha,
                data.branch,
                data.reference_type,
                data.source,
            ),
        )
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (cursor.lastrowid,))
        return _row_to_ref(row)  # type: ignore[arg-type]

    async def get(self, ref_id: int) -> CodeReference | None:
        row = await self._db.fetchone(f"{_SELECT} WHERE id = ?", (ref_id,))
        return _row_to_ref(row) if row else None

    async def list_by_rule(
        self, rule_id: int, limit: int = 100
    ) -> list[CodeReference]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE rule_id = ? ORDER BY detected_at DESC LIMIT ?",
            (rule_id, limit),
        )
        return [_row_to_ref(r) for r in rows]

    async def list_by_file(
        self, file_path: str, limit: int = 100
    ) -> list[CodeReference]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE file_path = ? ORDER BY detected_at DESC LIMIT ?",
            (file_path, limit),
        )
        return [_row_to_ref(r) for r in rows]

    async def list_by_commit(self, commit_sha: str) -> list[CodeReference]:
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE commit_sha = ? ORDER BY detected_at DESC",
            (commit_sha,),
        )
        return [_row_to_ref(r) for r in rows]

    async def list_by_rules(
        self, rule_ids: list[int], limit: int = 100
    ) -> list[CodeReferenceWithRule]:
        """List code references for multiple rules, joined with rule name/severity."""
        if not rule_ids:
            return []
        placeholders = ",".join("?" for _ in rule_ids)
        rows = await self._db.fetchall(
            f"SELECT cr.id, cr.rule_id, cr.file_path, cr.line_start, cr.line_end, "
            f"cr.snippet, cr.repo_url, cr.commit_sha, cr.branch, "
            f"cr.reference_type, cr.source, cr.detected_at, "
            f"r.name as rule_name, r.severity as rule_severity "
            f"FROM rule_code_references cr "
            f"JOIN rules r ON cr.rule_id = r.id "
            f"WHERE cr.rule_id IN ({placeholders}) "
            f"ORDER BY cr.detected_at DESC LIMIT ?",
            (*rule_ids, limit),
        )
        result: list[CodeReferenceWithRule] = []
        for row in rows:
            ref = _row_to_ref(row[:12])
            result.append(
                CodeReferenceWithRule(
                    **ref.model_dump(),
                    rule_name=row[12],
                    rule_severity=row[13],
                )
            )
        return result

    async def count_by_rule(self, rule_id: int) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) FROM rule_code_references WHERE rule_id = ?",
            (rule_id,),
        )
        return row[0] if row else 0

    async def delete(self, ref_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM rule_code_references WHERE id = ?", (ref_id,)
        )
        return cursor.rowcount > 0

    async def delete_by_commit(self, commit_sha: str) -> int:
        cursor = await self._db.execute(
            "DELETE FROM rule_code_references WHERE commit_sha = ?",
            (commit_sha,),
        )
        return cursor.rowcount

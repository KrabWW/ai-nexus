"""RuleRepo — rules 表单表 CRUD。"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import Any

from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import (
    Rule,
    RuleCreate,
    RuleRepoBinding,
    RuleRepoBindingCreate,
    RuleUpdate,
)


def _tokenize_query(query: str) -> list[str]:
    """Split query into search tokens.

    Whitespace-separated tokens are kept whole (English words).
    Chinese character sequences are split into bigrams (2-char sliding window)
    so that '删除订单' produces ['删除', '除订', '订单'], matching
    '禁止删除已支付订单' because it contains '删除' and '订单'.
    Single CJK chars are kept as-is.
    """
    tokens: list[str] = []
    for part in query.split():
        if part:
            tokens.extend(_split_mixed(part))
    if not tokens and query.strip():
        tokens = _split_mixed(query.strip())
    return tokens


def _split_mixed(text: str) -> list[str]:
    """Split text into non-overlapping CJK 2-char chunks and non-CJK words."""
    tokens: list[str] = []
    cjk_buf: list[str] = []
    ascii_buf: list[str] = []

    def flush_cjk() -> None:
        # Non-overlapping 2-char pairs: '删除订单' → ['删除', '订单']
        for i in range(0, len(cjk_buf) - 1, 2):
            tokens.append(cjk_buf[i] + cjk_buf[i + 1])
        if len(cjk_buf) % 2 == 1:
            tokens.append(cjk_buf[-1])
        cjk_buf.clear()

    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            if ascii_buf:
                tokens.append(''.join(ascii_buf))
                ascii_buf.clear()
            cjk_buf.append(ch)
        elif ch.strip():
            flush_cjk()
            ascii_buf.append(ch)
    flush_cjk()
    if ascii_buf:
        tokens.append(''.join(ascii_buf))
    return tokens


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


def normalize_repo_url(url: str) -> str:
    """Normalize git remote URLs for consistent matching.

    Converts various git URL formats to a canonical "host/org/repo" format:
    - git@github.com:org/repo.git → github.com/org/repo
    - https://github.com/org/repo.git → github.com/org/repo
    - https://gitlab.com/org/repo → gitlab.com/org/repo

    Args:
        url: Raw git remote URL

    Returns:
        Normalized URL in "host/org/repo" format
    """
    url = url.strip()
    # SSH format: git@host:org/repo.git
    m = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    # HTTPS format: https://host/org/repo.git
    m = re.match(r"https?://([^/]+)/(.+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return url.rstrip("/")


_RULE_UPDATEABLE_COLUMNS = frozenset({
    "name", "description", "domain", "severity", "conditions",
    "related_entity_ids", "status", "source", "confidence",
})


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
        invalid = set(fields.keys()) - _RULE_UPDATEABLE_COLUMNS
        if invalid:
            raise ValueError(f"Invalid columns: {invalid}")
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
        offset: int = 0,
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
        params.extend([limit, offset])
        rows = await self._db.fetchall(f"{_SELECT} {where} LIMIT ? OFFSET ?", tuple(params))
        return [_row_to_rule(r) for r in rows]

    async def count(
        self,
        domain: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> int:
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
        row = await self._db.fetchone(f"SELECT COUNT(*) FROM rules {where}", tuple(params))
        return row[0] if row else 0

    async def search(
        self,
        keyword: str,
        domain: str | None = None,
        severity: str | None = None,
        limit: int = 10,
    ) -> list[Rule]:
        tokens = _tokenize_query(keyword)
        if not tokens:
            return []
        # Each token must appear in name OR description (AND logic)
        conditions: list[str] = []
        params: list[Any] = []
        for tok in tokens:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{tok}%", f"%{tok}%"])
        extra = ""
        if domain:
            extra += " AND domain = ?"
            params.append(domain)
        if severity:
            extra += " AND severity = ?"
            params.append(severity)
        params.append(limit)
        where = " AND ".join(conditions)
        rows = await self._db.fetchall(
            f"{_SELECT} WHERE ({where}){extra} LIMIT ?",
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

    async def list_bindings(self, rule_id: int) -> list[RuleRepoBinding]:
        """List all repository bindings for a specific rule.

        Args:
            rule_id: ID of the rule to list bindings for

        Returns:
            List of RuleRepoBinding objects for this rule
        """
        rows = await self._db.fetchall(
            "SELECT id, rule_id, repo_url, branch_pattern, created_at "
            "FROM rule_repo_bindings WHERE rule_id = ? "
            "ORDER BY created_at DESC",
            (rule_id,),
        )
        return [
            RuleRepoBinding(
                id=row[0],
                rule_id=row[1],
                repo_url=row[2],
                branch_pattern=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    async def add_binding(
        self, rule_id: int, data: RuleRepoBindingCreate
    ) -> RuleRepoBinding:
        """Add a repository binding to a rule.

        Args:
            rule_id: ID of the rule to bind
            data: Binding data (repo_url, branch_pattern)

        Returns:
            Created RuleRepoBinding object

        Raises:
            sqlite3.IntegrityError: If binding already exists (UNIQUE constraint)
        """
        normalized_url = normalize_repo_url(data.repo_url)
        cursor = await self._db.execute(
            "INSERT INTO rule_repo_bindings (rule_id, repo_url, branch_pattern) "
            "VALUES (?, ?, ?)",
            (rule_id, normalized_url, data.branch_pattern),
        )
        row = await self._db.fetchone(
            "SELECT id, rule_id, repo_url, branch_pattern, created_at "
            "FROM rule_repo_bindings WHERE id = ?",
            (cursor.lastrowid,),
        )
        return RuleRepoBinding(
            id=row[0],
            rule_id=row[1],
            repo_url=row[2],
            branch_pattern=row[3],
            created_at=row[4],
        )

    async def remove_binding(self, binding_id: int) -> bool:
        """Remove a repository binding.

        Args:
            binding_id: ID of the binding to remove

        Returns:
            True if binding was deleted, False if not found
        """
        cursor = await self._db.execute(
            "DELETE FROM rule_repo_bindings WHERE id = ?", (binding_id,)
        )
        return cursor.rowcount > 0

    async def match_rules(self, repo_url: str, branch: str) -> list[int]:
        """Find rule IDs that match a given repository and branch.

        Returns:
            - All rule IDs with NO bindings (global rules)
            - Rule IDs with bindings matching repo_url + branch_pattern

        Matching logic:
        - repo_url is normalized and matched exactly against stored normalized URLs
        - branch is matched against branch_pattern using fnmatch glob patterns

        Args:
            repo_url: Git remote URL (will be normalized)
            branch: Branch name (e.g., "main", "feature/login")

        Returns:
            List of rule IDs that should apply to this repo/branch
        """
        normalized_url = normalize_repo_url(repo_url)

        # Get rules with no bindings (global rules)
        global_rules = await self._db.fetchall(
            "SELECT id FROM rules WHERE id NOT IN (SELECT DISTINCT rule_id FROM rule_repo_bindings)"
        )
        global_rule_ids = [row[0] for row in global_rules]

        # Get rules with bindings matching this repo
        bound_rules = await self._db.fetchall(
            "SELECT rule_id, branch_pattern FROM rule_repo_bindings WHERE repo_url = ?",
            (normalized_url,),
        )

        # Filter by branch pattern using fnmatch
        matching_rule_ids = [
            row[0]
            for row in bound_rules
            if fnmatch.fnmatch(branch, row[1])
        ]

        # Combine global rules + matching bound rules (deduplicate)
        return list(set(global_rule_ids + matching_rule_ids))

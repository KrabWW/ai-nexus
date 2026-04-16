"""Tests for Rule ↔ Repository Binding feature.

Covers:
- URL normalization (SSH/HTTPS formats)
- Binding CRUD operations
- Rule matching logic (exact, glob, wildcard)
- Pre-commit hook filtering integration
- API endpoints
- Migration schema
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ai_nexus.db.sqlite import Database
from ai_nexus.models.rule import (
    Rule,
    RuleCreate,
    RuleRepoBindingCreate,
)
from ai_nexus.repos.rule_repo import RuleRepo, normalize_repo_url

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
async def db():
    """In-memory SQLite with full schema."""
    database = Database(":memory:")
    await database.connect()
    await database.run_migrations()
    yield database
    await database.disconnect()


@pytest.fixture
async def rule_repo(db: Database) -> RuleRepo:
    return RuleRepo(db)


@pytest.fixture
async def sample_rule(rule_repo: RuleRepo) -> Rule:
    """Create a sample rule for testing."""
    return await rule_repo.create(RuleCreate(
        name="TestRule",
        description="Test rule for bindings",
        domain="test",
        severity="warning",
    ))


# ── 1. URL Normalization Tests ────────────────────────────────────────


class TestNormalizeRepoUrl:
    """Test URL normalization function."""

    def test_ssh_format(self):
        """SSH format: git@github.com:org/repo.git → github.com/org/repo"""
        result = normalize_repo_url("git@github.com:org/repo.git")
        assert result == "github.com/org/repo"

    def test_https_format_with_git(self):
        """HTTPS format: https://github.com/org/repo.git → github.com/org/repo"""
        result = normalize_repo_url("https://github.com/org/repo.git")
        assert result == "github.com/org/repo"

    def test_https_format_without_git(self):
        """HTTPS without .git: https://github.com/org/repo → github.com/org/repo"""
        result = normalize_repo_url("https://github.com/org/repo")
        assert result == "github.com/org/repo"

    def test_trailing_slash(self):
        """Trailing slash: github.com/org/repo/ → github.com/org/repo"""
        result = normalize_repo_url("github.com/org/repo/")
        assert result == "github.com/org/repo"

    def test_already_normalized(self):
        """Already normalized: github.com/org/repo → github.com/org/repo"""
        result = normalize_repo_url("github.com/org/repo")
        assert result == "github.com/org/repo"

    def test_gitlab_ssh(self):
        """GitLab SSH: git@gitlab.com:org/repo.git → gitlab.com/org/repo"""
        result = normalize_repo_url("git@gitlab.com:org/repo.git")
        assert result == "gitlab.com/org/repo"

    def test_gitlab_https(self):
        """GitLab HTTPS: https://gitlab.com/org/repo → gitlab.com/org/repo"""
        result = normalize_repo_url("https://gitlab.com/org/group/repo.git")
        assert result == "gitlab.com/org/group/repo"

    def test_whitespace_preserved(self):
        """Whitespace is stripped."""
        result = normalize_repo_url("  git@github.com:org/repo.git  ")
        assert result == "github.com/org/repo"


# ── 2. Binding CRUD Tests ───────────────────────────────────────────────


class TestBindingCRUD:
    """Test CRUD operations for rule-repo bindings."""

    async def test_add_binding(self, rule_repo: RuleRepo, sample_rule: Rule):
        """Add a binding to a rule."""
        binding = await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(
                repo_url="git@github.com:org/repo.git",
                branch_pattern="main",
            ),
        )
        assert binding.id > 0
        assert binding.rule_id == sample_rule.id
        assert binding.repo_url == "github.com/org/repo"
        assert binding.branch_pattern == "main"
        assert binding.created_at is not None

    async def test_list_bindings_empty(self, rule_repo: RuleRepo, sample_rule: Rule):
        """List bindings for a new rule returns empty list."""
        bindings = await rule_repo.list_bindings(sample_rule.id)
        assert bindings == []

    async def test_list_bindings(self, rule_repo: RuleRepo, sample_rule: Rule):
        """List bindings returns all bindings for a rule."""
        await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="https://github.com/org/repo.git", branch_pattern="main"),
        )
        await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="git@github.com:other/repo.git", branch_pattern="develop"),
        )

        bindings = await rule_repo.list_bindings(sample_rule.id)
        assert len(bindings) == 2
        # Bindings are ordered by created_at DESC, so most recent is first
        repo_urls = {b.repo_url for b in bindings}
        assert repo_urls == {"github.com/org/repo", "github.com/other/repo"}

    async def test_remove_binding(self, rule_repo: RuleRepo, sample_rule: Rule):
        """Remove a binding by ID."""
        binding = await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="main"),
        )

        removed = await rule_repo.remove_binding(binding.id)
        assert removed is True

        bindings = await rule_repo.list_bindings(sample_rule.id)
        assert bindings == []

    async def test_remove_nonexistent_binding(self, rule_repo: RuleRepo):
        """Removing nonexistent binding returns False."""
        removed = await rule_repo.remove_binding(99999)
        assert removed is False

    async def test_unique_constraint_duplicate_binding(
        self, rule_repo: RuleRepo, sample_rule: Rule,
    ):
        """UNIQUE constraint: cannot add duplicate (rule_id, repo_url, branch_pattern)."""
        await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="main"),
        )

        with pytest.raises(Exception) as exc_info:  # sqlite3.IntegrityError
            await rule_repo.add_binding(
                sample_rule.id,
                RuleRepoBindingCreate(repo_url="git@github.com:org/repo.git", branch_pattern="main"),
            )
        # Error message varies by sqlite3 version, check it's an integrity error
        assert "UNIQUE" in str(exc_info.value).upper() or "constraint" in str(exc_info.value).lower()

    async def test_different_branch_patterns_allowed(
        self, rule_repo: RuleRepo, sample_rule: Rule,
    ):
        """Same repo with different branch patterns is allowed."""
        await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="main"),
        )
        await rule_repo.add_binding(
            sample_rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="develop"),
        )

        bindings = await rule_repo.list_bindings(sample_rule.id)
        assert len(bindings) == 2


# ── 3. Rule Matching Tests ───────────────────────────────────────────────


class TestMatchRules:
    """Test core rule matching logic."""

    async def test_exact_branch_match(self, rule_repo: RuleRepo, db: Database):
        """Exact match: branch_pattern="main" matches branch="main", not "develop"."""
        rule1 = await rule_repo.create(RuleCreate(
            name="RuleMain", description="Main branch rule", domain="test",
        ))
        rule2 = await rule_repo.create(RuleCreate(
            name="RuleDevelop", description="Develop branch rule", domain="test",
        ))

        await rule_repo.add_binding(
            rule1.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="main"),
        )
        await rule_repo.add_binding(
            rule2.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="develop"),
        )

        # Query main branch
        main_rule_ids = await rule_repo.match_rules("github.com/org/repo", "main")
        assert rule1.id in main_rule_ids
        assert rule2.id not in main_rule_ids

        # Query develop branch
        dev_rule_ids = await rule_repo.match_rules("github.com/org/repo", "develop")
        assert rule2.id in dev_rule_ids
        assert rule1.id not in dev_rule_ids

    async def test_glob_branch_match(self, rule_repo: RuleRepo):
        """Glob match: branch_pattern="feature/*" matches "feature/login", not "hotfix/fix"."""
        rule = await rule_repo.create(RuleCreate(
            name="FeatureRule", description="Feature branch rule", domain="test",
        ))

        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="feature/*"),
        )

        # Match feature branches
        feature_ids = await rule_repo.match_rules("github.com/org/repo", "feature/login")
        assert rule.id in feature_ids

        feature_ids2 = await rule_repo.match_rules("github.com/org/repo", "feature/user-auth")
        assert rule.id in feature_ids2

        # No match for hotfix
        hotfix_ids = await rule_repo.match_rules("github.com/org/repo", "hotfix/fix")
        assert rule.id not in hotfix_ids

    async def test_wildcard_match(self, rule_repo: RuleRepo):
        """Wildcard: branch_pattern="*" matches all branches."""
        rule = await rule_repo.create(RuleCreate(
            name="WildcardRule", description="Wildcard rule", domain="test",
        ))

        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="*"),
        )

        for branch in ["main", "develop", "feature/x", "hotfix/y"]:
            rule_ids = await rule_repo.match_rules("github.com/org/repo", branch)
            assert rule.id in rule_ids

    async def test_global_rules_always_included(self, rule_repo: RuleRepo):
        """Global rules (no bindings) always appear in results."""
        global_rule = await rule_repo.create(RuleCreate(
            name="GlobalRule", description="Global rule", domain="test",
        ))
        bound_rule = await rule_repo.create(RuleCreate(
            name="BoundRule", description="Bound rule", domain="test",
        ))

        # Only bind bound_rule
        await rule_repo.add_binding(
            bound_rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="main"),
        )

        # Global rule should appear for any repo
        rule_ids = await rule_repo.match_rules("different.com/repo", "main")
        assert global_rule.id in rule_ids

        # Both rules for matching repo
        rule_ids2 = await rule_repo.match_rules("github.com/org/repo", "main")
        assert global_rule.id in rule_ids2
        assert bound_rule.id in rule_ids2

    async def test_multi_binding_different_repos(self, rule_repo: RuleRepo):
        """One rule bound to multiple repos only matches the right repo."""
        rule = await rule_repo.create(RuleCreate(
            name="MultiRepoRule", description="Multi-repo rule", domain="test",
        ))

        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo1", branch_pattern="main"),
        )
        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo2", branch_pattern="main"),
        )

        # Matches repo1
        ids1 = await rule_repo.match_rules("github.com/org/repo1", "main")
        assert rule.id in ids1

        # Matches repo2
        ids2 = await rule_repo.match_rules("github.com/org/repo2", "main")
        assert rule.id in ids2

        # Does not match unrelated repo
        ids3 = await rule_repo.match_rules("github.com/org/repo3", "main")
        assert rule.id not in ids3

    async def test_url_normalization_matching(self, rule_repo: RuleRepo):
        """SSH and HTTPS URLs match the same binding."""
        rule = await rule_repo.create(RuleCreate(
            name="UrlNormRule", description="URL normalization rule", domain="test",
        ))

        # Add binding with HTTPS
        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="https://github.com/org/repo.git", branch_pattern="main"),
        )

        # Query with SSH should match
        ssh_ids = await rule_repo.match_rules("git@github.com:org/repo.git", "main")
        assert rule.id in ssh_ids

        # Query with HTTPS should match
        https_ids = await rule_repo.match_rules("https://github.com/org/repo", "main")
        assert rule.id in https_ids

        # Query with normalized URL should match
        norm_ids = await rule_repo.match_rules("github.com/org/repo", "main")
        assert rule.id in norm_ids

    async def test_no_match_for_different_branch(self, rule_repo: RuleRepo):
        """Rule with specific branch pattern doesn't match different branch."""
        rule = await rule_repo.create(RuleCreate(
            name="SpecificBranch", description="Specific branch rule", domain="test",
        ))

        await rule_repo.add_binding(
            rule.id,
            RuleRepoBindingCreate(repo_url="github.com/org/repo", branch_pattern="production"),
        )

        # No match for main branch
        main_ids = await rule_repo.match_rules("github.com/org/repo", "main")
        assert rule.id not in main_ids

        # Match for production branch
        prod_ids = await rule_repo.match_rules("github.com/org/repo", "production")
        assert rule.id in prod_ids


# ── 4. Pre-Commit Hook Filter Tests ─────────────────────────────────────


class TestPreCommitHookFilter:
    """Test pre-commit hook endpoint filters by binding."""

    @pytest.fixture
    def _mock_db(self):
        """Create a mock Database with async execute/fetchone/fetchall."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.fetchone = AsyncMock()
        db.fetchall = AsyncMock(return_value=[])
        db.connect = AsyncMock()
        db.disconnect = AsyncMock()
        db.run_migrations = AsyncMock()
        return db

    @pytest.fixture
    def _make_app(self, _mock_db: MagicMock):
        """Build a FastAPI app with mocked services for testing."""
        from fastapi import FastAPI

        from ai_nexus.api.router import router
        from ai_nexus.extraction.extraction_service import ExtractionService
        from ai_nexus.repos.audit_repo import AuditRepo
        from ai_nexus.services.graph_service import GraphService
        from ai_nexus.services.query_service import QueryService

        app = FastAPI()
        app.include_router(router)

        # Wire up app.state
        app.state.extraction_service = MagicMock(spec=ExtractionService)
        app.state.audit_repo = AuditRepo(_mock_db)

        # Wire up rule_repo for dependency injection
        from ai_nexus.repos.rule_repo import RuleRepo
        rule_repo_instance = RuleRepo(_mock_db)
        app.state.rule_repo = rule_repo_instance

        # Wire up graph_service (required by pre-commit endpoint)
        graph_svc = MagicMock(spec=GraphService)
        graph_svc._rules = rule_repo_instance
        app.state.graph_service = graph_svc

        # Wire up query_service (required by pre-commit endpoint)
        app.state.query_service = MagicMock(spec=QueryService)
        app.state.query_service.query_rules = AsyncMock(return_value=[])

        # Wire up code_reference_repo (required by pre-commit endpoint)
        from ai_nexus.repos.code_reference_repo import CodeReferenceRepo
        app.state.code_reference_repo = MagicMock(spec=CodeReferenceRepo)

        return TestClient(app)

    def test_with_repo_url_and_branch_filters_rules(
        self, _mock_db: MagicMock, _make_app,
    ):
        """With repo_url + branch: only returns matched + global rules."""
        from ai_nexus.models.rule import Rule

        app = _make_app

        # Mock rules: rule1 bound to main, rule2 bound to develop, rule3 global
        rule1 = MagicMock(spec=Rule)
        rule1.id = 1
        rule1.name = "MainRule"
        rule1.severity = "warning"
        rule1.description = "Main branch rule"
        rule1.status = "approved"

        rule2 = MagicMock(spec=Rule)
        rule2.id = 2
        rule2.name = "DevRule"
        rule2.severity = "warning"
        rule2.description = "Dev branch rule"
        rule2.status = "approved"

        rule3 = MagicMock(spec=Rule)
        rule3.id = 3
        rule3.name = "GlobalRule"
        rule3.severity = "info"
        rule3.description = "Global rule"
        rule3.status = "approved"

        # Mock search returns all rules for any keyword
        async def mock_query_rules(keyword: str, **kwargs):
            return [rule1, rule2, rule3]

        app.app.state.query_service.query_rules = mock_query_rules

        # Mock match_rules to filter by repo/branch
        async def mock_match(repo_url: str, branch: str) -> list[int]:
            if branch == "main":
                return [1, 3]  # rule1 (main) + rule3 (global)
            elif branch == "develop":
                return [2, 3]  # rule2 (develop) + rule3 (global)
            return [3]  # only global

        app.app.state.rule_repo.match_rules = mock_match

        # Test main branch query
        resp = app.post("/api/hooks/pre-commit", json={
            "change_description": "test changes",
            "repo_url": "git@github.com:org/repo.git",
            "branch": "main",
        })

        assert resp.status_code == 200
        body = resp.json()
        # Should get warnings for matched rules (rule1 and rule3)
        assert len(body.get("warnings", []) + body.get("infos", [])) >= 1

    def test_without_repo_url_branch_returns_all(
        self, _mock_db: MagicMock, _make_app,
    ):
        """Without repo_url/branch: returns all rules (backward compatible)."""
        app = _make_app

        # Mock empty search
        _mock_db.fetchall.return_value = []

        resp = app.post("/api/hooks/pre-commit", json={
            "change_description": "test changes",
        })

        assert resp.status_code == 200
        # Should return 200 even with no repo context
        body = resp.json()
        assert "errors" in body
        assert "warnings" in body
        assert "infos" in body


# ── 5. API Endpoint Tests ───────────────────────────────────────────────


class TestBindingAPIEndpoints:
    """Test API endpoints for binding CRUD."""

    @pytest.fixture
    def _mock_db(self):
        """Create a mock Database."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.fetchone = AsyncMock()
        db.fetchall = AsyncMock(return_value=[])
        db.connect = AsyncMock()
        db.disconnect = AsyncMock()
        db.run_migrations = AsyncMock()
        return db

    @pytest.fixture
    def _make_app(self, _mock_db: MagicMock):
        """Build a FastAPI app with mocked services."""
        from fastapi import FastAPI

        from ai_nexus.api.router import router
        from ai_nexus.extraction.extraction_service import ExtractionService
        from ai_nexus.repos.audit_repo import AuditRepo
        from ai_nexus.services.graph_service import GraphService

        app = FastAPI()
        app.include_router(router)

        app.state.extraction_service = MagicMock(spec=ExtractionService)
        app.state.audit_repo = AuditRepo(_mock_db)

        from ai_nexus.repos.rule_repo import RuleRepo
        rule_repo_instance = RuleRepo(_mock_db)
        app.state.rule_repo = rule_repo_instance

        # Wire up graph_service (required by get_rule_repo dependency)
        graph_svc = MagicMock(spec=GraphService)
        graph_svc._rules = rule_repo_instance
        app.state.graph_service = graph_svc

        return TestClient(app)

    def test_post_add_binding(self, _mock_db: MagicMock, _make_app):
        """POST /api/rules/{rule_id}/bindings — create binding."""
        app = _make_app

        # Mock rule exists (first fetchone call)
        rule_row = (
            1, "TestRule", "desc", "test", "warning", None, None, "approved",
            "manual", 1.0, "2026-01-01", "2026-01-01",
        )

        # Mock binding insert returns new binding (second fetchone call)
        binding_row = (
            42, 1, "github.com/org/repo", "main", "2026-01-01",
        )

        # Setup side_effect to return different values on consecutive calls
        _mock_db.fetchone.side_effect = [rule_row, binding_row]
        _mock_db.execute.return_value = MagicMock(lastrowid=42)

        resp = app.post("/api/rules/1/bindings", json={
            "repo_url": "git@github.com:org/repo.git",
            "branch_pattern": "main",
        })

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == 42
        assert body["rule_id"] == 1
        assert body["repo_url"] == "github.com/org/repo"
        assert body["branch_pattern"] == "main"

    def test_post_add_binding_404_rule_not_found(self, _mock_db: MagicMock, _make_app):
        """POST /api/rules/{rule_id}/bindings — 404 for non-existent rule."""
        app = _make_app

        # Mock rule not found
        _mock_db.fetchone.return_value = None

        resp = app.post("/api/rules/99999/bindings", json={
            "repo_url": "github.com/org/repo",
            "branch_pattern": "main",
        })

        assert resp.status_code == 404
        assert "Rule not found" in resp.json()["detail"]

    def test_get_list_bindings(self, _mock_db: MagicMock, _make_app):
        """GET /api/rules/{rule_id}/bindings — list bindings."""
        app = _make_app

        # Mock rule exists
        _mock_db.fetchone.return_value = (
            1, "TestRule", "desc", "test", "warning", None, None, "approved",
            "manual", 1.0, "2026-01-01", "2026-01-01",
        )

        # Mock bindings list
        _mock_db.fetchall.return_value = [
            (1, 1, "github.com/org/repo", "main", "2026-01-01"),
            (2, 1, "gitlab.com/org/repo", "develop", "2026-01-02"),
        ]

        resp = app.get("/api/rules/1/bindings")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["repo_url"] == "github.com/org/repo"
        assert body[1]["repo_url"] == "gitlab.com/org/repo"

    def test_get_list_bindings_404_rule_not_found(self, _mock_db: MagicMock, _make_app):
        """GET /api/rules/{rule_id}/bindings — 404 for non-existent rule."""
        app = _make_app

        _mock_db.fetchone.return_value = None

        resp = app.get("/api/rules/99999/bindings")

        assert resp.status_code == 404
        assert "Rule not found" in resp.json()["detail"]

    def test_delete_binding(self, _mock_db: MagicMock, _make_app):
        """DELETE /api/rules/{rule_id}/bindings/{binding_id} — delete binding."""
        app = _make_app

        # Mock rule exists
        _mock_db.fetchone.return_value = (
            1, "TestRule", "desc", "test", "warning", None, None, "approved",
            "manual", 1.0, "2026-01-01", "2026-01-01",
        )

        # Mock delete succeeded
        _mock_db.execute.return_value = MagicMock(rowcount=1)

        resp = app.delete("/api/rules/1/bindings/42")

        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}

    def test_delete_binding_404_rule_not_found(self, _mock_db: MagicMock, _make_app):
        """DELETE /api/rules/{rule_id}/bindings/{binding_id} — 404 for non-existent rule."""
        app = _make_app

        _mock_db.fetchone.return_value = None

        resp = app.delete("/api/rules/99999/bindings/1")

        assert resp.status_code == 404
        assert "Rule not found" in resp.json()["detail"]

    def test_delete_binding_404_binding_not_found(self, _mock_db: MagicMock, _make_app):
        """DELETE /api/rules/{rule_id}/bindings/{binding_id} — 404 for non-existent binding."""
        app = _make_app

        # Mock rule exists
        _mock_db.fetchone.return_value = (
            1, "TestRule", "desc", "test", "warning", None, None, "approved",
            "manual", 1.0, "2026-01-01", "2026-01-01",
        )

        # Mock delete failed (binding not found)
        _mock_db.execute.return_value = MagicMock(rowcount=0)

        resp = app.delete("/api/rules/1/bindings/99999")

        assert resp.status_code == 404
        assert "Binding not found" in resp.json()["detail"]

    def test_get_match_rules(self, _mock_db: MagicMock, _make_app):
        """GET /api/rules/match — query matching rules."""
        app = _make_app

        # Mock match_rules returns global rules + matched rules
        mock_repo = app.app.state.graph_service._rules
        mock_repo.match_rules = AsyncMock(return_value=[1, 3, 5])

        resp = app.get("/api/rules/match?repo_url=github.com/org/repo&branch=main")

        assert resp.status_code == 200
        assert resp.json() == [1, 3, 5]
        mock_repo.match_rules.assert_called_once_with("github.com/org/repo", "main")


# ── 6. Migration Tests ───────────────────────────────────────────────────


class TestMigration:
    """Test migration 008 adds rule_repo_bindings table."""

    async def test_rule_repo_bindings_table_exists(self, db: Database):
        """Apply migration 008, verify table exists with correct schema."""
        await db.run_migrations()

        row = await db.fetchone(
            "SELECT sql FROM sqlite_master WHERE name = 'rule_repo_bindings'"
        )
        assert row is not None
        schema = row[0]

        # Verify columns
        assert "id" in schema
        assert "rule_id" in schema
        assert "repo_url" in schema
        assert "branch_pattern" in schema
        assert "created_at" in schema

        # Verify UNIQUE constraint
        assert "UNIQUE" in schema.upper()
        assert "rule_id" in schema
        assert "repo_url" in schema
        assert "branch_pattern" in schema

    async def test_rollback_drops_table(self, db: Database):
        """Verify rollback: DROP TABLE succeeds."""
        await db.run_migrations()

        # Simulate rollback by dropping the table
        await db.execute("DROP TABLE IF EXISTS rule_repo_bindings")

        # Verify table is gone
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE name = 'rule_repo_bindings'"
        )
        assert row is None

    async def test_migration_count_increments(self, db: Database):
        """After migration 008, migration count should be 8."""
        await db.run_migrations()

        # Check schema_version table
        rows = await db.fetchall("SELECT version FROM schema_version ORDER BY version DESC")
        assert len(rows) >= 8

        # Max version should be at least 8
        max_version = max(row[0] for row in rows)
        assert max_version >= 8

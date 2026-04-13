"""Tests for Audit Workflow Redesign (Steps 1-7).

Covers:
- source_context storage and retrieval
- temp_id format and injection
- Per-item approval via ingest_candidate approved_temp_ids
- Conflict detection
- Backward compatibility
- IngestService audit path (feishu + document)
- Migration apply/rollback
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_nexus.db.sqlite import Database
from ai_nexus.models.audit import ApproveRequest, AuditLogCreate, ItemAction
from ai_nexus.models.extraction import (
    ExtractedEntity,
    ExtractedRule,
    ExtractionResult,
)
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.services.extraction_service import ExtractionService
from ai_nexus.services.ingest_service import IngestService

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
async def audit_repo(db: Database) -> AuditRepo:
    return AuditRepo(db)


def _make_entity(name: str = "TestEntity", domain: str = "test", **kw) -> dict:
    return {"name": name, "type": "概念", "domain": domain, "confidence": 0.8,
            "source_type": "extracted", "description": f"desc for {name}", **kw}


def _make_rule(name: str = "TestRule", domain: str = "test", **kw) -> dict:
    return {"name": name, "severity": "warning", "domain": domain,
            "confidence": 0.7, "source_type": "inferred", "description": f"desc for {name}", **kw}


def _make_relation(source: str = "A", target: str = "B", domain: str = "test") -> dict:
    return {"name": f"{source} → depends_on → {target}", "type": "depends_on",
            "domain": domain, "source_name": source, "source_domain": domain,
            "target_name": target, "target_domain": domain, "relation_type": "depends_on",
            "confidence": 0.6, "source_type": "inferred", "description": ""}


# ── 1. source_context tests ──────────────────────────────────────────


class TestSourceContext:
    """Verify source_context is stored and retrievable for each path."""

    async def test_source_context_stored(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction",
            record_id=0,
            action="submit_candidate",
            new_value={"entities": [_make_entity()], "rules": [], "relations": []},
            source_context={
                "source_type": "post_task",
                "task_description": "implement refund",
                "original_text": "some text",
            },
        ))
        assert log.source_context is not None
        assert log.source_context["source_type"] == "post_task"
        assert log.source_context["task_description"] == "implement refund"

    async def test_source_context_none_when_absent(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="rules", record_id=1, action="create",
            new_value={"name": "R1"},
        ))
        assert log.source_context is None

    async def test_source_context_cold_start(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={"entities": [], "rules": [], "relations": []},
            source_context={"source_type": "cold_start", "domain": "payment"},
        ))
        fetched = await audit_repo.get_by_id(log.id)
        assert fetched is not None
        assert fetched.source_context["source_type"] == "cold_start"
        assert fetched.source_context["domain"] == "payment"

    async def test_source_context_manual(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="temp_entity", record_id=42, action="submit_candidate",
            new_value={"name": "X", "_meta": {"source": "manual"}},
            source_context={"source_type": "manual"},
        ))
        fetched = await audit_repo.get_by_id(log.id)
        assert fetched.source_context["source_type"] == "manual"


# ── 2. temp_id format + prefix validation ────────────────────────────


class TestTempId:
    """Verify temp_id injection by AuditRepo.create()."""

    async def test_temp_id_injected_for_entities(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={
                "entities": [_make_entity("E1"), _make_entity("E2")],
                "rules": [], "relations": [],
            },
        ))
        entities = log.new_value["entities"]
        assert entities[0]["temp_id"] == f"{log.id}_entity_0"
        assert entities[1]["temp_id"] == f"{log.id}_entity_1"

    async def test_temp_id_injected_for_rules(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={
                "entities": [],
                "rules": [_make_rule("R1"), _make_rule("R2")],
                "relations": [],
            },
        ))
        rules = log.new_value["rules"]
        assert rules[0]["temp_id"] == f"{log.id}_rule_0"
        assert rules[1]["temp_id"] == f"{log.id}_rule_1"

    async def test_temp_id_injected_for_relations(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={
                "entities": [],
                "rules": [],
                "relations": [_make_relation()],
            },
        ))
        relations = log.new_value["relations"]
        assert relations[0]["temp_id"] == f"{log.id}_relation_0"

    async def test_temp_id_mixed_types(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={
                "entities": [_make_entity()],
                "rules": [_make_rule()],
                "relations": [_make_relation()],
            },
        ))
        nv = log.new_value
        assert nv["entities"][0]["temp_id"] == f"{log.id}_entity_0"
        assert nv["rules"][0]["temp_id"] == f"{log.id}_rule_0"
        assert nv["relations"][0]["temp_id"] == f"{log.id}_relation_0"

    async def test_temp_id_not_overwritten_if_present(self, audit_repo: AuditRepo):
        entity = _make_entity()
        entity["temp_id"] = "custom_id_99"
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={"entities": [entity], "rules": [], "relations": []},
        ))
        # Repo should NOT overwrite an existing temp_id
        assert log.new_value["entities"][0]["temp_id"] == "custom_id_99"

    async def test_no_temp_id_when_new_value_has_no_lists(self, audit_repo: AuditRepo):
        log = await audit_repo.create(AuditLogCreate(
            table_name="rules", record_id=1, action="create",
            new_value={"name": "simple"},
        ))
        assert log.new_value == {"name": "simple"}


# ── 3. ingest_candidate filtering (per-item approval at service level) ──


class TestIngestCandidateFiltering:
    """Test ExtractionService.ingest_candidate with approved_temp_ids."""

    @pytest.fixture
    def extraction_service(self) -> ExtractionService:
        entity_repo = MagicMock()
        entity_repo.create = AsyncMock(return_value=MagicMock(id=1))
        entity_repo.search = AsyncMock(return_value=[])
        entity_repo.update = AsyncMock()

        rule_repo = MagicMock()
        rule_repo.create = AsyncMock(return_value=MagicMock(id=1))
        rule_repo.search = AsyncMock(return_value=[])
        rule_repo.update = AsyncMock()

        relation_repo = MagicMock()
        relation_repo.create = AsyncMock(return_value=MagicMock(id=1))

        # Mock db for transaction
        mock_db = MagicMock()
        mock_db.transaction = MagicMock()
        mock_db.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_db.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
        entity_repo._db = mock_db

        svc = ExtractionService.__new__(ExtractionService)
        svc._api_key = "test"
        svc._base_url = None
        svc._model = "test"
        svc._entity_repo = entity_repo
        svc._rule_repo = rule_repo
        svc._relation_repo = relation_repo
        return svc

    async def test_full_approval_all_items(self, extraction_service: ExtractionService):
        data = {
            "entities": [_make_entity()], "rules": [_make_rule()],
            "relations": [], "source_metadata": None,
        }
        result = await extraction_service.ingest_candidate(data, approved_temp_ids=None)
        assert result["entities_created"] == 1
        assert result["rules_created"] == 1

    async def test_partial_approval_entity_approved_rule_rejected(
        self, extraction_service: ExtractionService,
    ):
        data = {
            "entities": [{**_make_entity(), "temp_id": "1_entity_0"}],
            "rules": [{**_make_rule(), "temp_id": "1_rule_0"}],
            "relations": [],
            "source_metadata": None,
        }
        result = await extraction_service.ingest_candidate(
            data, approved_temp_ids={"1_entity_0"},
        )
        assert result["entities_created"] == 1
        assert result["rules_created"] == 0

    async def test_all_rejected(self, extraction_service: ExtractionService):
        data = {
            "entities": [{**_make_entity(), "temp_id": "1_entity_0"}],
            "rules": [{**_make_rule(), "temp_id": "1_rule_0"}],
            "relations": [],
            "source_metadata": None,
        }
        result = await extraction_service.ingest_candidate(
            data, approved_temp_ids=set(),
        )
        assert result["entities_created"] == 0
        assert result["rules_created"] == 0

    async def test_items_without_temp_id_pass_through_when_filtering(
        self, extraction_service: ExtractionService,
    ):
        """Items without temp_id are included by default (backward compat)."""
        data = {
            "entities": [_make_entity()],  # no temp_id
            "rules": [{**_make_rule(), "temp_id": "1_rule_0"}],
            "relations": [],
            "source_metadata": None,
        }
        result = await extraction_service.ingest_candidate(
            data, approved_temp_ids=set(),
        )
        # Entity without temp_id passes through even with empty approved set
        assert result["entities_created"] == 1
        # Rule with temp_id not in set is filtered out
        assert result["rules_created"] == 0

    async def test_backward_compat_no_filter(self, extraction_service: ExtractionService):
        """None means approve all — backward compat."""
        data = {
            "entities": [_make_entity()],
            "rules": [_make_rule()],
            "relations": [],
            "source_metadata": None,
        }
        result = await extraction_service.ingest_candidate(data, approved_temp_ids=None)
        assert result["entities_created"] == 1
        assert result["rules_created"] == 1


# ── 4. Conflict detection ────────────────────────────────────────────


class TestConflictDetection:
    """Test ExtractionService.detect_conflicts."""

    @pytest.fixture
    def extraction_service(self, db: Database) -> ExtractionService:
        from ai_nexus.repos.entity_repo import EntityRepo
        from ai_nexus.repos.rule_repo import RuleRepo

        svc = ExtractionService.__new__(ExtractionService)
        svc._api_key = "test"
        svc._base_url = None
        svc._model = "test"
        svc._entity_repo = EntityRepo(db)
        svc._rule_repo = RuleRepo(db)
        svc._relation_repo = None
        return svc

    async def test_duplicate_entity_detected(
        self, extraction_service: ExtractionService, db: Database,
    ):
        from ai_nexus.models.entity import EntityCreate
        from ai_nexus.repos.entity_repo import EntityRepo

        repo = EntityRepo(db)
        await repo.create(EntityCreate(
            name="订单", type="概念", domain="payment", description="existing",
        ))

        conflicts = await extraction_service.detect_conflicts({
            "entities": [_make_entity("订单", "payment")],
            "rules": [],
        })
        assert len(conflicts["duplicates"]) == 1
        assert conflicts["duplicates"][0]["type"] == "entity"
        assert conflicts["duplicates"][0]["existing_name"] == "订单"

    async def test_duplicate_rule_detected(
        self, extraction_service: ExtractionService, db: Database,
    ):
        from ai_nexus.models.rule import RuleCreate
        from ai_nexus.repos.rule_repo import RuleRepo

        repo = RuleRepo(db)
        await repo.create(RuleCreate(
            name="NoDirectDB", domain="backend", severity="error",
            description="rule",
        ))

        conflicts = await extraction_service.detect_conflicts({
            "entities": [],
            "rules": [_make_rule("NoDirectDB", "backend")],
        })
        assert len(conflicts["duplicates"]) == 1
        assert conflicts["duplicates"][0]["type"] == "rule"

    async def test_no_conflicts(self, extraction_service: ExtractionService):
        conflicts = await extraction_service.detect_conflicts({
            "entities": [_make_entity("NewEntity", "fresh")],
            "rules": [_make_rule("NewRule", "fresh")],
        })
        assert len(conflicts["duplicates"]) == 0


# ── 5. Backward compatibility ────────────────────────────────────────


class TestBackwardCompat:
    """Old-format candidates (no source_context/temp_id) still work."""

    async def test_old_format_full_approval(self, audit_repo: AuditRepo):
        """Submit without source_context, approve via old path."""
        log = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={"entities": [_make_entity()], "rules": [], "relations": []},
        ))
        # No source_context
        fetched = await audit_repo.get_by_id(log.id)
        assert fetched.source_context is None
        # But temp_ids are still injected by repo
        assert "temp_id" in fetched.new_value["entities"][0]

    async def test_old_format_approve_via_audit_repo(self, audit_repo: AuditRepo):
        """Simulate old-style full approve (create approve log)."""
        candidate = await audit_repo.create(AuditLogCreate(
            table_name="extraction", record_id=0, action="submit_candidate",
            new_value={"entities": [_make_entity()], "rules": [], "relations": []},
        ))
        approve_log = await audit_repo.create(AuditLogCreate(
            table_name="knowledge_audit_log",
            record_id=candidate.id,
            action="approve",
            reviewer="admin",
        ))
        assert approve_log.action == "approve"
        assert approve_log.record_id == candidate.id

    async def test_ingest_candidate_old_data_no_temp_ids(
        self, extraction_service_for_compat: ExtractionService,
    ):
        """ingest_candidate works with data that has no temp_ids."""
        data = {
            "entities": [_make_entity()],
            "rules": [],
            "relations": [],
            "source_metadata": None,
        }
        result = await extraction_service_for_compat.ingest_candidate(
            data, approved_temp_ids=None,
        )
        assert result["entities_created"] == 1


@pytest.fixture
def extraction_service_for_compat() -> ExtractionService:
    entity_repo = MagicMock()
    entity_repo.create = AsyncMock(return_value=MagicMock(id=1))
    entity_repo.search = AsyncMock(return_value=[])
    entity_repo.update = AsyncMock()

    mock_db = MagicMock()
    mock_db.transaction = MagicMock()
    mock_db.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_db.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    entity_repo._db = mock_db

    svc = ExtractionService.__new__(ExtractionService)
    svc._api_key = "test"
    svc._base_url = None
    svc._model = "test"
    svc._entity_repo = entity_repo
    svc._rule_repo = None
    svc._relation_repo = None
    return svc


# ── 6. IngestService audit path ──────────────────────────────────────


class TestIngestServiceAuditPath:
    """Verify IngestService submits through audit log, not direct creation."""

    @pytest.fixture
    def ingest_service(self) -> IngestService:
        mock_feishu = MagicMock()
        mock_extraction = MagicMock()
        mock_extraction.extract = AsyncMock(return_value=ExtractionResult(
            entities=[ExtractedEntity(
                name="E1", type="概念", domain="test", confidence=0.9, description="d",
            )],
            rules=[ExtractedRule(
                name="R1", severity="warning", domain="test", confidence=0.8, description="d",
            )],
            relations=[],
        ))

        mock_audit = MagicMock()
        mock_audit.create = AsyncMock(return_value=MagicMock(
            id=42, source_context=None, new_value={},
        ))

        return IngestService(
            feishu_proxy=mock_feishu,
            extraction_service=mock_extraction,
            entity_repo=MagicMock(),
            relation_repo=MagicMock(),
            rule_repo=MagicMock(),
            audit_repo=mock_audit,
        )

    @pytest.mark.asyncio
    async def test_document_submits_to_audit_log(
        self, ingest_service: IngestService,
    ):
        with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
            result = await ingest_service.ingest_document(
                content="Some business content",
                title="Test Doc",
                source="manual",
            )

        # Verify audit repo was called (not entity/rule repos)
        ingest_service._audit.create.assert_called_once()
        call_args = ingest_service._audit.create.call_args
        audit_create = call_args[0][0]
        assert audit_create.action == "submit_candidate"
        assert audit_create.source_context["source_type"] == "document"

        # Verify return format
        assert result["submitted"] == 2  # 1 entity + 1 rule
        assert result["status"] == "pending_audit"

    @pytest.mark.asyncio
    async def test_feishu_submits_to_audit_log(
        self, ingest_service: IngestService,
    ):
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_document(
                    content="Feishu doc content",
                    title="飞书文档",
                    source="feishu:space1",
                    space_id="space1",
                    doc_token="tok1",
                )

        ingest_service._audit.create.assert_called_once()
        call_args = ingest_service._audit.create.call_args
        audit_create = call_args[0][0]
        assert audit_create.source_context["source_type"] == "feishu"
        assert audit_create.source_context["space_id"] == "space1"
        assert result["status"] == "pending_audit"

    @pytest.mark.asyncio
    async def test_no_direct_entity_creation(
        self, ingest_service: IngestService,
    ):
        """Verify entity/rule repos are NOT called directly."""
        with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
            await ingest_service.ingest_document(
                content="content", title="T",
            )

        # Entity/rule/relation repos should not have create called
        ingest_service._entities.create.assert_not_called()
        ingest_service._rules.create.assert_not_called()
        ingest_service._relations.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_content_returns_direct(
        self, ingest_service: IngestService,
    ):
        result = await ingest_service.ingest_document(
            content="", title="Empty",
        )
        assert result["submitted"] == 0
        assert result["status"] == "direct"
        ingest_service._audit.create.assert_not_called()


# ── 7. Migration test ────────────────────────────────────────────────


class TestMigration:
    """Verify migration 007 adds source_context column."""

    async def test_source_context_column_exists_after_migration(
        self, db: Database,
    ):
        row = await db.fetchone(
            "SELECT sql FROM sqlite_master WHERE name = 'knowledge_audit_log'"
        )
        assert row is not None
        schema = row[0]
        assert "source_context" in schema

    async def test_rollback_removes_column(self, db: Database):
        """Verify rollback (DROP COLUMN) works."""
        await db.execute(
            "ALTER TABLE knowledge_audit_log DROP COLUMN source_context"
        )
        row = await db.fetchone(
            "SELECT sql FROM sqlite_master WHERE name = 'knowledge_audit_log'"
        )
        assert "source_context" not in row[0]


# ── 8. ApproveRequest model validation ───────────────────────────────


class TestApproveRequestModel:
    """Test ApproveRequest and ItemAction models."""

    def test_approve_request_with_items(self):
        req = ApproveRequest(
            reviewer="admin",
            items=[
                ItemAction(temp_id="1_entity_0", action="approve"),
                ItemAction(temp_id="1_rule_0", action="reject"),
            ],
        )
        assert len(req.items) == 2
        assert req.items[0].action == "approve"
        assert req.items[1].action == "reject"

    def test_approve_request_without_items(self):
        req = ApproveRequest(reviewer="console")
        assert req.items is None
        assert req.reviewer == "console"

    def test_item_action_requires_valid_action(self):
        with pytest.raises(ValueError):
            ItemAction(temp_id="1_entity_0", action="invalid")

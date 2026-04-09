"""Tests for Pydantic data models."""


from ai_nexus.models.audit import AuditLog, HookRequest, KnowledgeCandidate
from ai_nexus.models.entity import Entity, EntityCreate, EntityUpdate
from ai_nexus.models.relation import Relation, RelationCreate
from ai_nexus.models.rule import RuleCreate, RuleUpdate


class TestEntityModels:
    """Entity model validation tests."""

    def test_entity_create_minimal(self):
        entity = EntityCreate(name="Payment", type="service", domain="finance")
        assert entity.name == "Payment"
        assert entity.type == "service"
        assert entity.domain == "finance"
        assert entity.status == "approved"
        assert entity.source == "manual"
        assert entity.description is None

    def test_entity_create_full(self):
        entity = EntityCreate(
            name="Order",
            type="aggregate",
            description="Customer order entity",
            attributes={"fields": ["id", "amount", "status"]},
            domain="commerce",
            status="pending",
            source="ai_extracted",
        )
        assert entity.attributes == {"fields": ["id", "amount", "status"]}
        assert entity.status == "pending"

    def test_entity_update_partial(self):
        update = EntityUpdate(name="NewName")
        assert update.name == "NewName"
        assert update.type is None
        assert update.domain is None

    def test_entity_from_attributes(self):
        entity = Entity(
            id=1,
            name="Payment",
            type="service",
            domain="finance",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        assert entity.id == 1


class TestRelationModels:
    """Relation model validation tests."""

    def test_relation_create(self):
        rel = RelationCreate(
            source_entity_id=1,
            relation_type="depends_on",
            target_entity_id=2,
        )
        assert rel.weight == 1.0
        assert rel.status == "approved"

    def test_relation_with_conditions(self):
        rel = RelationCreate(
            source_entity_id=1,
            relation_type="triggers",
            target_entity_id=2,
            conditions={"when": "status=completed"},
        )
        assert rel.conditions == {"when": "status=completed"}

    def test_relation_model(self):
        rel = Relation(
            id=1,
            source_entity_id=1,
            relation_type="belongs_to",
            target_entity_id=2,
        )
        assert rel.id == 1


class TestRuleModels:
    """Rule model validation tests."""

    def test_rule_create(self):
        rule = RuleCreate(
            name="Payment timeout",
            description="Payment must complete within 30 minutes",
            domain="finance",
        )
        assert rule.severity == "warning"
        assert rule.status == "pending"
        assert rule.confidence == 0.0

    def test_rule_update(self):
        update = RuleUpdate(severity="critical", confidence=0.95)
        assert update.severity == "critical"
        assert update.name is None

    def test_rule_with_related_entities(self):
        rule = RuleCreate(
            name="Refund limit",
            description="Refund amount cannot exceed original payment",
            domain="finance",
            related_entity_ids=[1, 2, 3],
            severity="error",
        )
        assert rule.related_entity_ids == [1, 2, 3]


class TestAuditModels:
    """Audit model validation tests."""

    def test_knowledge_candidate(self):
        candidate = KnowledgeCandidate(
            type="entity",
            data={"name": "Invoice", "type": "document", "domain": "finance"},
            source="ai_extracted",
            confidence=0.85,
        )
        assert candidate.type == "entity"
        assert candidate.confidence == 0.85

    def test_hook_request_pre_plan(self):
        req = HookRequest(task_description="Add refund feature")
        assert req.task_description == "Add refund feature"
        assert req.keywords is None
        assert req.diff is None

    def test_hook_request_pre_commit(self):
        req = HookRequest(
            task_description="Commit",
            diff="diff --git a/payment.py",
            affected_files=["payment.py"],
        )
        assert req.diff is not None
        assert len(req.affected_files) == 1

    def test_audit_log(self):
        log = AuditLog(
            id=1,
            table_name="entities",
            record_id=42,
            action="approve",
        )
        assert log.table_name == "entities"

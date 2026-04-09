"""Tests for LintService knowledge health scanning."""

import pytest

from ai_nexus.models.entity import EntityCreate
from ai_nexus.models.rule import RuleCreate
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.lint_service import LintService


@pytest.fixture
async def lint_service(db):
    """Provide a LintService instance with repos."""
    entity_repo = EntityRepo(db)
    rule_repo = RuleRepo(db)
    audit_repo = AuditRepo(db)
    return LintService(rule_repo, entity_repo, audit_repo)


@pytest.mark.asyncio
async def test_conflict_detection(lint_service: LintService):
    """Test detection of contradictory rules within the same domain."""
    rule_repo = lint_service._rule_repo

    # Create two conflicting rules in the same domain
    await rule_repo.create(RuleCreate(
        name="订单可取消规则",
        description="订单可在24小时内取消",
        domain="订单",
        severity="warning",
        status="approved",
    ))

    await rule_repo.create(RuleCreate(
        name="订单不可取消规则",
        description="订单一旦确认不可取消",
        domain="订单",
        severity="warning",
        status="approved",
    ))

    # Run conflict detection
    conflicts = await lint_service.detect_conflicts()

    # Should detect at least one conflict
    assert len(conflicts) >= 1
    assert conflicts[0].domain == "订单"
    assert "可以" in conflicts[0].reason or "不可" in conflicts[0].reason


@pytest.mark.asyncio
async def test_no_conflicts_for_consistent_rules(lint_service: LintService):
    """Test that no conflicts are detected when rules are consistent."""
    rule_repo = lint_service._rule_repo

    # Create two non-conflicting rules
    await rule_repo.create(RuleCreate(
        name="订单折扣规则",
        description="VIP用户可享受9折优惠",
        domain="订单",
        severity="info",
        status="approved",
    ))

    await rule_repo.create(RuleCreate(
        name="订单配送规则",
        description="订单满99元包邮",
        domain="订单",
        severity="info",
        status="approved",
    ))

    conflicts = await lint_service.detect_conflicts()
    # Should not detect conflicts for these consistent rules
    order_conflicts = [c for c in conflicts if c.domain == "订单"]
    assert len(order_conflicts) == 0


@pytest.mark.asyncio
async def test_dead_rule_detection(lint_service: LintService):
    """Test detection of rules not referenced in audit logs."""
    from datetime import datetime, timedelta

    rule_repo = lint_service._rule_repo
    db = rule_repo._db

    # Create an old rule directly in the database (to control created_at)
    old_date = (datetime.now() - timedelta(days=35)).isoformat()
    await db.execute(
        """INSERT INTO rules (name, description, domain, severity, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("废弃规则", "这是一个很久没用的规则", "测试域", "warning", "approved", old_date),
    )

    # Create a recent rule
    await rule_repo.create(RuleCreate(
        name="新规则",
        description="这是一个新规则",
        domain="测试域",
        severity="info",
        status="approved",
    ))

    # Run dead rule detection
    dead_rules = await lint_service.detect_dead_rules(days_threshold=30)

    # Should detect the old rule with no audit references
    assert len(dead_rules) >= 1
    assert any(r.rule_name == "废弃规则" for r in dead_rules)
    assert all(r.days_since_creation >= 30 for r in dead_rules)


@pytest.mark.asyncio
async def test_coverage_gap_detection(lint_service: LintService):
    """Test detection of domains with entities but no rules."""
    entity_repo = lint_service._entity_repo
    rule_repo = lint_service._rule_repo

    # Create entities in a domain with no rules
    await entity_repo.create(EntityCreate(
        name="手术A",
        type="procedure",
        domain="手术",
        description="手术类型A",
    ))

    await entity_repo.create(EntityCreate(
        name="手术B",
        type="procedure",
        domain="手术",
        description="手术类型B",
    ))

    # Create a rule in a different domain
    await rule_repo.create(RuleCreate(
        name="排班规则",
        description="医生排班规则",
        domain="排班",
        severity="info",
        status="approved",
    ))

    # Run coverage gap detection
    gaps = await lint_service.detect_coverage_gaps()

    # Should detect the "手术" domain as a coverage gap
    assert len(gaps) >= 1
    surgery_gap = next((g for g in gaps if g.domain == "手术"), None)
    assert surgery_gap is not None
    assert surgery_gap.entity_count == 2
    assert "手术A" in surgery_gap.entities
    assert "手术B" in surgery_gap.entities


@pytest.mark.asyncio
async def test_full_report_generation(lint_service: LintService):
    """Test generation of a complete lint report."""
    rule_repo = lint_service._rule_repo
    entity_repo = lint_service._entity_repo

    # Create test data
    await rule_repo.create(RuleCreate(
        name="测试规则",
        description="可以测试",
        domain="测试",
        severity="warning",
        status="approved",
    ))

    await rule_repo.create(RuleCreate(
        name="测试规则2",
        description="不可以测试",
        domain="测试",
        severity="warning",
        status="approved",
    ))

    await entity_repo.create(EntityCreate(
        name="测试实体",
        type="test",
        domain="无规则域",
    ))

    # Generate full report
    report = await lint_service.generate_report()

    # Verify report structure
    assert report.generated_at is not None
    assert isinstance(report.conflicts, list)
    assert isinstance(report.dead_rules, list)
    assert isinstance(report.coverage_gaps, list)


@pytest.mark.asyncio
async def test_markdown_report_format(lint_service: LintService):
    """Test Markdown formatting of lint reports."""
    rule_repo = lint_service._rule_repo
    entity_repo = lint_service._entity_repo

    # Create test data with conflicts
    await rule_repo.create(RuleCreate(
        name="规则1",
        description="允许访问",
        domain="安全",
        severity="warning",
        status="approved",
    ))

    await rule_repo.create(RuleCreate(
        name="规则2",
        description="不允许访问",
        domain="安全",
        severity="warning",
        status="approved",
    ))

    await entity_repo.create(EntityCreate(
        name="孤岛实体",
        type="entity",
        domain="孤岛域",
    ))

    report = await lint_service.generate_report()
    markdown = report.to_markdown()

    # Verify markdown structure
    assert "# 知识健康度报告" in markdown
    assert "## 规则冲突" in markdown
    assert "## 死规则" in markdown
    assert "## 覆盖缺口" in markdown
    assert "安全" in markdown or "孤岛域" in markdown


@pytest.mark.asyncio
async def test_cross_domain_no_conflict(lint_service: LintService):
    """Test that rules in different domains don't trigger conflicts."""
    rule_repo = lint_service._rule_repo

    # Create rules with opposite keywords but in different domains
    await rule_repo.create(RuleCreate(
        name="域A规则",
        description="可以操作",
        domain="域A",
        severity="info",
        status="approved",
    ))

    await rule_repo.create(RuleCreate(
        name="域B规则",
        description="不可以操作",
        domain="域B",
        severity="info",
        status="approved",
    ))

    conflicts = await lint_service.detect_conflicts()

    # Should not detect cross-domain conflicts
    assert not any(c.domain == "域A" and "域B" in c.rule_2_name for c in conflicts)
    assert not any(c.domain == "域B" and "域A" in c.rule_2_name for c in conflicts)


@pytest.mark.asyncio
async def test_empty_report_for_clean_database(lint_service: LintService):
    """Test report generation when database is empty."""
    report = await lint_service.generate_report()

    assert len(report.conflicts) == 0
    assert len(report.dead_rules) == 0
    assert len(report.coverage_gaps) == 0

    markdown = report.to_markdown()
    assert "未发现规则冲突" in markdown
    assert "未发现死规则" in markdown
    assert "未发现覆盖缺口" in markdown

"""Tests for data flywheel functionality (violation events, confidence boost, pattern detection)."""

import pytest

from ai_nexus.models.rule import RuleCreate, RuleUpdate
from ai_nexus.models.violation import ViolationEventCreate, ViolationEventUpdate
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.repos.violation_repo import ViolationRepo
from ai_nexus.services.flywheel_service import FlywheelService


@pytest.mark.asyncio
async def test_violation_event_recording(db):
    """Test recording a new violation event."""
    repo = ViolationRepo(db)

    event = await repo.create(
        ViolationEventCreate(
            rule_id="test-rule-1",
            change_description="Modified order deletion logic",
            resolution="pending",
        )
    )

    assert event.id is not None
    assert event.rule_id == "test-rule-1"
    assert event.change_description == "Modified order deletion logic"
    assert event.resolution == "pending"
    assert event.created_at is not None
    assert event.resolved_at is None


@pytest.mark.asyncio
async def test_violation_event_resolution(db):
    """Test resolving a violation event."""
    repo = ViolationRepo(db)

    # Create an event
    event = await repo.create(
        ViolationEventCreate(
            rule_id="test-rule-2",
            change_description="Test violation",
            resolution="pending",
        )
    )

    # Resolve it
    resolved = await repo.update(event.id, ViolationEventUpdate(resolution="fixed"))

    assert resolved.id == event.id
    assert resolved.resolution == "fixed"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_confidence_boost_on_fixed_violation(db):
    """Test rule confidence increases when violation is fixed."""
    rule_repo = RuleRepo(db)
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    # Create a rule with initial confidence
    rule = await rule_repo.create(
        RuleCreate(
            name="Test Rule",
            description="Test rule for confidence boost",
            domain="test",
            confidence=0.80,
            status="approved",
        )
    )

    # Create and resolve a violation as "fixed"
    event = await violation_repo.create(
        ViolationEventCreate(
            rule_id=str(rule.id),
            change_description="Test violation",
            resolution="pending",
        )
    )

    await flywheel.resolve_violation(event.id, "fixed")

    # Check confidence was boosted
    updated_rule = await rule_repo.get(rule.id)
    assert updated_rule.confidence == pytest.approx(0.82)  # 0.80 + 0.02


@pytest.mark.asyncio
async def test_no_confidence_boost_on_suppressed_violation(db):
    """Test rule confidence does NOT increase when violation is suppressed."""
    rule_repo = RuleRepo(db)
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    # Create a rule with initial confidence
    rule = await rule_repo.create(
        RuleCreate(
            name="Test Rule",
            description="Test rule for no boost",
            domain="test",
            confidence=0.80,
            status="approved",
        )
    )

    # Create and resolve a violation as "suppressed"
    event = await violation_repo.create(
        ViolationEventCreate(
            rule_id=str(rule.id),
            change_description="Test violation",
            resolution="pending",
        )
    )

    await flywheel.resolve_violation(event.id, "suppressed")

    # Check confidence was NOT boosted
    updated_rule = await rule_repo.get(rule.id)
    assert updated_rule.confidence == 0.80  # Unchanged


@pytest.mark.asyncio
async def test_confidence_cap_at_maximum(db):
    """Test rule confidence is capped at 1.0."""
    rule_repo = RuleRepo(db)
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    # Create a rule near max confidence
    rule = await rule_repo.create(
        RuleCreate(
            name="Test Rule",
            description="Test rule for cap",
            domain="test",
            confidence=0.99,
            status="approved",
        )
    )

    # Create and resolve a violation as "fixed"
    event = await violation_repo.create(
        ViolationEventCreate(
            rule_id=str(rule.id),
            change_description="Test violation",
            resolution="pending",
        )
    )

    await flywheel.resolve_violation(event.id, "fixed")

    # Check confidence is capped at 1.0
    updated_rule = await rule_repo.get(rule.id)
    assert updated_rule.confidence == 1.0


@pytest.mark.asyncio
async def test_list_violations_by_rule(db):
    """Test listing violations for a specific rule."""
    repo = ViolationRepo(db)

    rule_id = "test-rule-list"

    # Create multiple events
    await repo.create(
        ViolationEventCreate(
            rule_id=rule_id,
            change_description="First violation",
            resolution="pending",
        )
    )
    await repo.create(
        ViolationEventCreate(
            rule_id=rule_id,
            change_description="Second violation",
            resolution="fixed",
        )
    )
    # Different rule
    await repo.create(
        ViolationEventCreate(
            rule_id="other-rule",
            change_description="Other violation",
            resolution="pending",
        )
    )

    # List by rule
    events = await repo.list_by_rule(rule_id)

    assert len(events) == 2
    assert all(e.rule_id == rule_id for e in events)


@pytest.mark.asyncio
async def test_violation_stats_calculation(db):
    """Test violation statistics aggregation."""
    repo = ViolationRepo(db)

    rule_id = "stats-rule"

    # Create various events with different resolutions
    await repo.create(ViolationEventCreate(rule_id=rule_id, change_description="v1", resolution="fixed"))
    await repo.create(ViolationEventCreate(rule_id=rule_id, change_description="v2", resolution="fixed"))
    await repo.create(ViolationEventCreate(rule_id=rule_id, change_description="v3", resolution="suppressed"))
    await repo.create(ViolationEventCreate(rule_id=rule_id, change_description="v4", resolution="pending"))

    stats = await repo.get_stats(days=30)

    assert len(stats) == 1
    stat = stats[0]
    assert stat.rule_id == rule_id
    assert stat.violation_count == 4
    assert stat.fixed_count == 2
    assert stat.fix_rate == 0.5


@pytest.mark.asyncio
async def test_pattern_detection_below_threshold(db):
    """Test pattern detection returns empty when below threshold."""
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(None, violation_repo)  # rule_repo not needed for detection

    # Create only 2 similar violations (below threshold of 3)
    await violation_repo.create(
        ViolationEventCreate(
            rule_id="rule-1",
            change_description="payment processing logic modified",
            resolution="ignored",
        )
    )
    await violation_repo.create(
        ViolationEventCreate(
            rule_id="rule-2",
            change_description="payment processing logic changed",
            resolution="ignored",
        )
    )

    patterns = await flywheel.detect_violation_patterns(days=30)

    # Should be empty since below threshold
    assert len(patterns) == 0


@pytest.mark.asyncio
async def test_pattern_detection_above_threshold(db):
    """Test pattern detection finds patterns above threshold."""
    violation_repo = ViolationRepo(db)
    rule_repo = RuleRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    # Create 3 similar violations (at threshold)
    for i in range(3):
        await violation_repo.create(
            ViolationEventCreate(
                rule_id=f"rule-{i}",
                change_description="payment processing logic modified",
                resolution="ignored",
            )
        )

    patterns = await flywheel.detect_violation_patterns(days=30)

    # Should find the pattern
    assert len(patterns) >= 1


@pytest.mark.asyncio
async def test_generate_rule_candidate(db):
    """Test generating a rule candidate from a pattern."""
    rule_repo = RuleRepo(db)
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    pattern = "payment processing logic modified"

    rule = await flywheel.generate_rule_candidate(pattern, source_domain="ecommerce")

    assert rule.id is not None
    assert rule.status == "pending"
    assert rule.source == "flywheel"
    assert "payment processing logic modified" in rule.description
    assert rule.confidence == 0.5


@pytest.mark.asyncio
async def test_get_violation_stats_service(db):
    """Test getting violation stats through service."""
    rule_repo = RuleRepo(db)
    violation_repo = ViolationRepo(db)
    flywheel = FlywheelService(rule_repo, violation_repo)

    rule_id = "stats-service-rule"

    # Create some violations
    for i in range(5):
        resolution = "fixed" if i < 3 else "pending"
        await violation_repo.create(
            ViolationEventCreate(
                rule_id=rule_id,
                change_description=f"violation {i}",
                resolution=resolution,
            )
        )

    stats = await flywheel.get_violation_stats(days=30)

    assert len(stats) == 1
    stat = stats[0]
    assert stat.rule_id == rule_id
    assert stat.violation_count == 5
    assert stat.fixed_count == 3

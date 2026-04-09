"""FlywheelService — data flywheel for rule confidence boosting and pattern detection.

Implements the data flywheel functionality:
- Confidence boosting when rules successfully catch violations
- Pattern detection for generating new rule candidates
- Violation event tracking and statistics
"""

from __future__ import annotations

from typing import Any

from ai_nexus.models.rule import Rule, RuleCreate, RuleUpdate
from ai_nexus.models.violation import ViolationEventCreate, ViolationEventUpdate
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.repos.violation_repo import ViolationRepo


class FlywheelService:
    """Service for data flywheel operations.

    Manages the feedback loop where successful rule violations lead to
    higher confidence, and repeated patterns lead to new rule candidates.
    """

    CONFIDENCE_BOOST = 0.02
    CONFIDENCE_CAP = 1.0
    PATTERN_THRESHOLD = 3  # Number of similar violations to trigger candidate generation

    def __init__(self, rule_repo: RuleRepo, violation_repo: ViolationRepo) -> None:
        self._rules = rule_repo
        self._violations = violation_repo

    async def record_violation(self, data: ViolationEventCreate) -> Any:
        """Record a new violation event.

        Args:
            data: Violation event data

        Returns:
            Created violation event
        """
        return await self._violations.create(data)

    async def resolve_violation(
        self, event_id: int, resolution: str
    ) -> Any:
        """Resolve a violation event and potentially boost rule confidence.

        If the violation is marked as "fixed", the rule's confidence is boosted.

        Args:
            event_id: ID of the violation event
            resolution: Resolution status (fixed, suppressed, ignored)

        Returns:
            Updated violation event
        """
        # Update the violation event
        event = await self._violations.update(
            event_id, ViolationEventUpdate(resolution=resolution)
        )
        if not event:
            return None

        # Boost confidence only for fixed violations
        if resolution == "fixed":
            await self._boost_confidence(event.rule_id)

        return event

    async def _boost_confidence(self, rule_id: str) -> Rule | None:
        """Boost the confidence score of a rule.

        Increments confidence by CONFIDENCE_BOOST, capped at CONFIDENCE_CAP.

        Args:
            rule_id: ID or name of the rule to boost

        Returns:
            Updated rule, or None if rule not found
        """
        # Try to parse as integer ID first
        try:
            rule = await self._rules.get(int(rule_id))
        except (ValueError, TypeError):
            # Search by name if not an integer
            rules = await self._rules.search(rule_id, limit=1)
            rule = rules[0] if rules else None

        if not rule:
            return None

        # Calculate new confidence
        new_confidence = min(rule.confidence + self.CONFIDENCE_BOOST, self.CONFIDENCE_CAP)

        # Update the rule
        return await self._rules.update(
            rule.id, RuleUpdate(confidence=new_confidence)
        )

    async def detect_violation_patterns(self, days: int = 30) -> list[str]:
        """Detect patterns in uncaught violations that may need new rules.

        Looks for similar changes that were marked as 'ignored' or 'suppressed'
        multiple times, indicating they might warrant a new rule.

        Args:
            days: Number of days to look back for patterns

        Returns:
            List of change descriptions that occurred PATTERN_THRESHOLD or more times
        """
        # Get recent ignored/suppressed violations
        recent_events = await self._violations.list_recent(
            days=days, resolution="ignored", limit=1000
        )
        recent_events.extend(
            await self._violations.list_recent(
                days=days, resolution="suppressed", limit=1000
            )
        )

        # Count similar descriptions (simple keyword matching)
        from collections import Counter

        pattern_counts: Counter[str] = Counter()

        for event in recent_events:
            # Normalize description for matching
            desc = event.change_description.lower().strip()
            # Use first few words as pattern key
            words = desc.split()[:5]
            pattern_key = " ".join(words)
            pattern_counts[pattern_key] += 1

        # Return patterns that exceed threshold
        return [
            pattern
            for pattern, count in pattern_counts.items()
            if count >= self.PATTERN_THRESHOLD
        ]

    async def generate_rule_candidate(
        self, pattern: str, source_domain: str = "flywheel"
    ) -> Rule | None:
        """Generate a new rule candidate from a detected pattern.

        Creates a new rule with pending status for human review.

        Args:
            pattern: Description of the pattern/violation
            source_domain: Domain to categorize the rule under

        Returns:
            Created rule candidate
        """
        rule_data = RuleCreate(
            name=f"Auto-generated rule: {pattern[:50]}...",
            description=(
                f"Automatically generated rule based on "
                f"repeated violation pattern: {pattern}"
            ),
            domain=source_domain,
            severity="warning",
            status="pending",
            source="flywheel",
            confidence=0.5,
        )

        return await self._rules.create(rule_data)

    async def get_violation_stats(self, days: int = 30) -> list[Any]:
        """Get violation statistics for the last N days.

        Args:
            days: Number of days to include in statistics

        Returns:
            List of violation stats per rule
        """
        return await self._violations.get_stats(days=days)

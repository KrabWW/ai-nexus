"""Knowledge health linting service.

Detects rule conflicts, dead rules, and coverage gaps in the knowledge graph.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.rule_repo import RuleRepo

# Chinese opposite keyword pairs for conflict detection
_OPPOSITE_PAIRS = [
    ("可以", "不可以"),
    ("必须", "禁止"),
    ("允许", "不允许"),
    ("能够", "不能"),
    ("可", "不可"),
    ("应当", "不应"),
    ("需要", "无需"),
    ("支持", "不支持"),
    ("启用", "禁用"),
    ("有", "无"),
]


@dataclass
class ConflictPair:
    """A pair of rules that potentially contradict each other."""

    rule_1_id: int
    rule_1_name: str
    rule_2_id: int
    rule_2_name: str
    domain: str
    reason: str


@dataclass
class DeadRule:
    """A rule that hasn't been referenced in audit logs for an extended period."""

    rule_id: int
    rule_name: str
    domain: str
    created_at: datetime
    days_since_creation: int


@dataclass
class CoverageGap:
    """A domain with entities but no associated rules."""

    domain: str
    entity_count: int
    entities: list[str]


@dataclass
class LintReport:
    """Complete lint report for knowledge health assessment."""

    conflicts: list[ConflictPair]
    dead_rules: list[DeadRule]
    coverage_gaps: list[CoverageGap]
    generated_at: datetime

    def to_markdown(self) -> str:
        """Convert report to Markdown format for human consumption."""
        lines = [
            "# 知识健康度报告",
            f"生成时间: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 规则冲突",
            f"检测到 {len(self.conflicts)} 个潜在冲突",
            "",
        ]

        if self.conflicts:
            for conflict in self.conflicts:
                lines.extend([
                    f"- **[{conflict.domain}]** {conflict.rule_1_name} vs {conflict.rule_2_name}",
                    f"  - 原因: {conflict.reason}",
                    "",
                ])
        else:
            lines.append("✅ 未发现规则冲突\n")

        lines.extend([
            "## 死规则",
            f"检测到 {len(self.dead_rules)} 个超过30天未被引用的规则",
            "",
        ])

        if self.dead_rules:
            for rule in self.dead_rules:
                lines.append(
                    f"- **[{rule.domain}]** {rule.rule_name} "
                    f"(创建于 {rule.days_since_creation} 天前)"
                )
        else:
            lines.append("✅ 未发现死规则\n")

        lines.extend([
            "## 覆盖缺口",
            f"检测到 {len(self.coverage_gaps)} 个有实体但无规则的域",
            "",
        ])

        if self.coverage_gaps:
            for gap in self.coverage_gaps:
                entities_str = ", ".join(gap.entities[:5])
                if gap.entity_count > 5:
                    entities_str += f" ... (共 {gap.entity_count} 个)"
                lines.append(
                    f"- **[{gap.domain}]** 有 {gap.entity_count} 个实体但无规则: {entities_str}"
                )
        else:
            lines.append("✅ 未发现覆盖缺口\n")

        return "\n".join(lines)


class LintService:
    """Service for scanning knowledge graph health issues."""

    def __init__(
        self,
        rule_repo: RuleRepo,
        entity_repo: EntityRepo,
        audit_repo: AuditRepo,
    ) -> None:
        self._rule_repo = rule_repo
        self._entity_repo = entity_repo
        self._audit_repo = audit_repo

    async def detect_conflicts(self) -> list[ConflictPair]:
        """Detect contradictory rules within the same domain.

        Uses heuristic text analysis to find rules with opposite keywords
        or contradictory conditions.
        """
        # Get all approved rules grouped by domain
        approved_rules = await self._rule_repo.list(status="approved", limit=1000)
        conflicts: list[ConflictPair] = []

        # Group by domain
        rules_by_domain: dict[str, list[tuple[int, str, str]]] = {}
        for rule in approved_rules:
            if rule.domain not in rules_by_domain:
                rules_by_domain[rule.domain] = []
            rules_by_domain[rule.domain].append((rule.id, rule.name, rule.description))

        # Check for conflicts within each domain
        for domain, rules in rules_by_domain.items():
            for i, (id_1, name_1, desc_1) in enumerate(rules):
                for id_2, name_2, desc_2 in rules[i + 1:]:
                    conflict_reason = self._check_conflict(name_1, desc_1, name_2, desc_2)
                    if conflict_reason:
                        conflicts.append(ConflictPair(
                            rule_1_id=id_1,
                            rule_1_name=name_1,
                            rule_2_id=id_2,
                            rule_2_name=name_2,
                            domain=domain,
                            reason=conflict_reason,
                        ))

        return conflicts

    def _check_conflict(self, name_1: str, desc_1: str, name_2: str, desc_2: str) -> str | None:
        """Check if two rules potentially conflict based on text analysis.

        Returns a reason string if conflict detected, None otherwise.
        """
        text_1 = (name_1 + " " + (desc_1 or "")).lower()
        text_2 = (name_2 + " " + (desc_2 or "")).lower()

        # Check for opposite keyword pairs
        for positive, negative in _OPPOSITE_PAIRS:
            if positive in text_1 and negative in text_2:
                return f"包含相反关键词: '{positive}' vs '{negative}'"
            if negative in text_1 and positive in text_2:
                return f"包含相反关键词: '{negative}' vs '{positive}'"

        return None

    async def detect_dead_rules(self, days_threshold: int = 30) -> list[DeadRule]:
        """Find rules with no audit log references for an extended period.

        A rule is considered "dead" if:
        1. It has been approved for more than `days_threshold` days
        2. It has zero references in the audit log
        """
        approved_rules = await self._rule_repo.list(status="approved", limit=1000)
        dead_rules: list[DeadRule] = []
        threshold_date = datetime.now() - timedelta(days=days_threshold)

        for rule in approved_rules:
            if not rule.created_at:
                continue

            rule_age = (datetime.now() - rule.created_at).days

            if rule.created_at < threshold_date:
                # Check if this rule has any audit log references
                audit_logs = await self._audit_repo.list_by_record("rules", rule.id)

                if not audit_logs:
                    dead_rules.append(DeadRule(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        domain=rule.domain,
                        created_at=rule.created_at,
                        days_since_creation=rule_age,
                    ))

        return dead_rules

    async def detect_coverage_gaps(self) -> list[CoverageGap]:
        """Find domains with entities but no associated rules.

        This indicates potential unmanaged risk areas where business
        concepts exist but no governing rules have been defined.
        """
        # Get all entities to extract domains
        entities = await self._entity_repo.list(limit=1000)

        # Group entities by domain
        entities_by_domain: dict[str, list[tuple[int, str]]] = {}
        for entity in entities:
            if entity.domain not in entities_by_domain:
                entities_by_domain[entity.domain] = []
            entities_by_domain[entity.domain].append((entity.id, entity.name))

        # Get all rules to extract domains
        rules = await self._rule_repo.list(status="approved", limit=1000)
        rule_domains = {rule.domain for rule in rules}

        # Find domains with entities but no rules
        gaps: list[CoverageGap] = []
        for domain, domain_entities in entities_by_domain.items():
            if domain not in rule_domains:
                gaps.append(CoverageGap(
                    domain=domain,
                    entity_count=len(domain_entities),
                    entities=[name for _, name in domain_entities],
                ))

        return gaps

    async def generate_report(self) -> LintReport:
        """Generate a complete lint report with all health checks."""
        conflicts = await self.detect_conflicts()
        dead_rules = await self.detect_dead_rules()
        gaps = await self.detect_coverage_gaps()

        return LintReport(
            conflicts=conflicts,
            dead_rules=dead_rules,
            coverage_gaps=gaps,
            generated_at=datetime.now(),
        )

## ADDED Requirements

### Requirement: Violation event capture
The system SHALL record every pre-commit violation as an event in a `violation_events` table, capturing the triggering rule, the change description, and the resolution status.

#### Scenario: Violation event recorded
- **WHEN** the pre-commit hook detects a violation of rule "禁止直接删除订单" (severity=critical)
- **THEN** a violation event is created with `rule_id`, `change_description`, `resolution` (fixed/suppressed/ignored), and timestamp

#### Scenario: No violation, no event
- **WHEN** the pre-commit hook finds no violations
- **THEN** no violation event is recorded (only violations are tracked, not clean passes)

### Requirement: Rule confidence boost
The system SHALL automatically increase the confidence score of a rule each time it successfully catches a violation, up to a maximum of 1.0.

#### Scenario: Rule confidence increases on successful catch
- **WHEN** rule "ICU值班规则" (confidence=0.85) catches a violation and the violation is fixed
- **THEN** the rule's confidence is incremented by 0.02 (to 0.87), capped at 1.0

#### Scenario: Rule confidence unchanged on suppressed violation
- **WHEN** a violation is caught but the developer explicitly suppresses it (resolution=suppressed)
- **THEN** the rule's confidence is not changed

### Requirement: New rule candidate from violation patterns
The system SHALL detect when the same type of violation occurs repeatedly without a matching rule, and auto-generate a rule candidate for human review.

#### Scenario: Repeated uncaught violation generates candidate
- **WHEN** 3 or more pre-commit checks detect similar changes (e.g., modifying payment-related entities) that pass validation but are flagged by the developer as concerning
- **THEN** the system creates a rule candidate in the audit workflow with source="flywheel" and the pattern description

### Requirement: Violation statistics API
The system SHALL expose `GET /api/violations/stats` returning aggregated violation statistics.

#### Scenario: Violation stats by rule
- **WHEN** a GET request is sent to `/api/violations/stats`
- **THEN** the response contains per-rule violation counts, fix rates, and average time-to-fix for the last 30 days

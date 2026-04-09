## ADDED Requirements

### Requirement: Rule conflict detection
The system SHALL scan all approved rules and detect pairs that contradict each other within the same domain.

#### Scenario: Contradictory severity rules detected
- **WHEN** two approved rules in the same domain have contradicting conditions (e.g., "订单可在24h内取消" and "订单不可取消")
- **THEN** the lint report includes both rules with a conflict flag and suggested resolution

#### Scenario: No conflicts found
- **WHEN** all approved rules are consistent within their domains
- **THEN** the lint report shows zero conflicts

### Requirement: Dead rule detection
The system SHALL identify rules that have never been referenced or triggered in any pre-commit hook call, PR review, or search query.

#### Scenario: Unused rule flagged
- **WHEN** a rule has been in approved status for more than 30 days and has zero references in the audit log
- **THEN** the lint report flags it as a "potentially dead rule" with its creation date and last audit activity

### Requirement: Coverage gap detection
The system SHALL identify business domains that have entities but no associated rules, suggesting potential unmanaged risk.

#### Scenario: Domain with entities but no rules
- **WHEN** a domain (e.g., "手术") has entities but zero approved rules
- **THEN** the lint report includes a coverage gap warning listing the domain and its entity count

### Requirement: Lint report API
The system SHALL expose `GET /api/lint/report` returning a JSON report of all detected issues.

#### Scenario: Full lint report
- **WHEN** a GET request is sent to `/api/lint/report`
- **THEN** the response contains sections for conflicts, dead rules, and coverage gaps, each with details and severity ratings

### Requirement: Markdown weekly report
The system SHALL provide an API endpoint `GET /api/lint/report?format=markdown` that returns a human-readable weekly digest suitable for sending to team leads.

#### Scenario: Markdown report generation
- **WHEN** a GET request is sent to `/api/lint/report?format=markdown`
- **THEN** the response is a Markdown-formatted report with sections for conflicts, dead rules, and coverage gaps, suitable for pasting into Feishu or Slack

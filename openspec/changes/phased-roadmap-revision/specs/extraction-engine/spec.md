## ADDED Requirements

### Requirement: Text-to-structured knowledge extraction
The system SHALL provide an `ExtractionService` that accepts arbitrary text input and returns structured knowledge candidates (entities, relations, rules) with confidence scores.

#### Scenario: Extract knowledge from commit message
- **WHEN** the extraction service receives text "feat: 新增ICU排班模块，支持24小时值班规则，排班周期7天"
- **THEN** it returns structured output containing at least one rule candidate ("ICU需要24小时值班医生", severity=error, confidence>=0.9) and related entity candidates ("ICU排班", type=功能模块)

#### Scenario: Extract knowledge from Feishu document
- **WHEN** the extraction service receives a multi-paragraph Feishu document about business rules
- **THEN** it returns structured output with entities, relations, and rules, each with domain classification and confidence scores

#### Scenario: No business knowledge found
- **WHEN** the extraction service receives text containing only technical implementation details with no business concepts
- **THEN** it returns an empty result set without error

### Requirement: Extraction prompt configuration
The system SHALL use a configurable extraction prompt that instructs the LLM to extract business entities (with types: 人物/地点/机构/概念/系统), relations (with direction and type), and rules (with severity: error/warning/info).

#### Scenario: Custom domain hint improves extraction
- **WHEN** the extraction service is called with `{"content": "...", "domain_hint": "医疗排班"}`
- **THEN** the extraction prompt includes the domain hint, and extracted items are tagged with that domain

### Requirement: Extraction output schema
The system SHALL return extraction results in a standardized format: `{"entities": [...], "relations": [...], "rules": [...]}`, where each item has `name`, `type`, `domain`, `confidence`, and `description` fields.

#### Scenario: Output schema validation
- **WHEN** the Claude API returns a response that does not match the expected schema
- **THEN** the system logs a warning and attempts to parse/fix the response before returning, or returns empty results if unparseable

### Requirement: Batch extraction with progress
The system SHALL support batch extraction of multiple documents, reporting progress after each document is processed.

#### Scenario: Batch extraction progress reporting
- **WHEN** batch extraction is initiated with 10 documents
- **THEN** after each document is processed, the system logs progress (e.g., "3/10 documents processed"), and final results aggregate all extracted knowledge

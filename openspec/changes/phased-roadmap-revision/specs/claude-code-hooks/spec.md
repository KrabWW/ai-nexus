## ADDED Requirements

### Requirement: Pre-plan hook auto-injection
The system SHALL provide a Claude Code hook script (`pre_plan.py`) that automatically calls `POST /api/hooks/pre-plan` with the current task description before AI starts coding.

#### Scenario: Hook triggers on Write/Edit tool use
- **WHEN** Claude Code triggers the PreToolUse hook matching "Write|Edit" pattern
- **THEN** the hook script reads the task context, calls the AI Nexus pre-plan API, and outputs the business context as a system reminder for the AI

#### Scenario: AI Nexus service unavailable
- **WHEN** the pre-plan hook script cannot reach the AI Nexus service
- **THEN** the hook silently succeeds without blocking the AI, optionally logging a warning

### Requirement: Pre-commit hook auto-validation
The system SHALL provide a Claude Code hook script (`pre_commit.py`) that automatically calls `POST /api/hooks/pre-commit` with the staged changes before code is committed.

#### Scenario: Hook detects rule violation
- **WHEN** the pre-commit hook receives staged changes that affect entities with critical business rules
- **THEN** the hook returns a warning message listing the violated rules, and the AI is prompted to fix the violations

#### Scenario: No violations found
- **WHEN** the pre-commit hook receives staged changes that do not violate any known business rules
- **THEN** the hook succeeds silently, allowing the commit to proceed

#### Scenario: Hook execution timeout
- **WHEN** the pre-commit hook takes longer than 5 seconds to complete
- **THEN** the hook succeeds with a warning (does not block the commit), and logs the timeout for investigation

### Requirement: Hook configuration generation
The system SHALL provide a CLI command `ai-nexus install-hooks` that generates the Claude Code hooks configuration in `.claude/settings.json`.

#### Scenario: Install hooks for the first time
- **WHEN** the user runs `ai-nexus install-hooks --url http://localhost:8000`
- **THEN** the system writes the hooks configuration to `.claude/settings.json` with pre_plan and pre_commit hooks pointing to the specified AI Nexus URL

#### Scenario: Hooks already exist
- **WHEN** the user runs `ai-nexus install-hooks` and hooks already exist in settings.json
- **THEN** the system updates the existing hooks configuration without overwriting other unrelated hooks

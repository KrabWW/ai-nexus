-- src/ai_nexus/db/migrations/003_violation_events.sql
-- Violation events table for data flywheel functionality

CREATE TABLE IF NOT EXISTS violation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    change_description TEXT NOT NULL,
    resolution TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_violation_events_rule_id ON violation_events(rule_id);
CREATE INDEX IF NOT EXISTS idx_violation_events_created_at ON violation_events(created_at);
CREATE INDEX IF NOT EXISTS idx_violation_events_resolution ON violation_events(resolution);

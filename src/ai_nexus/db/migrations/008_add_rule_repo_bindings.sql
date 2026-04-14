-- src/ai_nexus/db/migrations/008_add_rule_repo_bindings.sql
-- Rule ↔ repository bindings for branch-aware rule filtering

CREATE TABLE IF NOT EXISTS rule_repo_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    repo_url TEXT NOT NULL,
    branch_pattern TEXT NOT NULL DEFAULT '*',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(rule_id, repo_url, branch_pattern)
);

CREATE INDEX IF NOT EXISTS idx_rrb_rule_id ON rule_repo_bindings(rule_id);
CREATE INDEX IF NOT EXISTS idx_rrb_repo_url ON rule_repo_bindings(repo_url);

-- Rollback: DROP TABLE IF EXISTS rule_repo_bindings;

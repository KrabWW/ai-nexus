-- src/ai_nexus/db/migrations/006_rule_code_references.sql
-- 代码锚定：规则与代码位置的映射关系

CREATE TABLE IF NOT EXISTS rule_code_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    snippet TEXT,
    repo_url TEXT,
    commit_sha TEXT NOT NULL,
    branch TEXT DEFAULT 'main',
    reference_type TEXT NOT NULL DEFAULT 'violation',
    source TEXT NOT NULL DEFAULT 'pre_commit',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_code_refs_rule_id ON rule_code_references(rule_id);
CREATE INDEX IF NOT EXISTS idx_code_refs_file_path ON rule_code_references(file_path);
CREATE INDEX IF NOT EXISTS idx_code_refs_commit_sha ON rule_code_references(commit_sha);

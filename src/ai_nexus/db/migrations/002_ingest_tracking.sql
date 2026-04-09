-- src/ai_nexus/db/migrations/002_ingest_tracking.sql
-- 飞书文档导入追踪表

CREATE TABLE IF NOT EXISTS ingest_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id TEXT NOT NULL,
    doc_token TEXT NOT NULL,
    doc_title TEXT,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    entities_count INTEGER DEFAULT 0,
    relations_count INTEGER DEFAULT 0,
    rules_count INTEGER DEFAULT 0,
    last_imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(space_id, doc_token)
);

CREATE INDEX IF NOT EXISTS idx_ingest_tracking_space ON ingest_tracking(space_id);
CREATE INDEX IF NOT EXISTS idx_ingest_tracking_status ON ingest_tracking(status);
CREATE INDEX IF NOT EXISTS idx_ingest_tracking_content_hash ON ingest_tracking(content_hash);

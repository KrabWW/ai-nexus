-- src/ai_nexus/db/migrations/004_pending_relations.sql
-- 待处理关系表：存储实体未找到的关系，供后续重试

CREATE TABLE IF NOT EXISTS pending_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_domain TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    description TEXT,
    conditions TEXT,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pending_relations_status ON pending_relations(status);
CREATE INDEX IF NOT EXISTS idx_pending_relations_domain ON pending_relations(domain);
CREATE INDEX IF NOT EXISTS idx_pending_relations_source ON pending_relations(source_name, source_domain);
CREATE INDEX IF NOT EXISTS idx_pending_relations_target ON pending_relations(target_name, target_domain);

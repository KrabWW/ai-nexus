-- src/ai_nexus/db/migrations/005_unique_entity_name.sql
-- 为 entities 表添加唯一约束，防止重复实体
-- 使用表达式索引，无需添加额外列

-- 先处理可能的重复数据（保留最早创建的）
DELETE FROM entities
WHERE id NOT IN (
    SELECT MIN(id) FROM entities GROUP BY LOWER(TRIM(name)), domain
);

-- 创建唯一索引（基于标准化后的 name + domain）
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_name_domain
ON entities(LOWER(TRIM(name)), domain);

-- Step 1: Add source_context column for audit trail provenance
ALTER TABLE knowledge_audit_log ADD COLUMN source_context TEXT;

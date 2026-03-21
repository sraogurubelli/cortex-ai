-- Semantic Memory Storage Schema
--
-- This table stores compressed interaction history for agents.
-- Each row represents the full interaction history for one conversation.

CREATE TABLE IF NOT EXISTS semantic_memory (
    -- Primary key
    thread_id TEXT PRIMARY KEY,

    -- JSON blob containing array of interactions
    -- Format: {"interactions": [{"timestamp": ..., "user_query": ..., ...}, ...]}
    data JSONB NOT NULL,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Indexes for common queries
    CONSTRAINT semantic_memory_thread_id_not_empty CHECK (thread_id <> '')
);

-- Index for efficient lookups by thread_id (already covered by PRIMARY KEY)
-- Index for cleanup by updated_at (find old conversations)
CREATE INDEX IF NOT EXISTS idx_semantic_memory_updated_at
    ON semantic_memory (updated_at);

-- Optional: Index on JSON data for advanced queries
-- (Only needed if you plan to query interaction details directly)
CREATE INDEX IF NOT EXISTS idx_semantic_memory_interactions
    ON semantic_memory USING GIN (data);

-- Cleanup function to remove old entries
-- Call this periodically (e.g. daily cron job)
--
-- Example usage:
--   DELETE FROM semantic_memory WHERE updated_at < NOW() - INTERVAL '30 days';
--
-- Or with a function:
CREATE OR REPLACE FUNCTION cleanup_old_semantic_memory(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM semantic_memory
    WHERE updated_at < NOW() - (days_old || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Example: Delete entries older than 30 days
-- SELECT cleanup_old_semantic_memory(30);

-- Add comments for documentation
COMMENT ON TABLE semantic_memory IS
    'Stores compressed interaction history for agent semantic memory. Each row contains the full history for one conversation thread.';

COMMENT ON COLUMN semantic_memory.thread_id IS
    'Unique thread identifier. Format: semantic_memory:<conversation_id>';

COMMENT ON COLUMN semantic_memory.data IS
    'JSONB array of compressed interaction objects. See PreviousInteraction type for structure.';

COMMENT ON COLUMN semantic_memory.updated_at IS
    'Last update timestamp. Used for TTL-based cleanup.';

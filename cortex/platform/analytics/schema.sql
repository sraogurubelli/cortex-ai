-- StarRocks Analytics Schema
--
-- OLAP tables for real-time analytics on cortex-ai platform data.
--
-- Data Pipeline:
--   PostgreSQL (OLTP) → Debezium CDC → Kafka → StarRocks (OLAP)
--
-- Usage:
--   mysql -h localhost -P 9030 -u root < schema.sql

-- ============================================================================
-- Database Setup
-- ============================================================================

CREATE DATABASE IF NOT EXISTS cortex_analytics;
USE cortex_analytics;

-- ============================================================================
-- Dimension Tables
-- ============================================================================

-- Conversations dimension (SCD Type 1 - overwrite on change)
CREATE TABLE IF NOT EXISTS conversations_dim (
    conversation_id VARCHAR(64) NOT NULL COMMENT 'Conversation UID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID for multi-tenancy',
    user_id VARCHAR(64) COMMENT 'User/principal ID',
    thread_id VARCHAR(128) NOT NULL COMMENT 'LangGraph thread ID',
    title VARCHAR(512) COMMENT 'Conversation title',
    model VARCHAR(64) COMMENT 'Primary LLM model used',
    created_at DATETIME NOT NULL COMMENT 'Conversation creation timestamp',
    updated_at DATETIME NOT NULL COMMENT 'Last update timestamp',
    deleted_at DATETIME COMMENT 'Soft delete timestamp',
    PRIMARY KEY (conversation_id)
)
ENGINE = OLAP
DUPLICATE KEY (conversation_id)
DISTRIBUTED BY HASH(conversation_id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "DEFAULT",
    "compression" = "LZ4"
);

-- Projects dimension
CREATE TABLE IF NOT EXISTS projects_dim (
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    organization_id VARCHAR(64) NOT NULL COMMENT 'Organization ID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    name VARCHAR(256) NOT NULL COMMENT 'Project name',
    created_at DATETIME NOT NULL COMMENT 'Project creation timestamp',
    PRIMARY KEY (project_id)
)
ENGINE = OLAP
DUPLICATE KEY (project_id)
DISTRIBUTED BY HASH(project_id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1"
);

-- Users dimension
CREATE TABLE IF NOT EXISTS users_dim (
    user_id VARCHAR(64) NOT NULL COMMENT 'User/principal ID',
    email VARCHAR(256) COMMENT 'User email',
    display_name VARCHAR(256) COMMENT 'User display name',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    created_at DATETIME NOT NULL COMMENT 'User creation timestamp',
    PRIMARY KEY (user_id)
)
ENGINE = OLAP
DUPLICATE KEY (user_id)
DISTRIBUTED BY HASH(user_id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1"
);

-- ============================================================================
-- Fact Tables
-- ============================================================================

-- Messages fact table (append-only)
CREATE TABLE IF NOT EXISTS messages_fact (
    message_id VARCHAR(64) NOT NULL COMMENT 'Message UID',
    conversation_id VARCHAR(64) NOT NULL COMMENT 'Conversation UID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    user_id VARCHAR(64) COMMENT 'User ID',
    role VARCHAR(32) NOT NULL COMMENT 'Message role (user/assistant/system/tool)',
    content TEXT COMMENT 'Message content',
    token_count INT COMMENT 'Token count (approximate)',
    model VARCHAR(64) COMMENT 'Model used (for assistant messages)',
    has_tool_calls BOOLEAN DEFAULT FALSE COMMENT 'Whether message has tool calls',
    has_attachments BOOLEAN DEFAULT FALSE COMMENT 'Whether message has attachments',
    rating TINYINT COMMENT 'User rating (1=thumbs down, 2=thumbs up)',
    created_at DATETIME NOT NULL COMMENT 'Message creation timestamp',
    PRIMARY KEY (message_id, created_at)
)
ENGINE = OLAP
DUPLICATE KEY (message_id, created_at)
PARTITION BY RANGE(created_at) (
    PARTITION p20260301 VALUES LESS THAN ("2026-04-01"),
    PARTITION p20260401 VALUES LESS THAN ("2026-05-01"),
    PARTITION p20260501 VALUES LESS THAN ("2026-06-01")
)
DISTRIBUTED BY HASH(conversation_id) BUCKETS 20
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "DEFAULT",
    "compression" = "LZ4",
    "dynamic_partition.enable" = "true",
    "dynamic_partition.time_unit" = "MONTH",
    "dynamic_partition.start" = "-3",
    "dynamic_partition.end" = "3",
    "dynamic_partition.prefix" = "p",
    "dynamic_partition.buckets" = "20"
);

-- Token usage fact table (append-only)
CREATE TABLE IF NOT EXISTS token_usage_fact (
    usage_id VARCHAR(64) NOT NULL COMMENT 'Usage record ID',
    conversation_id VARCHAR(64) NOT NULL COMMENT 'Conversation UID',
    message_id VARCHAR(64) COMMENT 'Message UID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    user_id VARCHAR(64) COMMENT 'User ID',
    model VARCHAR(64) NOT NULL COMMENT 'LLM model',
    provider VARCHAR(32) NOT NULL COMMENT 'Provider (openai/anthropic/google)',
    prompt_tokens INT NOT NULL COMMENT 'Prompt tokens',
    completion_tokens INT NOT NULL COMMENT 'Completion tokens',
    total_tokens INT NOT NULL COMMENT 'Total tokens',
    cache_creation_tokens INT COMMENT 'Cache creation tokens (Anthropic)',
    cache_read_tokens INT COMMENT 'Cache read tokens (Anthropic)',
    estimated_cost_usd DECIMAL(10, 6) COMMENT 'Estimated cost in USD',
    created_at DATETIME NOT NULL COMMENT 'Usage timestamp',
    PRIMARY KEY (usage_id, created_at)
)
ENGINE = OLAP
DUPLICATE KEY (usage_id, created_at)
PARTITION BY RANGE(created_at) (
    PARTITION p20260301 VALUES LESS THAN ("2026-04-01"),
    PARTITION p20260401 VALUES LESS THAN ("2026-05-01"),
    PARTITION p20260501 VALUES LESS THAN ("2026-06-01")
)
DISTRIBUTED BY HASH(conversation_id) BUCKETS 20
PROPERTIES (
    "replication_num" = "1",
    "storage_format" = "DEFAULT",
    "compression" = "LZ4",
    "dynamic_partition.enable" = "true",
    "dynamic_partition.time_unit" = "MONTH",
    "dynamic_partition.start" = "-3",
    "dynamic_partition.end" = "3",
    "dynamic_partition.prefix" = "p",
    "dynamic_partition.buckets" = "20"
);

-- Session events fact table (append-only)
CREATE TABLE IF NOT EXISTS session_events_fact (
    event_id VARCHAR(64) NOT NULL COMMENT 'Event ID',
    conversation_id VARCHAR(64) NOT NULL COMMENT 'Conversation UID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    user_id VARCHAR(64) COMMENT 'User ID',
    event_type VARCHAR(32) NOT NULL COMMENT 'Event type (started/completed/error)',
    model VARCHAR(64) COMMENT 'Model used',
    total_tokens INT COMMENT 'Total tokens used (for completed)',
    duration_ms DOUBLE COMMENT 'Duration in milliseconds (for completed)',
    message_count INT COMMENT 'Number of messages (for completed)',
    error_type VARCHAR(64) COMMENT 'Error type (for error events)',
    error_message TEXT COMMENT 'Error message (for error events)',
    created_at DATETIME NOT NULL COMMENT 'Event timestamp',
    PRIMARY KEY (event_id, created_at)
)
ENGINE = OLAP
DUPLICATE KEY (event_id, created_at)
PARTITION BY RANGE(created_at) (
    PARTITION p20260301 VALUES LESS THAN ("2026-04-01"),
    PARTITION p20260401 VALUES LESS THAN ("2026-05-01"),
    PARTITION p20260501 VALUES LESS THAN ("2026-06-01")
)
DISTRIBUTED BY HASH(conversation_id) BUCKETS 20
PROPERTIES (
    "replication_num" = "1",
    "dynamic_partition.enable" = "true",
    "dynamic_partition.time_unit" = "MONTH",
    "dynamic_partition.start" = "-3",
    "dynamic_partition.end" = "3",
    "dynamic_partition.prefix" = "p",
    "dynamic_partition.buckets" = "20"
);

-- ============================================================================
-- Aggregate Tables (Pre-computed for fast queries)
-- ============================================================================

-- Daily usage aggregates (materialized view equivalent)
CREATE TABLE IF NOT EXISTS usage_daily_agg (
    date DATE NOT NULL COMMENT 'Date',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    model VARCHAR(64) NOT NULL COMMENT 'LLM model',
    provider VARCHAR(32) NOT NULL COMMENT 'Provider',
    total_conversations INT NOT NULL COMMENT 'Total conversations',
    total_messages INT NOT NULL COMMENT 'Total messages',
    total_tokens BIGINT NOT NULL COMMENT 'Total tokens',
    total_cost_usd DECIMAL(10, 2) NOT NULL COMMENT 'Total cost in USD',
    avg_tokens_per_message DOUBLE COMMENT 'Average tokens per message',
    PRIMARY KEY (date, project_id, model)
)
ENGINE = OLAP
AGGREGATE KEY (date, tenant_id, project_id, model, provider)
DISTRIBUTED BY HASH(date, project_id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1"
);

-- Conversation metrics aggregate
CREATE TABLE IF NOT EXISTS conversation_metrics_agg (
    conversation_id VARCHAR(64) NOT NULL COMMENT 'Conversation UID',
    project_id VARCHAR(64) NOT NULL COMMENT 'Project UID',
    tenant_id VARCHAR(64) COMMENT 'Tenant ID',
    total_messages INT NOT NULL COMMENT 'Total messages',
    total_tokens BIGINT NOT NULL COMMENT 'Total tokens',
    total_cost_usd DECIMAL(10, 2) NOT NULL COMMENT 'Total cost',
    avg_rating DOUBLE COMMENT 'Average message rating',
    duration_seconds DOUBLE COMMENT 'Total conversation duration',
    first_message_at DATETIME COMMENT 'First message timestamp',
    last_message_at DATETIME COMMENT 'Last message timestamp',
    PRIMARY KEY (conversation_id)
)
ENGINE = OLAP
AGGREGATE KEY (conversation_id, project_id, tenant_id)
DISTRIBUTED BY HASH(conversation_id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1"
);

-- ============================================================================
-- Indexes
-- ============================================================================

-- Bitmap indexes for common filter columns
ALTER TABLE messages_fact ADD INDEX idx_role (role) USING BITMAP;
ALTER TABLE messages_fact ADD INDEX idx_model (model) USING BITMAP;
ALTER TABLE messages_fact ADD INDEX idx_has_tool_calls (has_tool_calls) USING BITMAP;

ALTER TABLE token_usage_fact ADD INDEX idx_model (model) USING BITMAP;
ALTER TABLE token_usage_fact ADD INDEX idx_provider (provider) USING BITMAP;

ALTER TABLE session_events_fact ADD INDEX idx_event_type (event_type) USING BITMAP;

-- ============================================================================
-- Refresh Policies (for aggregate tables)
-- ============================================================================

-- Note: These would typically be populated via scheduled SQL or streaming
-- For now, they can be refreshed via INSERT INTO ... SELECT queries

-- Example refresh query for usage_daily_agg:
-- INSERT INTO usage_daily_agg
-- SELECT
--     DATE(created_at) as date,
--     tenant_id,
--     project_id,
--     model,
--     provider,
--     COUNT(DISTINCT conversation_id) as total_conversations,
--     COUNT(*) as total_messages,
--     SUM(total_tokens) as total_tokens,
--     SUM(estimated_cost_usd) as total_cost_usd,
--     AVG(total_tokens) as avg_tokens_per_message
-- FROM token_usage_fact
-- WHERE DATE(created_at) = CURRENT_DATE - INTERVAL 1 DAY
-- GROUP BY date, tenant_id, project_id, model, provider;

-- ============================================================================
-- Views (Virtual tables for common queries)
-- ============================================================================

-- Recent conversations with metrics
CREATE VIEW IF NOT EXISTS recent_conversations_v AS
SELECT
    c.conversation_id,
    c.project_id,
    c.tenant_id,
    c.user_id,
    c.title,
    c.model,
    c.created_at,
    COUNT(m.message_id) as message_count,
    SUM(m.token_count) as total_tokens,
    MAX(m.created_at) as last_message_at
FROM conversations_dim c
LEFT JOIN messages_fact m ON c.conversation_id = m.conversation_id
WHERE c.deleted_at IS NULL
GROUP BY c.conversation_id, c.project_id, c.tenant_id, c.user_id, c.title, c.model, c.created_at;

-- Daily token usage by model
CREATE VIEW IF NOT EXISTS daily_usage_by_model_v AS
SELECT
    DATE(created_at) as date,
    tenant_id,
    project_id,
    model,
    provider,
    SUM(total_tokens) as total_tokens,
    SUM(estimated_cost_usd) as total_cost_usd,
    COUNT(DISTINCT conversation_id) as conversation_count
FROM token_usage_fact
GROUP BY DATE(created_at), tenant_id, project_id, model, provider;

-- User engagement metrics
CREATE VIEW IF NOT EXISTS user_engagement_v AS
SELECT
    user_id,
    tenant_id,
    COUNT(DISTINCT conversation_id) as conversation_count,
    COUNT(DISTINCT DATE(created_at)) as active_days,
    COUNT(*) as total_messages,
    SUM(token_count) as total_tokens,
    MIN(created_at) as first_message_at,
    MAX(created_at) as last_message_at
FROM messages_fact
WHERE role = 'user'
GROUP BY user_id, tenant_id;

-- Lakebase Workshop: Advanced PostgreSQL Features
-- Run these against your Lakebase endpoint to explore advanced capabilities.
-- Set search_path to your schema (replace with your actual schema name from notebook 00):
-- SET search_path TO lakebase_lab_<your_username>, public;

-- ============================================================
-- 1. JSONB Queries
-- ============================================================

-- Query products by metadata fields
SELECT name, price, metadata->>'brand' as brand
FROM products
WHERE metadata @> '{"brand": "SoundMax"}';

-- Update nested JSONB
UPDATE products
SET metadata = metadata || '{"on_sale": true, "discount_pct": 15}'::jsonb
WHERE category = 'Electronics';

-- Find all products with a specific JSONB key
SELECT name, metadata
FROM products
WHERE metadata ? 'on_sale';


-- ============================================================
-- 2. Array Operations
-- ============================================================

-- Find products with a specific tag
SELECT name, tags
FROM products
WHERE 'featured' = ANY(tags);

-- Find products matching multiple tags (overlap)
SELECT name, tags
FROM products
WHERE tags && ARRAY['audio', 'gaming'];

-- Append a tag to a product
UPDATE products
SET tags = array_append(tags, 'workshop-tested')
WHERE product_id = 1;


-- ============================================================
-- 3. Computed Columns and CTEs
-- ============================================================

-- Revenue by category with window functions
WITH category_stats AS (
    SELECT
        category,
        COUNT(*) as product_count,
        AVG(price) as avg_price,
        SUM(stock_quantity) as total_stock,
        SUM(price * stock_quantity) as potential_revenue
    FROM products
    GROUP BY category
)
SELECT
    category,
    product_count,
    ROUND(avg_price::numeric, 2) as avg_price,
    total_stock,
    ROUND(potential_revenue::numeric, 2) as potential_revenue,
    ROUND(
        potential_revenue / SUM(potential_revenue) OVER () * 100, 1
    ) as revenue_pct
FROM category_stats
ORDER BY potential_revenue DESC;


-- ============================================================
-- 4. Audit Log Analysis
-- ============================================================

-- Operations summary
SELECT
    table_name,
    operation,
    COUNT(*) as count,
    MIN(created_at) as first_at,
    MAX(created_at) as last_at
FROM audit_log
GROUP BY table_name, operation
ORDER BY table_name, operation;

-- Recent changes with before/after comparison
SELECT
    audit_id,
    table_name,
    operation,
    old_data->>'name' as old_name,
    new_data->>'name' as new_name,
    old_data->>'price' as old_price,
    new_data->>'price' as new_price,
    created_at
FROM audit_log
WHERE operation = 'UPDATE'
ORDER BY created_at DESC
LIMIT 10;


-- ============================================================
-- 5. PostgreSQL System Metadata
-- ============================================================

-- Table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) as data_size
FROM pg_tables
WHERE schemaname = current_schema()
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;

-- Index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = current_schema()
ORDER BY idx_scan DESC;

-- Connection stats
SELECT
    datname,
    numbackends as active_connections,
    xact_commit as commits,
    xact_rollback as rollbacks,
    blks_read,
    blks_hit,
    ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) as cache_hit_pct
FROM pg_stat_database
WHERE datname = current_database();


-- ============================================================
-- 6. Transactions Demo
-- ============================================================

-- Multi-statement transaction
BEGIN;

INSERT INTO events (event_type, source, payload)
VALUES ('transaction_demo', 'advanced-sql', '{"step": 1}'::jsonb);

INSERT INTO events (event_type, source, payload)
VALUES ('transaction_demo', 'advanced-sql', '{"step": 2}'::jsonb);

-- Both inserts succeed or fail together
COMMIT;

-- Verify
SELECT * FROM events
WHERE event_type = 'transaction_demo'
ORDER BY created_at DESC;

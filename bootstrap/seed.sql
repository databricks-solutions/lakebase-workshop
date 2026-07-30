-- Lakebase Workshop: Schema Seed
-- Idempotent -- safe to run multiple times
-- Source of truth: notebooks/00_Setup_Lakebase_Project reads this file at runtime.

CREATE SCHEMA IF NOT EXISTS {schema};

-- Products table
CREATE TABLE IF NOT EXISTS {schema}.products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    category VARCHAR(100),
    tags TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Events table (for load testing and CRUD demos)
CREATE TABLE IF NOT EXISTS {schema}.events (
    event_id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(100),
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Agent sessions (for agent memory lab)
CREATE TABLE IF NOT EXISTS {schema}.agent_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Agent messages (short-term memory — conversation history per thread)
CREATE TABLE IF NOT EXISTS {schema}.agent_messages (
    message_id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES {schema}.agent_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Agent memory store (long-term memory — extracted knowledge across sessions)
CREATE TABLE IF NOT EXISTS {schema}.agent_memory_store (
    memory_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    memory TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, topic)
);

-- Audit log (tracks changes across tables)
CREATE TABLE IF NOT EXISTS {schema}.audit_log (
    audit_id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    operation VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    record_id INTEGER,
    old_data JSONB,
    new_data JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_type ON {schema}.events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON {schema}.events(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session ON {schema}.agent_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_user ON {schema}.agent_memory_store(user_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON {schema}.products(category);
CREATE INDEX IF NOT EXISTS idx_products_tags ON {schema}.products USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_audit_table ON {schema}.audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_record ON {schema}.audit_log(record_id);

-- Audit trigger function
-- Uses JSONB extraction to get the PK value, since each table has a different PK column name
CREATE OR REPLACE FUNCTION {schema}.audit_trigger_fn()
RETURNS TRIGGER AS $$
DECLARE
    pk_col TEXT;
    rec_id INTEGER;
BEGIN
    pk_col := CASE TG_TABLE_NAME
        WHEN 'products' THEN 'product_id'
        WHEN 'events'   THEN 'event_id'
        WHEN 'agent_messages' THEN 'message_id'
        ELSE NULL
    END;

    IF TG_OP = 'INSERT' THEN
        rec_id := (row_to_json(NEW)::jsonb ->> pk_col)::int;
        INSERT INTO {schema}.audit_log (table_name, operation, record_id, new_data)
        VALUES (TG_TABLE_NAME, 'INSERT', rec_id, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        rec_id := (row_to_json(NEW)::jsonb ->> pk_col)::int;
        INSERT INTO {schema}.audit_log (table_name, operation, record_id, old_data, new_data)
        VALUES (TG_TABLE_NAME, 'UPDATE', rec_id, row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        rec_id := (row_to_json(OLD)::jsonb ->> pk_col)::int;
        INSERT INTO {schema}.audit_log (table_name, operation, record_id, old_data)
        VALUES (TG_TABLE_NAME, 'DELETE', rec_id, row_to_json(OLD)::jsonb);
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Attach audit triggers (idempotent via DROP IF EXISTS)
DROP TRIGGER IF EXISTS trg_audit_products ON {schema}.products;
CREATE TRIGGER trg_audit_products
    AFTER INSERT OR UPDATE OR DELETE ON {schema}.products
    FOR EACH ROW EXECUTE FUNCTION {schema}.audit_trigger_fn();

DROP TRIGGER IF EXISTS trg_audit_events ON {schema}.events;
CREATE TRIGGER trg_audit_events
    AFTER INSERT OR UPDATE OR DELETE ON {schema}.events
    FOR EACH ROW EXECUTE FUNCTION {schema}.audit_trigger_fn();

-- Seed sample products (skip if already seeded)
INSERT INTO {schema}.products (name, description, price, stock_quantity, category, tags, metadata)
SELECT * FROM (VALUES
    ('Wireless Headphones', 'Bluetooth 5.3 with ANC', 79.99, 150, 'Electronics',
     ARRAY['audio', 'bluetooth', 'featured'], '{"brand": "SoundMax", "color": "black"}'::jsonb),
    ('Mechanical Keyboard', 'Cherry MX Brown switches, RGB', 129.99, 75, 'Electronics',
     ARRAY['peripherals', 'gaming'], '{"brand": "KeyForge", "layout": "TKL"}'::jsonb),
    ('Python Cookbook', 'Advanced recipes for Python 3.12', 44.99, 200, 'Books',
     ARRAY['programming', 'bestseller'], '{"author": "A. Developer", "pages": 680}'::jsonb),
    ('USB-C Hub', '7-in-1 with HDMI and ethernet', 49.99, 300, 'Accessories',
     ARRAY['usb', 'hub', 'new'], '{"brand": "ConnectPro", "ports": 7}'::jsonb),
    ('Standing Desk Mat', 'Anti-fatigue ergonomic mat', 39.99, 90, 'Office',
     ARRAY['ergonomic', 'office'], '{"material": "polyurethane", "size": "20x36"}'::jsonb),
    ('4K Webcam', 'Ultra HD with autofocus and mic', 89.99, 60, 'Electronics',
     ARRAY['video', 'streaming'], '{"brand": "ClearView", "resolution": "4K"}'::jsonb),
    ('Laptop Stand', 'Adjustable aluminum stand', 34.99, 120, 'Accessories',
     ARRAY['ergonomic', 'laptop'], '{"material": "aluminum", "adjustable": true}'::jsonb),
    ('Data Engineering Book', 'Fundamentals of Data Engineering', 54.99, 85, 'Books',
     ARRAY['data', 'engineering', 'featured'], '{"author": "J. Reis", "pages": 450}'::jsonb)
) AS seed(name, description, price, stock_quantity, category, tags, metadata)
WHERE NOT EXISTS (SELECT 1 FROM {schema}.products LIMIT 1);

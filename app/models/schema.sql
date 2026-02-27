CREATE TABLE IF NOT EXISTS products (
    product_name TEXT PRIMARY KEY,
    brand TEXT,
    sugar_g NUMERIC,
    ingredients TEXT,
    usda_signal TEXT,
    review_signals JSONB,
    pubmed_findings JSONB,
    final_insight TEXT,
    data_source TEXT DEFAULT 'pipeline',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS requests_log (
    id BIGSERIAL PRIMARY KEY,
    endpoint TEXT NOT NULL,
    status_code INT NOT NULL,
    latency_ms INT NOT NULL,
    provider TEXT,
    token_usage INT,
    estimated_cost_usd NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_requests_log_created_at ON requests_log(created_at);
CREATE INDEX IF NOT EXISTS idx_requests_log_endpoint ON requests_log(endpoint);

-- FinanceInsight Agent Phase 2.1 schema
-- SQLite-first; the relational model is intentionally close to MySQL.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY,
    stock_code TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    exchange TEXT,
    industry TEXT,
    is_target INTEGER NOT NULL DEFAULT 1 CHECK (is_target IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_periods (
    report_period_id INTEGER PRIMARY KEY,
    period_code TEXT NOT NULL,
    report_year INTEGER NOT NULL CHECK (report_year BETWEEN 1900 AND 2100),
    report_quarter INTEGER NOT NULL CHECK (report_quarter BETWEEN 1 AND 4),
    period_label TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_code, report_year, report_quarter)
);

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_id INTEGER PRIMARY KEY,
    metric_code TEXT NOT NULL UNIQUE,
    metric_name TEXT NOT NULL,
    category TEXT NOT NULL,
    default_unit TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('reported', 'derived')),
    formula TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    report_period_id INTEGER NOT NULL,
    metric_id INTEGER NOT NULL,
    metric_value NUMERIC NOT NULL,
    normalized_unit TEXT NOT NULL,
    raw_value NUMERIC,
    raw_unit TEXT,
    accounting_scope TEXT,
    value_type TEXT NOT NULL CHECK (value_type IN ('reported', 'derived')),
    source_file TEXT,
    source_page INTEGER CHECK (source_page IS NULL OR source_page > 0),
    extraction_method TEXT,
    quality_status TEXT NOT NULL DEFAULT 'candidate_pending_review',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    FOREIGN KEY (report_period_id) REFERENCES report_periods(report_period_id),
    FOREIGN KEY (metric_id) REFERENCES metric_definitions(metric_id),
    UNIQUE (company_id, report_period_id, metric_id)
);

CREATE INDEX IF NOT EXISTS idx_facts_company_period
    ON financial_facts (company_id, report_period_id);

CREATE INDEX IF NOT EXISTS idx_facts_metric_period
    ON financial_facts (metric_id, report_period_id);

CREATE INDEX IF NOT EXISTS idx_facts_quality_status
    ON financial_facts (quality_status);

CREATE INDEX IF NOT EXISTS idx_facts_source
    ON financial_facts (source_file, source_page);



CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('loading', 'loaded', 'failed')),
    error_message TEXT,
    loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_financial_rows (
    raw_row_id INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    stock_code TEXT NOT NULL,
    period_code TEXT NOT NULL,
    report_year INTEGER NOT NULL,
    metric_code TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES ingestion_batches(batch_id),
    UNIQUE (batch_id, source_row_number)
);

CREATE INDEX IF NOT EXISTS idx_raw_rows_business_key
    ON raw_financial_rows (stock_code, period_code, report_year, metric_code);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    quality_issue_id INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL,
    raw_row_id INTEGER,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES ingestion_batches(batch_id),
    FOREIGN KEY (raw_row_id) REFERENCES raw_financial_rows(raw_row_id)
);

CREATE INDEX IF NOT EXISTS idx_quality_batch
    ON data_quality_issues (batch_id, severity);

CREATE VIEW IF NOT EXISTS v_annual_financial_summary AS
SELECT
    c.stock_code,
    c.company_name,
    rp.report_year,
    rp.period_code,
    MAX(CASE WHEN md.metric_code = 'revenue' THEN ff.metric_value END) AS revenue,
    MAX(CASE WHEN md.metric_code = 'net_profit_attributable' THEN ff.metric_value END) AS net_profit_attributable,
    MAX(CASE WHEN md.metric_code = 'net_profit_excl_non_recurring' THEN ff.metric_value END) AS net_profit_excl_non_recurring,
    MAX(CASE WHEN md.metric_code = 'operating_cash_flow' THEN ff.metric_value END) AS operating_cash_flow,
    MAX(CASE WHEN md.metric_code = 'eps' THEN ff.metric_value END) AS eps,
    MAX(CASE WHEN md.metric_code = 'roe' THEN ff.metric_value END) AS roe,
    MAX(CASE WHEN md.metric_code = 'total_assets' THEN ff.metric_value END) AS total_assets,
    MAX(CASE WHEN md.metric_code = 'net_assets' THEN ff.metric_value END) AS net_assets,
    MAX(CASE WHEN md.metric_code = 'net_margin' THEN ff.metric_value END) AS net_margin,
    MAX(CASE WHEN md.metric_code = 'operating_cash_margin' THEN ff.metric_value END) AS operating_cash_margin
FROM financial_facts ff
JOIN companies c ON c.company_id = ff.company_id
JOIN report_periods rp ON rp.report_period_id = ff.report_period_id
JOIN metric_definitions md ON md.metric_id = ff.metric_id
WHERE rp.period_code = 'FY'
GROUP BY c.stock_code, c.company_name, rp.report_year, rp.period_code;

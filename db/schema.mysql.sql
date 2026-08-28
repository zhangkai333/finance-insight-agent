-- FinanceInsight Agent Phase 2 MySQL 8 schema.
-- Execute after selecting the target database, for example: USE finance_insight;

CREATE TABLE IF NOT EXISTS companies (
    company_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    stock_code VARCHAR(16) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    exchange VARCHAR(32) NULL,
    industry VARCHAR(128) NULL,
    is_target TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id),
    UNIQUE KEY uk_companies_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS report_periods (
    report_period_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    period_code VARCHAR(16) NOT NULL,
    report_year SMALLINT NOT NULL,
    report_quarter TINYINT NOT NULL,
    period_label VARCHAR(32) NOT NULL,
    period_start DATE NULL,
    period_end DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (report_period_id),
    UNIQUE KEY uk_report_periods_code_year_quarter (period_code, report_year, report_quarter),
    CONSTRAINT chk_report_periods_year CHECK (report_year BETWEEN 1900 AND 2100),
    CONSTRAINT chk_report_periods_quarter CHECK (report_quarter BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    metric_code VARCHAR(64) NOT NULL,
    metric_name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL,
    default_unit VARCHAR(32) NOT NULL,
    value_type ENUM('reported', 'derived') NOT NULL,
    formula VARCHAR(512) NULL,
    description TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (metric_id),
    UNIQUE KEY uk_metric_definitions_code (metric_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id VARCHAR(64) NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    row_count INT NOT NULL DEFAULT 0,
    status ENUM('loading', 'loaded', 'failed') NOT NULL,
    error_message TEXT NULL,
    loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    KEY idx_ingestion_batches_sha256 (source_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS raw_financial_rows (
    raw_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(64) NOT NULL,
    source_row_number INT NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    period_code VARCHAR(16) NOT NULL,
    report_year SMALLINT NOT NULL,
    metric_code VARCHAR(64) NOT NULL,
    raw_payload JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (raw_row_id),
    UNIQUE KEY uk_raw_rows_batch_row (batch_id, source_row_number),
    KEY idx_raw_rows_business_key (stock_code, period_code, report_year, metric_code),
    CONSTRAINT fk_raw_rows_batch FOREIGN KEY (batch_id) REFERENCES ingestion_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    company_id BIGINT UNSIGNED NOT NULL,
    report_period_id BIGINT UNSIGNED NOT NULL,
    metric_id BIGINT UNSIGNED NOT NULL,
    metric_value DECIMAL(24, 6) NOT NULL,
    normalized_unit VARCHAR(32) NOT NULL,
    raw_value DECIMAL(24, 6) NULL,
    raw_unit VARCHAR(32) NULL,
    accounting_scope VARCHAR(32) NULL,
    value_type ENUM('reported', 'derived') NOT NULL,
    source_file VARCHAR(512) NULL,
    source_page INT NULL,
    extraction_method VARCHAR(128) NULL,
    quality_status VARCHAR(64) NOT NULL DEFAULT 'candidate_pending_review',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (fact_id),
    UNIQUE KEY uk_financial_facts_business_key (company_id, report_period_id, metric_id),
    KEY idx_facts_company_period (company_id, report_period_id),
    KEY idx_facts_metric_period (metric_id, report_period_id),
    KEY idx_facts_quality_status (quality_status),
    KEY idx_facts_source (source_file(191), source_page),
    CONSTRAINT fk_facts_company FOREIGN KEY (company_id) REFERENCES companies(company_id),
    CONSTRAINT fk_facts_period FOREIGN KEY (report_period_id) REFERENCES report_periods(report_period_id),
    CONSTRAINT fk_facts_metric FOREIGN KEY (metric_id) REFERENCES metric_definitions(metric_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS data_quality_issues (
    quality_issue_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(64) NOT NULL,
    raw_row_id BIGINT UNSIGNED NULL,
    issue_code VARCHAR(64) NOT NULL,
    severity ENUM('info', 'warning', 'error') NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (quality_issue_id),
    KEY idx_quality_batch (batch_id, severity),
    CONSTRAINT fk_quality_batch FOREIGN KEY (batch_id) REFERENCES ingestion_batches(batch_id),
    CONSTRAINT fk_quality_raw_row FOREIGN KEY (raw_row_id) REFERENCES raw_financial_rows(raw_row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE OR REPLACE VIEW v_annual_financial_summary AS
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

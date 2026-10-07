-- FinanceInsight Agent Phase 3 lexical RAG baseline schema.
-- The FTS table is a replaceable retrieval backend; semantic embeddings are tracked separately.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY,
    stock_code TEXT NOT NULL,
    company_name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    report_year INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_path TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    parser TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (stock_code, document_type, report_year, source_file)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    section_hint TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(document_id),
    UNIQUE (document_id, page_number, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_documents_company_year
    ON documents (stock_code, report_year, document_type);

CREATE INDEX IF NOT EXISTS idx_chunks_document_page
    ON document_chunks (document_id, page_number);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    content,
    page_number UNINDEXED,
    tokenize = 'trigram'
);

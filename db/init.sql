CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(1000),
    s3_key VARCHAR(500),
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period_start DATE,
    period_end DATE,
    row_count INTEGER,
    file_size BIGINT,
    status VARCHAR(50) DEFAULT 'active',
    file_content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    response_type VARCHAR(20),
    chart_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    data_source VARCHAR(50) DEFAULT 'file_upload',
    s3_bucket VARCHAR(255),
    s3_prefix VARCHAR(500),
    s3_region VARCHAR(50) DEFAULT 'us-east-1',
    aws_access_key VARCHAR(255),
    aws_secret_key VARCHAR(255),
    active_report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main table for scraped websites
CREATE TABLE IF NOT EXISTS scraped_websites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT UNIQUE NOT NULL,
    
    -- Content in different formats
    html TEXT,
    cleaned_html TEXT,
    markdown TEXT,
    formatted_markdown TEXT, -- Markdown with metadata formatting
    links JSONB,  -- Array of links extracted from the page
    media JSONB,  -- Media files info (images, videos, etc.)
    downloaded_files JSONB,  -- List of downloaded file URLs
    is_content_useful BOOLEAN,  -- Flag to indicate if content is useful and should be stored in vector DB
    is_content_pdf BOOLEAN,  -- Flag to indicate if content is a PDF document
    is_active BOOLEAN DEFAULT TRUE,  -- Flag to indicate if URL is still active (not 404). Used for re-crawling. Url could've been deleted from the website.
    ragflow_process_info JSONB,  -- {"ragflow_doc_id": "<id>", save_metadata: true/false, parsing_started: true/false}"}
    -- Metadata
    title TEXT,
    description TEXT,
    author TEXT,
    keywords TEXT,

    
    -- Change detection
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash for quick comparison
    
    -- Status
    status_code INTEGER,
    
    -- Scraping tracking
    scrape_count INTEGER DEFAULT 1,
    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    
    -- Additional data
    response_headers JSONB,  -- Flexible field for any extra data

    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scraped_websites_url ON scraped_websites(url);
CREATE INDEX IF NOT EXISTS idx_scraped_websites_content_hash ON scraped_websites(content_hash);
CREATE INDEX IF NOT EXISTS idx_scraped_websites_last_scraped ON scraped_websites(last_scraped_at);

-- Helper function to calculate content hash
CREATE OR REPLACE FUNCTION calculate_content_hash(content TEXT)
RETURNS VARCHAR(64) AS $$
BEGIN
    RETURN encode(digest(content, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_scraped_websites_updated_at 
    BEFORE UPDATE ON scraped_websites 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
-- Add status column to request_logs table for live request tracking
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed';
CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs(status);

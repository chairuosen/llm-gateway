-- Migration: Add cache token count columns to request_logs table
-- Date: 2026-03-19

ALTER TABLE request_logs ADD COLUMN cache_read_tokens INTEGER NULL;
ALTER TABLE request_logs ADD COLUMN cache_creation_tokens INTEGER NULL;

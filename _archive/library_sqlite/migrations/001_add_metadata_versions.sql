-- Migration: Add step_metadata_versions table
-- Version: 001
-- Date: 2025-11-15
-- Description: Adds version tracking for processing step metadata

-- Create step_metadata_versions table for tracking metadata changes over time
CREATE TABLE IF NOT EXISTS step_metadata_versions (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    version INTEGER NOT NULL,

    -- Change tracking
    changed_at TEXT NOT NULL,
    changed_by TEXT,                      -- "tool", "user", "system"
    change_reason TEXT,                   -- "initial", "manual_edit", "reprocessed", "processing_step"

    -- Snapshot of metadata at this version
    metadata_snapshot TEXT NOT NULL,      -- JSON blob of all metadata at this version

    FOREIGN KEY (item_id) REFERENCES collection_items(id) ON DELETE CASCADE
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_item_id ON step_metadata_versions(item_id);
CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_step_name ON step_metadata_versions(step_name);
CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_changed_at ON step_metadata_versions(changed_at);
CREATE INDEX IF NOT EXISTS idx_step_metadata_versions_item_step ON step_metadata_versions(item_id, step_name);

-- Create unique constraint on item_id + step_name + version
CREATE UNIQUE INDEX IF NOT EXISTS idx_step_metadata_versions_unique ON step_metadata_versions(item_id, step_name, version);

#!/usr/bin/env python3
"""
Data Migration Script: Add status column to request_logs

Adds `status` (VARCHAR(20), NOT NULL DEFAULT 'completed') to request_logs.
Used for live request tracking: records are inserted as 'in_progress' at
request start and updated to 'completed' when the request finishes.

Also creates an index on the status column for efficient filtering.

Usage:
    python migrations/add_log_status.py [--dry-run]
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text

from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def migrate(dry_run: bool = False) -> dict:
    """
    Add status column and index to request_logs.

    Idempotent: skips columns/indexes that already exist.

    Returns migration statistics.
    """
    settings = get_settings()

    database_url = settings.DATABASE_URL
    is_sqlite = "sqlite" in database_url
    if "aiosqlite" in database_url:
        database_url = database_url.replace("aiosqlite", "pysqlite")
    elif "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "+psycopg2")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    stats = {"skipped": 0, "applied": 0, "errors": 0}

    with engine.begin() as conn:
        # Add status column
        existing_columns = {col["name"] for col in inspector.get_columns("request_logs")}
        if "status" in existing_columns:
            logger.info("Column request_logs.status already exists — skipping")
            stats["skipped"] += 1
        else:
            if is_sqlite:
                ddl = "ALTER TABLE request_logs ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'completed'"
            else:
                ddl = "ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed'"
            if dry_run:
                logger.info(f"[DRY RUN] Would execute: {ddl}")
                stats["applied"] += 1
            else:
                try:
                    conn.execute(text(ddl))
                    logger.info(f"Applied: {ddl}")
                    stats["applied"] += 1
                except Exception as exc:
                    logger.error(f"Failed to apply '{ddl}': {exc}")
                    stats["errors"] += 1

        # Create index
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("request_logs")}
        if "idx_request_logs_status" in existing_indexes:
            logger.info("Index idx_request_logs_status already exists — skipping")
            stats["skipped"] += 1
        else:
            if is_sqlite:
                idx_ddl = "CREATE INDEX idx_request_logs_status ON request_logs(status)"
            else:
                idx_ddl = "CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs(status)"
            if dry_run:
                logger.info(f"[DRY RUN] Would execute: {idx_ddl}")
                stats["applied"] += 1
            else:
                try:
                    conn.execute(text(idx_ddl))
                    logger.info(f"Applied: {idx_ddl}")
                    stats["applied"] += 1
                except Exception as exc:
                    logger.error(f"Failed to apply '{idx_ddl}': {exc}")
                    stats["errors"] += 1

    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Add status column to request_logs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    dry_run = args.dry_run
    if dry_run:
        logger.info("=== DRY RUN MODE — no changes will be made ===")

    stats = migrate(dry_run=dry_run)
    logger.info(f"Migration complete: {stats}")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

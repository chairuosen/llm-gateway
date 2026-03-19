#!/usr/bin/env python3
"""
Data Migration Script: Add cache_creation_cost column to request_logs

Adds `cache_creation_cost` (NUMERIC(12,4), nullable) to request_logs.

This field stores the computed cost for Anthropic cache creation tokens,
which are billed separately from regular input tokens at ~25% surcharge.

Usage:
    python migrations/add_cache_creation_cost_to_logs.py [--dry-run]
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

_MIGRATIONS = [
    (
        "request_logs",
        "cache_creation_cost",
        "ALTER TABLE request_logs ADD COLUMN cache_creation_cost NUMERIC(12, 4)",
    ),
]


def migrate(dry_run: bool = False) -> dict:
    """
    Add cache_creation_cost column to request_logs.

    Idempotent: skips columns that already exist.

    Returns migration statistics.
    """
    settings = get_settings()

    database_url = settings.DATABASE_URL
    if "aiosqlite" in database_url:
        database_url = database_url.replace("aiosqlite", "pysqlite")
    elif "+asyncpg" in database_url:
        database_url = database_url.replace("+asyncpg", "+psycopg2")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    stats = {"skipped": 0, "applied": 0, "errors": 0}

    with engine.begin() as conn:
        for table, column, ddl in _MIGRATIONS:
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                logger.info(f"Column {table}.{column} already exists — skipping")
                stats["skipped"] += 1
                continue

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

    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Add cache_creation_cost column to request_logs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 70)
    logger.info("Migration: add_cache_creation_cost_to_logs")
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("DRY RUN — no changes will be made")

    stats = migrate(dry_run=args.dry_run)

    logger.info("=" * 70)
    logger.info("Summary:")
    logger.info(f"  Applied : {stats['applied']}")
    logger.info(f"  Skipped : {stats['skipped']}")
    logger.info(f"  Errors  : {stats['errors']}")
    logger.info("=" * 70)

    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

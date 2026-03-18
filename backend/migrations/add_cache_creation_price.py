#!/usr/bin/env python3
"""
Data Migration Script: Add cache_creation_price column

Adds `cache_creation_price` (NUMERIC(12,4), nullable) to:
  - model_mappings
  - model_mapping_providers

This field stores the per-token price (USD per 1M tokens) for Anthropic's
"cache creation" billing: the one-time cost charged when tokens are written
to the prompt cache for the first time. Typically ~25% higher than the
regular input_price (e.g. $3.75/1M vs $3/1M for claude-3-5-sonnet).

Usage:
    python migrations/add_cache_creation_price.py [--dry-run]
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
        "model_mappings",
        "cache_creation_price",
        "ALTER TABLE model_mappings ADD COLUMN cache_creation_price NUMERIC(12, 4)",
    ),
    (
        "model_mapping_providers",
        "cache_creation_price",
        "ALTER TABLE model_mapping_providers ADD COLUMN cache_creation_price NUMERIC(12, 4)",
    ),
]


def migrate(dry_run: bool = False) -> dict:
    """
    Add cache_creation_price column to model_mappings and model_mapping_providers.

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

    parser = argparse.ArgumentParser(description="Add cache_creation_price column")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 70)
    logger.info("Migration: add_cache_creation_price")
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

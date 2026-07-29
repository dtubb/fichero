#!/usr/bin/env python3
"""Migrate KnowledgeClaim records from single-source to multi-source schema.

Idempotent: safe to run multiple times. Checks source_type to avoid double-migration.

Usage:
    python scripts/migrate_claims_to_multi_source.py [--dry-run] [--library <path>]
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "fichero-server" / "src"))

from fichero_server.db import Database
from fichero_server.db.migrations.runner import migrate_claims_to_multi_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate claims to multi-source schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--library",
        type=Path,
        help="Path to library directory (contains .duckdb file)",
    )
    args = parser.parse_args()

    if args.library:
        db_path = args.library / "fichero.duckdb"
    else:
        # Default: look for the default library
        default_lib = Path.home() / "Library" / "Application Support" / "Fichero"
        candidates = list(default_lib.glob("*.fichero"))
        if not candidates:
            print("ERROR: No library found. Use --library to specify.")
            sys.exit(1)
        db_path = candidates[0] / "fichero.duckdb"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    print(f"Opening database: {db_path}")
    db = Database(db_path)

    migrated, skipped = migrate_claims_to_multi_source(db, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n[DRY RUN] Would migrate {migrated} claims ({skipped} already migrated)")
    else:
        print(f"\nMigrated {migrated} claims ({skipped} already migrated)")

    if migrated == 0 and not args.dry_run:
        print("No migration needed — all claims already multi-source.")


if __name__ == "__main__":
    main()

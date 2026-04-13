#!/usr/bin/env python3
"""CLI script for running knowledge migrations with dry-run and rollback support.

Usage:
    # List available migrations
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py list

    # Dry-run a migration (validate without changing data)
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        migrate_claims_to_multi_source --dry-run --library-path ~/fichero-library

    # Execute a migration
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        migrate_claims_to_multi_source --library-path ~/fichero-library

    # Check status of a migration run
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        status --run-id <audit_id> --library-path ~/fichero-library

    # Rollback a migration
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        rollback --run-id <audit_id> --library-path ~/fichero-library

    # Repair orphaned claim links
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        repair_orphaned_claim_links --dry-run --library-path ~/fichero-library

    # Backfill source metadata
    PYTHONPATH=fichero-api/src python fichero-api/scripts/run_migration.py \
        backfill_claim_source_metadata --dry-run --library-path ~/fichero-library

Exit codes:
    0 - Success
    1 - Migration failed or error occurred
    2 - Validation failed (dry-run found issues)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Setup logging before other imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_argparse() -> argparse.ArgumentParser:
    """Configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Knowledge migration runner with dry-run and rollback support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s migrate_claims_to_multi_source --dry-run -p ~/library
  %(prog)s repair_orphaned_claim_links --library-path ~/library
  %(prog)s backfill_claim_source_metadata -p ~/library --batch-size 100
  %(prog)s status --run-id abc123 -p ~/library
  %(prog)s rollback --run-id abc123 --library-path ~/library
  %(prog)s validate migrate_claims_to_multi_source -p ~/library
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "list",
            "migrate_claims_to_multi_source",
            "repair_orphaned_claim_links",
            "backfill_claim_source_metadata",
            "status",
            "rollback",
            "validate",
        ],
        help="Migration command to run",
    )

    parser.add_argument(
        "-p",
        "--library-path",
        dest="library_path",
        type=Path,
        default=None,
        help="Path to Fichero library (required for most commands)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate migration without making changes",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Process in batches of this size",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of items to process",
    )

    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Migration run ID for status/rollback commands",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def list_migrations():
    """List all available migrations."""
    migrations = [
        {
            "name": "migrate_claims_to_multi_source",
            "description": (
                "Migrate KnowledgeClaim from single-source to multi-source schema"
            ),
            "type": "data",
            "idempotent": True,
        },
        {
            "name": "backfill_claim_source_metadata",
            "description": (
                "Backfill source_metadata for claims from their source documents"
            ),
            "type": "backfill",
            "idempotent": True,
        },
        {
            "name": "repair_orphaned_claim_links",
            "description": ("Remove claim links pointing to deleted claims"),
            "type": "repair",
            "idempotent": True,
        },
    ]

    print("\nAvailable migrations:")
    print("=" * 70)
    for m in migrations:
        print(f"\n  {m['name']}")
        print(f"    Description: {m['description']}")
        print(f"    Type: {m['type']}")
        print(f"    Idempotent: {m['idempotent']}")
    print()


def run_migration(
    command: str,
    library_path: Path,
    dry_run: bool,
    batch_size: int | None,
    limit: int | None,
) -> dict:
    """Execute a migration command."""
    from fichero.db import Database
    from fichero.migrations import MigrationRunner

    logger.info(f"Opening database at {library_path}")
    db = Database(library_path)
    runner = MigrationRunner(db)

    # Set up progress callback
    def progress_callback(operation: str, current: int, total: int):
        if current % 10 == 0:  # Report every 10 items
            pct = (current / total * 100) if total > 0 else 0
            logger.info(f"{operation}: {current}/{total} ({pct:.1f}%)")

    runner.set_progress_callback(progress_callback)

    logger.info(f"Running {command} (dry_run={dry_run})")

    if command == "migrate_claims_to_multi_source":
        return runner.migrate_claims_to_multi_source(
            dry_run=dry_run, batch_size=batch_size, limit=limit
        )
    elif command == "repair_orphaned_claim_links":
        return runner.repair_orphaned_claim_links(dry_run=dry_run)
    elif command == "backfill_claim_source_metadata":
        return runner.backfill_claim_source_metadata(
            dry_run=dry_run, batch_size=batch_size
        )
    else:
        raise ValueError(f"Unknown migration: {command}")


def show_status(runner, run_id: str) -> dict:
    """Get status of a migration run."""
    return runner.get_migration_status(run_id)


def do_rollback(runner, run_id: str) -> dict:
    """Rollback a migration."""
    return runner.rollback(run_id)


def validate_migration(runner, command: str, sample_size: int = 100) -> dict:
    """Validate migration safety."""
    return runner.validate_migration_safety(command, sample_size)


def print_result(result, json_output: bool):
    """Print migration result."""
    if hasattr(result, "to_dict"):
        data = result.to_dict()
    else:
        data = result

    if json_output:
        print(json.dumps(data, indent=2, default=str))
    else:
        print("\n" + "=" * 70)
        print(f"Migration: {data.get('migration_name', 'N/A')}")
        print(f"Status: {data.get('status', 'N/A')}")
        print(f"Migrated: {data.get('migrated', 0)}")
        print(f"Skipped: {data.get('skipped', 0)}")
        print(f"Failed: {data.get('failed', 0)}")
        print(f"Dry run: {data.get('dry_run', False)}")
        print(f"Audit ID: {data.get('audit_id', 'N/A')}")
        if data.get("duration_ms"):
            print(f"Duration: {data['duration_ms']}ms")
        if data.get("error_message"):
            print(f"Error: {data['error_message']}")
        print("=" * 70 + "\n")


def main():
    """Main entry point."""
    parser = setup_argparse()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Commands that don't need a library
    if args.command == "list":
        list_migrations()
        return 0

    # Commands that need a library path
    if args.library_path is None:
        print("Error: --library-path is required for this command", file=sys.stderr)
        return 1

    library_path = Path(args.library_path).expanduser().resolve()
    if not library_path.exists():
        print(f"Error: Library path does not exist: {library_path}", file=sys.stderr)
        return 1

    from fichero.db import Database
    from fichero.migrations import MigrationRunner

    db = Database(library_path)
    runner = MigrationRunner(db)

    try:
        if args.command == "status":
            if not args.run_id:
                print("Error: --run-id required", file=sys.stderr)
                return 1
            status = show_status(runner, args.run_id)
            if status:
                print(
                    json.dumps(status, indent=2, default=str) if args.json else status
                )
            else:
                print(f"No migration found with run_id: {args.run_id}")
                return 1

        elif args.command == "rollback":
            if not args.run_id:
                print("Error: --run-id required", file=sys.stderr)
                return 1
            result = do_rollback(runner, args.run_id)
            print_result(result, args.json)
            if result.status == "failed":
                return 1

        elif args.command == "validate":
            result = validate_migration(runner, args.command)
            print(json.dumps(result, indent=2) if args.json else result)
            if not result.get("can_run", True):
                return 2

        else:  # Migration commands
            result = run_migration(
                args.command,
                library_path,
                args.dry_run,
                args.batch_size,
                args.limit,
            )
            print_result(result, args.json)
            if result.status.value == "failed":
                return 1

        return 0

    except Exception as e:
        logger.exception("Migration failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

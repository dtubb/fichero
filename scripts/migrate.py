#!/usr/bin/env python3
"""Comprehensive migration CLI for Fichero database operations.

Supports:
- Dry-run mode for validation
- Rollback of completed migrations
- Audit trail logging
- Batch operations with progress reporting
- Multiple migration types (schema, data, backfill, repair)

Usage:
    # List available migrations
    python scripts/migrate.py --list

    # Dry-run a migration to validate
    python scripts/migrate.py migrate_claims_to_multi_source --dry-run

    # Execute migration with audit trail
    python scripts/migrate.py migrate_claims_to_multi_source

    # Rollback a migration
    python scripts/migrate.py rollback --run-id MIGRATION_RUN_ID

    # Backfill operation with batch size
    python scripts/migrate.py backfill_claim_source_metadata --batch-size 100

    # Repair orphaned data
    python scripts/migrate.py repair_orphaned_claim_links --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "fichero-engine" / "src"))

from fichero.db import Database
from fichero.db.migrations.runner import MigrationRunner, MigrationResult, MigrationStatus


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("fichero.migrate")


def progress_callback(operation: str, current: int, total: int) -> None:
    """Display progress for long-running operations."""
    percent = (current / total * 100) if total > 0 else 0
    print(f"\r  {operation}: {current}/{total} ({percent:.1f}%)", end="", flush=True)


def find_library_path(library_arg: Path | None = None) -> Path:
    """Find the library database path."""
    if library_arg:
        db_path = library_arg / "fichero.duckdb"
        if not db_path.exists():
            # Try .fichero bundle
            candidates = list(library_arg.glob("*.fichero"))
            if candidates:
                db_path = candidates[0] / "fichero.duckdb"
        return db_path

    # Default: look for the default library
    default_lib = Path.home() / "Library" / "Application Support" / "Fichero"
    candidates = list(default_lib.glob("*.fichero"))
    if not candidates:
        print("ERROR: No library found. Use --library to specify.")
        sys.exit(1)
    return candidates[0] / "fichero.duckdb"


def list_migrations() -> None:
    """List available migration commands."""
    migrations = [
        ("migrate_claims_to_multi_source",
         "Migrate KnowledgeClaim from single to multi-source schema"),
        ("backfill_claim_source_metadata",
         "Backfill source_metadata from document metadata"),
        ("repair_orphaned_claim_links",
         "Remove claim links to deleted claims"),
    ]

    print("Available migrations:")
    print()
    for name, description in migrations:
        print(f"  {name:<40} {description}")
    print()
    print("Use: python scripts/migrate.py <migration_name> [--dry-run]")


def run_migration(
    runner: MigrationRunner,
    migration_name: str,
    dry_run: bool,
    batch_size: int | None,
) -> MigrationResult:
    """Run a specific migration by name."""
    if migration_name == "migrate_claims_to_multi_source":
        return runner.migrate_claims_to_multi_source(
            dry_run=dry_run, batch_size=batch_size
        )
    elif migration_name == "backfill_claim_source_metadata":
        return runner.backfill_claim_source_metadata(
            dry_run=dry_run, batch_size=batch_size
        )
    elif migration_name == "repair_orphaned_claim_links":
        return runner.repair_orphaned_claim_links(dry_run=dry_run)
    else:
        raise ValueError(f"Unknown migration: {migration_name}")


def print_result(result: MigrationResult) -> None:
    """Print migration result in a formatted way."""
    print()
    print("=" * 60)
    print(f"Migration: {result.migration_name}")
    print(f"Status: {result.status.value}")
    print(f"Dry run: {result.dry_run}")
    print("-" * 60)
    print(f"Migrated: {result.migrated}")
    print(f"Skipped:  {result.skipped}")
    print(f"Failed:   {result.failed}")
    if result.duration_ms:
        print(f"Duration: {result.duration_ms}ms")
    if result.audit_id:
        print(f"Audit ID: {result.audit_id}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fichero database migration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all migrations
  python scripts/migrate.py --list

  # Dry-run a migration
  python scripts/migrate.py migrate_claims_to_multi_source --dry-run

  # Execute migration
  python scripts/migrate.py migrate_claims_to_multi_source

  # Batch processing
  python scripts/migrate.py backfill_claim_source_metadata --batch-size 50

  # Rollback
  python scripts/migrate.py rollback --run-id abc123

  # Export audit log
  python scripts/migrate.py audit --run-id abc123 --export audit.json
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        help="Migration name or command (use --list to see options)",
    )
    parser.add_argument(
        "--library",
        type=Path,
        metavar="PATH",
        help="Path to library directory (contains .duckdb file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        metavar="N",
        help="Process in batches of N items",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available migrations",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    # Rollback subcommand
    rollback_group = parser.add_argument_group("Rollback options")
    rollback_group.add_argument(
        "--run-id",
        metavar="ID",
        help="Migration run ID to rollback or audit",
    )

    # Audit subcommand
    audit_group = parser.add_argument_group("Audit options")
    audit_group.add_argument(
        "--export",
        type=Path,
        metavar="FILE",
        help="Export audit data to JSON file",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list:
        list_migrations()
        return 0

    if not args.command:
        parser.print_help()
        return 1

    # Find and open database
    db_path = find_library_path(args.library)

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"Opening database: {db_path}")
    db = Database(db_path)
    runner = MigrationRunner(db)
    runner.set_progress_callback(progress_callback)

    try:
        if args.command == "rollback":
            if not args.run_id:
                print("ERROR: --run-id required for rollback")
                return 1

            print(f"Rolling back migration: {args.run_id}")
            result = runner.rollback(args.run_id)

            print()
            print("=" * 60)
            print(f"Rollback Status: {result.status.value}")
            print(f"Restored: {result.restored}")
            print(f"Failed: {result.failed}")
            if result.error_message:
                print(f"Error: {result.error_message}")
            print("=" * 60)

            return 0 if result.status.value == "rolled_back" else 1

        elif args.command == "audit":
            if not args.run_id:
                print("ERROR: --run-id required for audit")
                return 1

            status = runner.get_migration_status(args.run_id)
            if not status:
                print(f"ERROR: No migration found with run_id: {args.run_id}")
                return 1

            print(json.dumps(status, indent=2))

            if args.export:
                with open(args.export, "w") as f:
                    json.dump(status, f, indent=2)
                print(f"Audit exported to: {args.export}")

            return 0

        elif args.command == "validate":
            print("Validating migration safety...")
            validation = runner.validate_migration_safety(
                args.run_id or "unknown", sample_size=100
            )
            print(json.dumps(validation, indent=2))
            return 0 if validation.get("can_run", False) else 1

        else:
            # Run a migration
            result = run_migration(
                runner,
                args.command,
                args.dry_run,
                args.batch_size,
            )
            print_result(result)

            if args.export:
                with open(args.export, "w") as f:
                    json.dump(result.to_dict(), f, indent=2)
                print(f"Result exported to: {args.export}")

            return 0 if result.status == MigrationStatus.completed else 1

    except Exception as e:
        logger.exception("Migration failed")
        print(f"\nERROR: {e}")
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

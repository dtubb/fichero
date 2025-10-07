#!/usr/bin/env python3
"""
Manual GUI Test Script

This script helps verify the GUI Process button workflow by:
1. Checking if collections exist
2. Listing collection items
3. Verifying director integration is available
4. Providing debug info for manual testing

Run this to check your GUI setup before clicking Process button.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def check_gui_setup():
    """Check GUI setup for processing"""
    print("=" * 60)
    print("Fichero GUI Processing Setup Checker")
    print("=" * 60)
    print()

    # Import after adding to path
    from fichero.library.storage import LibraryStorage
    from fichero.library.library_manager import LibraryManager
    from fichero.director.director_service import FicheroDirector

    # Check 1: Database exists
    print("✓ Checking library database...")
    db_path = Path.home() / "Library/Application Support/ca.tubb.fichero/library/library.db"
    if db_path.exists():
        print(f"  ✅ Database found: {db_path}")
    else:
        print(f"  ❌ Database NOT found: {db_path}")
        print("  → Run the GUI first to create database")
        return

    # Check 2: Collections exist
    print("\n✓ Checking collections...")
    storage = LibraryStorage(db_path=str(db_path))
    collections = storage.get_all_collections()

    if not collections:
        print("  ❌ No collections found")
        print("  → Use GUI to add a collection first")
        return

    print(f"  ✅ Found {len(collections)} collection(s):")
    for i, coll in enumerate(collections, 1):
        print(f"     {i}. {coll.name} (ID: {coll.id[:8]}...)")
        print(f"        Type: {coll.type}")
        if coll.source_path:
            print(f"        Source: {coll.source_path}")

    # Check 3: Items in collections
    print("\n✓ Checking collection items...")
    for coll in collections[:3]:  # Check first 3 collections
        items = storage.get_collection_items(coll.id)
        print(f"  Collection '{coll.name}': {len(items)} items")
        if items:
            for item in items[:3]:  # Show first 3 items
                print(f"    - {item.name} ({item.type})")
                if hasattr(item, 'source_path') and item.source_path:
                    exists = Path(item.source_path).exists()
                    status = "✅" if exists else "❌"
                    print(f"      {status} Source: {item.source_path}")
        else:
            print(f"    ⚠️  No items - add items to collection or it will use folder processing")

    # Check 4: Director can initialize
    print("\n✓ Checking Director service...")
    try:
        # Mock minimal app config
        class MockApp:
            def __init__(self):
                self.paths = type('obj', (object,), {
                    'data': Path.home() / "Library/Application Support/ca.tubb.fichero"
                })()
                self.settings = None

        mock_app = MockApp()
        director = FicheroDirector(app=mock_app)
        print("  ✅ Director initialized successfully")
        print(f"     Backend: {director.backend.backend_name if hasattr(director.backend, 'backend_name') else 'python'}")
    except Exception as e:
        print(f"  ❌ Director failed to initialize: {e}")
        return

    # Check 5: Output directory
    print("\n✓ Checking output directories...")
    output_base = Path.home() / "Library/Application Support/ca.tubb.fichero/processed"
    if output_base.exists():
        print(f"  ✅ Output directory exists: {output_base}")

        # Check for existing outputs
        output_count = len(list(output_base.rglob("outputs.json")))
        if output_count > 0:
            print(f"     Found {output_count} previous processing output(s)")
        else:
            print(f"     No previous outputs (first run)")
    else:
        print(f"  ℹ️  Output directory will be created: {output_base}")

    # Check 6: Plans available
    print("\n✓ Checking processing plans...")
    plans_dir = Path(__file__).parent.parent / "src/fichero/resources/config_defaults/plans"
    if plans_dir.exists():
        plans = list(plans_dir.glob("*.yml"))
        print(f"  ✅ Found {len(plans)} plan(s):")
        for plan in plans[:5]:
            print(f"     - {plan.stem}")
    else:
        print(f"  ❌ Plans directory not found: {plans_dir}")

    # Summary
    print("\n" + "=" * 60)
    print("SETUP CHECK COMPLETE")
    print("=" * 60)
    print("\n🎯 Next Steps:")
    print("1. Launch GUI: FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev")
    print("2. Navigate to a collection")
    print("3. Click the Process button")
    print("4. Watch for:")
    print("   - Confirmation dialog")
    print("   - 'Processing Started' dialog")
    print("   - Item subtitle updates (if items exist)")
    print("   - Check logs for task progress")
    print()
    print("📋 Log file location:")
    print(f"   ~/Library/Application Support/ca.tubb.fichero/logs/")
    print()

if __name__ == "__main__":
    try:
        asyncio.run(check_gui_setup())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

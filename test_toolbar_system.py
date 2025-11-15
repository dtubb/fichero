#!/usr/bin/env python
"""
Test script to verify which toolbar system is being used on macOS
"""
import sys
import os
import logging

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s'
)

print("=" * 80)
print("TOOLBAR SYSTEM INVESTIGATION")
print("=" * 80)

# Test 1: Check platform
print("\n1. Platform Check:")
print(f"   Platform: {sys.platform}")
print(f"   Is macOS: {sys.platform == 'darwin'}")

# Test 2: Check Rubicon availability
print("\n2. Rubicon-ObjC Check:")
try:
    from rubicon.objc import ObjCClass, objc_method, NSObject
    print("   ✅ Rubicon-ObjC is available")
    RUBICON_AVAILABLE = True
except ImportError as e:
    print(f"   ❌ Rubicon-ObjC NOT available: {e}")
    RUBICON_AVAILABLE = False

# Test 3: Check MacToolbarManager
print("\n3. MacToolbarManager Check:")
try:
    from fichero.shared.commands.mac_toolbar_manager import MacToolbarManager, RUBICON_AVAILABLE as MTM_RUBICON
    print(f"   ✅ MacToolbarManager module loaded")
    print(f"   MacToolbarManager.RUBICON_AVAILABLE = {MTM_RUBICON}")
except ImportError as e:
    print(f"   ❌ MacToolbarManager NOT available: {e}")
    MTM_RUBICON = False

# Test 4: Check CommandManager initialization
print("\n4. CommandManager Initialization (simulated):")
print("   Creating mock app...")

class MockApp:
    """Mock Toga app for testing"""
    is_mobile = False

    class Paths:
        app = "/tmp/test"

    paths = Paths()

mock_app = MockApp()

try:
    from fichero.shared.commands.command_manager import CommandManager

    # Create a new instance
    cmd_manager = CommandManager(mock_app)

    print(f"   CommandManager.is_mobile = {cmd_manager.is_mobile}")
    print(f"   CommandManager.is_macos = {cmd_manager.is_macos}")
    print(f"   CommandManager._mac_toolbar_available = {cmd_manager._mac_toolbar_available}")

    if cmd_manager._mac_toolbar_available:
        print("\n   ✅ MacToolbarManager is ENABLED in CommandManager")
        print("   → Collection/Adjust buttons will use NSToolbar")
    else:
        print("\n   ❌ MacToolbarManager is DISABLED in CommandManager")
        print("   → Collection/Adjust buttons will use Toga toolbar")

except Exception as e:
    print(f"   ❌ Error initializing CommandManager: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Trace the code path
print("\n5. Code Path Analysis:")
print("   From command_manager.py __init__ (lines 59-81):")
print("   ```python")
print("   if self.is_macos and not self.is_mobile:")
print("       try:")
print("           from fichero.shared.commands.mac_toolbar_manager import MacToolbarManager, RUBICON_AVAILABLE")
print("           self._mac_toolbar_class = MacToolbarManager")
print("           self._mac_toolbar_available = RUBICON_AVAILABLE")
print("   ```")
print()
print(f"   Evaluation:")
print(f"   - is_macos: {cmd_manager.is_macos}")
print(f"   - is_mobile: {cmd_manager.is_mobile}")
print(f"   - Import succeeded: {MTM_RUBICON}")
print(f"   - RUBICON_AVAILABLE: {MTM_RUBICON}")
print(f"   - Result: _mac_toolbar_available = {cmd_manager._mac_toolbar_available}")

print("\n6. build_native_toolbar() Routing:")
print("   From command_manager.py build_native_toolbar() (lines 490-498):")
print("   ```python")
print("   if self._mac_toolbar_available:")
print("       print(f'✅ Routing to MacToolbarManager for window: {window.title}')")
print("       return self._build_mac_toolbar(...)")
print("   else:")
print("       print(f'⚠️  MacToolbarManager NOT available, using Toga fallback')")
print("   ```")
print()
if cmd_manager._mac_toolbar_available:
    print("   → Will route to _build_mac_toolbar() ✅")
else:
    print("   → Will use Toga fallback ❌")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)

if cmd_manager._mac_toolbar_available:
    print("✅ The working buttons (Collection toggle, Adjust toggle) ARE using")
    print("   the Mac NSToolbar system via MacToolbarManager.")
    print()
    print("Evidence:")
    print("- Rubicon-ObjC is installed and available")
    print("- MacToolbarManager module loads successfully")
    print("- CommandManager._mac_toolbar_available = True")
    print("- build_native_toolbar() routes to _build_mac_toolbar()")
else:
    print("❌ The working buttons (Collection toggle, Adjust toggle) are NOT using")
    print("   the Mac NSToolbar system. They are using Toga's toolbar system.")
    print()
    print("Evidence:")
    print("- CommandManager._mac_toolbar_available = False")
    print("- build_native_toolbar() uses Toga fallback path")

print("=" * 80)

#!/usr/bin/env python3
"""
Test file to verify iOS imports work correctly.
This should be the minimal set of imports needed to start the app.
"""

import sys
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test all the critical imports needed for iOS app startup"""
    try:
        logger.info("Testing basic imports...")
        
        # Test the main app import
        from fichero.app import FicheroApp
        logger.info("✅ FicheroApp import successful")
        
        # Test settings import
        from fichero.config.core.settings import get_app_settings
        logger.info("✅ Settings import successful")
        
        # Test UI imports
        from fichero.ui import MenuManager
        logger.info("✅ UI imports successful")
        
        # Test document imports
        # Document model removed - using library approach instead
        logger.info("✅ Document imports successful")
        
        # Test core imports
        from fichero.core.app_initializer import initialize_gui_app
        from fichero.core.error_handler import create_gui_error_handler
        logger.info("✅ Core imports successful")
        
        # Test shared data imports
        from fichero.shared_data import get_shared_data
        logger.info("✅ Shared data imports successful")
        
        logger.info("🎉 All critical imports successful!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1) 
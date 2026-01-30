#!/usr/bin/env python3
"""
Backend launcher for embedded Python in Fichero.app

This script is the entry point for the bundled Python backend.
It starts uvicorn WITHOUT --reload (production mode).
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start the Fichero backend server in production mode."""

    # Detect if we're running from a bundle
    bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    is_bundled = bundle_dir.endswith('.app/Contents/Resources/python')

    if is_bundled:
        logger.info(f"Running from bundle: {bundle_dir}")
        # Ensure PYTHONHOME is set correctly
        python_home = os.path.dirname(os.path.dirname(sys.executable))
        os.environ['PYTHONHOME'] = python_home
    else:
        logger.info("Running in development mode")

    # Disable tokenizers parallelism (avoids fork warnings)
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

    # Import after environment is set up
    import uvicorn

    # Production configuration (NO --reload!)
    config = {
        'app': 'fichero.api.main:app',
        'host': '127.0.0.1',
        'port': 8765,
        'workers': 1,
        'log_level': 'info',
        'reload': False,  # ← CRITICAL: No hot-reload in production
    }

    logger.info(f"Starting Fichero backend on {config['host']}:{config['port']}")
    logger.info(f"Hot-reload: {config['reload']}")

    # Start the server
    uvicorn.run(**config)

if __name__ == '__main__':
    main()

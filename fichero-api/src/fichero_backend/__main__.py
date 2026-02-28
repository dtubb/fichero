"""
Fichero Backend Entry Point

Starts the FastAPI backend server in production mode (no hot-reload).
This is the entry point when running as a Briefcase app.
"""

import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start the Fichero API backend server."""

    # Disable tokenizers parallelism (avoids fork warnings)
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

    # Import uvicorn
    import uvicorn

    logger.info("Starting Fichero Backend (Briefcase bundle)")
    logger.info("Server will listen on http://127.0.0.1:8765")
    logger.info("Hot-reload: DISABLED (production mode)")

    # Start server - NO --reload flag!
    try:
        uvicorn.run(
            "fichero.api.main:app",
            host="127.0.0.1",
            port=8765,
            workers=1,
            log_level="info",
            reload=False,  # ← PRODUCTION MODE
        )
    except KeyboardInterrupt:
        logger.info("Backend shutting down...")
    except Exception as e:
        logger.error(f"Backend failed to start: {e}")
        raise


if __name__ == "__main__":
    main()

"""
Fichero App Initializer - Shared Initialization System

Complete initialization system that both GUI (app.py) and CLI (cli.py) delegate to.
Both interfaces are thin wrappers that call this shared system for ALL setup:
- Logging configuration (comprehensive for GUI, basic for CLI)
- Settings and preferences (with app preferences integration)
- Shared data backend (Redis/Manager selection based on settings)
- Director service (with backend initialization - MUST succeed)
- Language/i18n system (GUI only)
- Document system (GUI only - tracker, auto-save, session manager)

GUI and CLI do NOT configure these themselves - they delegate everything here.
This ensures zero duplication and identical initialization across interfaces.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class FicheroAppInitializer:
    """
    Thin wrapper for Fichero app initialization.
    
    Handles all the complex setup logic that both GUI and CLI need:
    - Settings and environment variables
    - Shared data backend (Redis/Manager)
    - Director service initialization
    - Language/i18n system
    - Logging configuration
    - Proper cleanup
    """
    
    def __init__(self, app_context=None, cli_mode=False, data_dir=None):
        """
        Initialize the app initializer.
        
        Args:
            app_context: Toga app instance (for GUI) or None (for CLI)
            cli_mode: True if running in CLI mode
            data_dir: Override data directory (for CLI)
        """
        self.app_context = app_context
        self.cli_mode = cli_mode
        self.data_dir = data_dir
        
        # Initialized components (for cleanup)
        self.settings = None
        self.director = None
        # Document system components removed - using library approach
        
        # Backend selection (unified)
        self.processing_backend = None
        self.storage_backend = None
        
        logger.info(f"🔧 Initializing Fichero ({'CLI' if cli_mode else 'GUI'} mode)")
    
    def initialize_full_app(self, additional_settings: Dict = None) -> Dict[str, Any]:
        """
        Initialize complete Fichero application (GUI or CLI).
        
        Args:
            additional_settings: Additional settings to merge (e.g., CLI overrides)
            
        Returns:
            Dictionary with initialized components
        """
        try:
            # 1. Configure logging first
            if self.cli_mode:
                self._setup_basic_logging()
            else:
                self._setup_logging()
            
            # 2. Initialize settings and preferences
            self.settings = self._init_settings(additional_settings)
            

            
            # 4. Select unified backends (single source of truth)
            self.processing_backend, self.storage_backend = self._select_unified_backends()
            
            # 5. Initialize director service with selected backend
            self.director = self._init_director_service()
            
            # 6. Initialize shared data backend with selected backend
            self._init_shared_data_backend()
            
            # 6. Initialize document system (GUI only)
            if not self.cli_mode and self.app_context:
                self._init_document_system()
            
            logger.info("✨ Fichero initialization completed successfully!")
            
            return {
                'settings': self.settings,
                'director': self.director
            }
            
        except Exception as e:
            logger.error(f"❌ Fichero initialization failed: {e}")
            raise
    
    def cleanup(self):
        """Clean up all initialized components"""
        logger.info("🧹 Cleaning up Fichero components...")
        
        try:
            # Shutdown director service
            if self.director:
                logger.info("🧹 Shutting down director service...")
                self.director.shutdown()
                logger.info("✓ Director service shutdown completed")
            
            # Cleanup shared data backend
            try:
                from fichero.shared_data import get_shared_data
                shared_data = get_shared_data()
                
                # Check if the shared data object has a cleanup method
                if hasattr(shared_data, 'cleanup'):
                    logger.info("🧹 Cleaning up shared data...")
                    shared_data.cleanup()
                    logger.info("✓ Shared data cleanup completed")
                elif hasattr(shared_data, 'backend') and hasattr(shared_data.backend, 'cleanup'):
                    # Legacy support for objects with backend attribute
                    logger.info("🧹 Cleaning up shared data backend...")
                    shared_data.backend.cleanup()
                    logger.info("✓ Shared data backend cleanup completed")
                else:
                    logger.debug("🧹 No cleanup method found for shared data - skipping")
                    
            except Exception as e:
                logger.warning(f"⚠️ Shared data cleanup failed: {e}")
            
            # Cleanup document system (GUI only)
            if not self.cli_mode:
                # Document managers handle their own cleanup
                pass
            
            logger.info("✓ Fichero cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
    
    # Private initialization methods
    
    def _setup_logging(self):
        """Set up comprehensive logging for GUI"""
        import sys
        import os
        
        # Detect if running as bundled GUI app (avoid system logging)
        is_bundled_app = getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS')
        is_gui_app = not sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else True
        
        if is_bundled_app or is_gui_app:
            # For GUI apps: log to file only (avoid system logging that triggers briefcase log stream)
            self._setup_file_logging()
        else:
            # For development: use standard logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        logger.info("📝 GUI logging configured (file-based for bundled apps)")
    
    def _setup_file_logging(self):
        """Set up file-based logging for GUI apps (avoids system logging)"""
        import tempfile
        from pathlib import Path
        
        # Create logs directory in user data location
        if self.app_context:
            # Use app's data directory
            logs_dir = Path(self.app_context.paths.data) / "logs"
        else:
            # Fallback to temp directory
            logs_dir = Path(tempfile.gettempdir()) / "fichero_logs"
        
        logs_dir.mkdir(exist_ok=True)
        
        # Create timestamped log file
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"fichero_{timestamp}.log"
        
        # Configure file-based logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                # Add minimal console handler for critical errors only
                logging.StreamHandler()
            ]
        )
        
        # Set console handler to show info messages for debugging
        console_handler = logging.getLogger().handlers[-1]
        console_handler.setLevel(logging.INFO)  # Temporarily show info messages
        
        logger.info(f"📁 File logging configured: {log_file}")
    
    def _setup_basic_logging(self, verbose=False):
        """Set up basic logging for CLI"""
        # Always use ERROR level for CLI to see what's happening
        level = logging.ERROR
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True  # Force reconfiguration if already set
        )
        
        # Set specific loggers to ERROR level
        logging.getLogger('fichero').setLevel(logging.ERROR)
        logging.getLogger('fichero.cli').setLevel(logging.ERROR)
        logging.getLogger('fichero.core').setLevel(logging.ERROR)
        logging.getLogger('fichero.director').setLevel(logging.ERROR)
        
        logger.info(f"📝 CLI logging configured (ERROR mode)")
        logger.debug("🔍 Debug logging enabled for CLI troubleshooting")
    
    def _init_settings(self, additional_settings: Dict = None):
        """Initialize full application settings and preferences"""
        try:
            # Initialize app preferences first
            from fichero.config.core.app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app_context)
            logger.info("📋 App preferences initialized")
            
            # Load settings (environment variables set automatically)
            from fichero.config.core.settings import get_app_settings
            settings = get_app_settings(self.app_context)
            
            # Merge additional settings (e.g., CLI overrides) - let settings handle this
            if additional_settings:
                settings.merge_overrides(additional_settings)
                logger.info(f"🔧 Applied settings overrides: {additional_settings}")
            
            return settings
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load full settings: {e}")
            return None
    

    
    def _select_unified_backends(self):
        """Select unified backends using single source of truth"""
        try:
            from fichero.director.backends.backend_selector import BackendSelector
            
            # Use unified backend selector
            processing_backend, storage_backend = BackendSelector.select_backends(self.settings)
            
            # Log the unified selection
            backend_info = BackendSelector.get_backend_info(processing_backend, storage_backend)
            logger.info(f"🔧 Unified backend selection:")
            logger.info(f"   Processing: {backend_info['processing']['description']}")
            logger.info(f"   Storage: {backend_info['storage']['description']}")
            logger.info(f"   Infrastructure: {backend_info['infrastructure']}")
            
            return processing_backend, storage_backend
            
        except Exception as e:
            logger.warning(f"⚠️ Unified backend selection failed: {e}, using Python fallback")
            return "python", "manager"
    
    def _init_shared_data_backend(self):
        """Initialize shared data backend using unified backend selection"""
        try:
            # Use the selected storage backend
            prefer_backend = self.storage_backend  # "redis" or "threading"
            
            # Initialize shared data with selected backend
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data(prefer_backend=prefer_backend)
            
            logger.info(f"🔧 Shared data backend initialized: {shared_data.backend_name} (unified selection)")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize shared data backend: {e}")
    
    def _init_director_service(self):
        """Initialize director service using unified backend selection"""
        try:
            from fichero.director import FicheroDirector
            
            # Create director instance with settings object
            director = FicheroDirector.get_instance(settings=self.settings, app=self.app_context)
            
            # Set the unified backend selection hint
            director._preferred_backend = self.processing_backend  # "celery" or "python"
            
            # Initialize backend - this MUST succeed
            backend_initialized = director.initialize_backend()
            
            if backend_initialized:
                logger.info(f"🎯 Director service initialized successfully!")
                logger.info(f"🎯 Backend: {director.backend.backend_name} (unified selection)")
                
                # Verify backend matches unified selection
                actual_backend = "celery" if "celery" in director.backend.backend_name.lower() or "redis" in director.backend.backend_name.lower() else "python"
                if actual_backend == self.processing_backend:
                    logger.info(f"✅ Director backend matches unified selection: {actual_backend}")
                else:
                    logger.warning(f"⚠️ Director backend mismatch: expected {self.processing_backend}, got {actual_backend}")
                
                return director
            else:
                # Director backend failure is FATAL - the app cannot function
                error_msg = "Director backend initialization failed. Cannot process documents without working backend."
                logger.error(f"❌ {error_msg}")
                raise RuntimeError(error_msg)
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize director service: {e}")
            raise  # Re-raise to make it fatal
    
    def _init_document_system(self):
        """Initialize document system (GUI only) - DISABLED for library approach"""
        # Document system removed - using library approach instead
        logger.info("📄 Document system disabled - using library approach")
    



# Convenience functions for easy use

def initialize_gui_app(app_context, additional_settings=None):
    """
    Initialize GUI application with full features.
    
    Args:
        app_context: Toga app instance
        additional_settings: Additional settings to merge
        
    Returns:
        Dictionary with initialized components
    """
    initializer = FicheroAppInitializer(app_context=app_context, cli_mode=False)
    return initializer.initialize_full_app(additional_settings), initializer

def initialize_cli_app(cli_settings=None, data_dir=None):
    """
    Initialize CLI application with full features (same as GUI minus GUI-specific components).
    
    Args:
        cli_settings: CLI-specific settings
        data_dir: Override data directory
        
    Returns:
        Tuple of (components_dict, initializer)
    """
    initializer = FicheroAppInitializer(cli_mode=True, data_dir=data_dir)
    components = initializer.initialize_full_app(cli_settings)
    return components, initializer 
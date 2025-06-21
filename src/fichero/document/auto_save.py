"""
Document Auto-Save Management
Handles automatic saving of documents and temporary document storage
"""

import logging
import shutil
import datetime
import yaml
import time
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class AutoSaveManager:
    """Manages auto-saving functionality for documents"""
    
    def __init__(self, document):
        self.document = document
        self.auto_save_path: Optional[Path] = None
        self.is_auto_saved = False
    
    def setup_auto_save_path(self) -> bool:
        """Set up auto-save path for new documents"""
        try:
            app_ref = getattr(self.document, 'app', getattr(self.document, '_temp_app', getattr(self.document, '_app', None)))
            if app_ref and hasattr(app_ref, 'paths'):
                # Create auto-save directory
                auto_save_dir = app_ref.paths.data / "documents"
                auto_save_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate unique filename
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                document_name = f"Untitled_{timestamp}_{self.document.document_id[:8]}.fichero"
                
                self.auto_save_path = auto_save_dir / document_name
                # Don't mark as auto-saved until first save happens
                self.is_auto_saved = False
                
                logger.info(f"Auto-save path set up: {self.auto_save_path}")
                return True
            else:
                logger.warning("Cannot set up auto-save: no app paths available")
                return False
        except Exception as e:
            logger.error(f"Failed to set up auto-save path: {e}")
            return False
    
    def auto_save(self) -> bool:
        """Auto-save the document to the auto-save location"""
        if not self.auto_save_path:
            logger.warning("Cannot auto-save: no auto-save path available")
            return False
        
        try:
            # Ensure auto-save directory exists
            self.auto_save_path.mkdir(parents=True, exist_ok=True)
            
            # Update document config with auto-save path info
            self.document.state_manager.document_config["title"] = self.auto_save_path.stem
            if "vars" in self.document.state_manager.plans_config:
                self.document.state_manager.plans_config["vars"]["name"] = self.auto_save_path.stem
                self.document.state_manager.plans_config["vars"]["project_folder"] = str(self.auto_save_path)
                self.document.state_manager.plans_config["vars"]["documents_folder"] = str(self.auto_save_path / "documents")
                self.document.state_manager.plans_config["vars"]["assets_folder"] = str(self.auto_save_path / "assets")
            
            # Save configuration files to auto-save location
            plans_file = self.auto_save_path / "plans.yml"
            with open(plans_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.document.state_manager.plans_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            config_file = self.auto_save_path / "document_config.yml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.document.state_manager.document_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            # Create basic directory structure
            (self.auto_save_path / "documents").mkdir(exist_ok=True)
            (self.auto_save_path / "assets").mkdir(exist_ok=True)
            
            # Mark as auto-saved now that we've actually saved it
            self.is_auto_saved = True
            self.document.is_modified = False
            logger.info(f"Auto-saved document to: {self.auto_save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to auto-save document: {e}")
            return False
    
    def get_effective_path(self) -> Optional[Path]:
        """Get the effective path (either user-set path or auto-save path)"""
        if hasattr(self.document, 'path') and self.document.path:
            return self.document.path
        elif self.auto_save_path:
            return self.auto_save_path
        return None
    
    def cleanup_auto_save(self):
        """Clean up auto-save files when document is explicitly saved"""
        if self.is_auto_saved and self.auto_save_path and self.auto_save_path.exists():
            try:
                shutil.rmtree(self.auto_save_path)
                logger.info(f"Cleaned up auto-save file: {self.auto_save_path}")
                self.is_auto_saved = False
                self.auto_save_path = None
            except Exception as e:
                logger.warning(f"Failed to clean up auto-save file: {e}")
    
    def reset_auto_save(self):
        """Reset auto-save for a fresh document"""
        try:
            # Clean up the old auto-save directory
            if self.auto_save_path and self.auto_save_path.exists():
                shutil.rmtree(self.auto_save_path)
                logger.info(f"Cleaned up old auto-save: {self.auto_save_path}")
            
            # Create a fresh auto-save path
            self.setup_auto_save_path()
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset auto-save: {e}")
            return False
    
    def add_document_file(self, file_path: Path) -> bool:
        """Add a file to the document's documents folder and trigger auto-save"""
        try:
            if self.auto_save_path:
                documents_dir = self.auto_save_path / "documents"
                documents_dir.mkdir(exist_ok=True)
                
                destination = documents_dir / file_path.name
                shutil.copy2(file_path, destination)
                
                self.document.mark_modified()
                logger.info(f"Added file to document: {file_path.name}")
                return True
            else:
                logger.warning("Cannot add file: no auto-save path available")
                return False
        except Exception as e:
            logger.error(f"Failed to add file to document: {e}")
            return False


class AppAutoSaveManager:
    """Manages app-level auto-save operations and cleanup"""
    
    def __init__(self, app):
        self.app = app
        # Auto-cleanup on initialization - no manual orchestration needed
        self._startup_cleanup()
    
    def _startup_cleanup(self):
        """Perform automatic cleanup during initialization"""
        try:
            logger.info("Performing auto-save cleanup during startup...")
            self.clean_old_auto_saves(days_old=30)
            self.clean_empty_auto_saves()
            logger.info("Auto-save cleanup completed")
        except Exception as e:
            logger.warning(f"Auto-save cleanup failed: {e}")
    
    def get_auto_saved_documents(self) -> List[Path]:
        """Get list of auto-saved documents"""
        try:
            auto_save_dir = self.app.paths.data / "documents"
            if auto_save_dir.exists():
                auto_saved = []
                for doc_path in auto_save_dir.iterdir():
                    if doc_path.is_dir() and doc_path.suffix == ".fichero":
                        # Check if it's a valid fichero document
                        if (doc_path / "plans.yml").exists() and (doc_path / "document_config.yml").exists():
                            auto_saved.append(doc_path)
                return sorted(auto_saved, key=lambda x: x.stat().st_mtime, reverse=True)
            return []
        except Exception as e:
            logger.error(f"Failed to get auto-saved documents: {e}")
            return []
    
    def clean_old_auto_saves(self, days_old: int = 30):
        """Clean up auto-saved documents older than specified days"""
        try:
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)
            
            auto_save_dir = self.app.paths.data / "documents"
            if auto_save_dir.exists():
                cleaned_count = 0
                for doc_path in auto_save_dir.iterdir():
                    if doc_path.is_dir() and doc_path.suffix == ".fichero":
                        if doc_path.stat().st_mtime < cutoff_time:
                            try:
                                shutil.rmtree(doc_path)
                                cleaned_count += 1
                                logger.info(f"Cleaned old auto-save: {doc_path.name}")
                            except Exception as e:
                                logger.warning(f"Failed to clean {doc_path.name}: {e}")
                
                if cleaned_count > 0:
                    logger.info(f"Cleaned {cleaned_count} old auto-saved documents")
                else:
                    logger.info("No old auto-saved documents to clean")
                    
        except Exception as e:
            logger.error(f"Failed to clean old auto-saves: {e}")
    
    def clean_empty_auto_saves(self):
        """Clean up empty auto-saved documents that have no meaningful content"""
        try:
            auto_save_dir = self.app.paths.data / "documents"
            if auto_save_dir.exists():
                cleaned_count = 0
                for doc_path in auto_save_dir.iterdir():
                    if doc_path.is_dir() and doc_path.suffix == ".fichero":
                        try:
                            # Check if this is an empty auto-saved document
                            config_file = doc_path / "document_config.yml"
                            plans_file = doc_path / "plans.yml"
                            
                            is_empty = True
                            
                            if config_file.exists():
                                with open(config_file, 'r') as f:
                                    config_data = yaml.safe_load(f) or {}
                                
                                # Check basic fields
                                if config_data.get('description', '').strip():
                                    is_empty = False
                                if config_data.get('title', 'Untitled') not in ['Untitled', 'New Document']:
                                    is_empty = False
                                
                                # Check processing settings
                                processing_settings = config_data.get('processing_settings', {})
                                if processing_settings.get('input_folder', '').strip():
                                    is_empty = False
                                if processing_settings.get('selected_plan', 'Default Plan') != 'Default Plan':
                                    is_empty = False
                                if processing_settings.get('selected_workflow', 'default') != 'default':
                                    is_empty = False
                                if processing_settings.get('custom_steps', []):
                                    is_empty = False
                                if processing_settings.get('workflow_variables', {}):
                                    is_empty = False
                            
                            if plans_file.exists() and is_empty:
                                with open(plans_file, 'r') as f:
                                    plans_data = yaml.safe_load(f) or {}
                                # Check if title was changed from default
                                if plans_data.get('title', '') not in ['New Document', '']:
                                    is_empty = False
                            
                            # Also check if documents folder has any files
                            documents_dir = doc_path / "documents"
                            if documents_dir.exists() and any(documents_dir.iterdir()):
                                is_empty = False
                            
                            if is_empty:
                                shutil.rmtree(doc_path)
                                cleaned_count += 1
                                logger.info(f"Cleaned empty auto-save: {doc_path.name}")
                                
                        except Exception as e:
                            logger.warning(f"Failed to check/clean {doc_path.name}: {e}")
                
                if cleaned_count > 0:
                    logger.info(f"Cleaned {cleaned_count} empty auto-saved documents")
                    
        except Exception as e:
            logger.error(f"Failed to clean empty auto-saves: {e}")


# Global app auto-save manager instance
_app_auto_save_manager: Optional[AppAutoSaveManager] = None

def get_app_auto_save_manager(app=None) -> Optional[AppAutoSaveManager]:
    """Get the global app auto-save manager instance"""
    global _app_auto_save_manager
    if _app_auto_save_manager is None and app:
        _app_auto_save_manager = AppAutoSaveManager(app)
    return _app_auto_save_manager

def init_app_auto_save_manager(app):
    """Initialize the global app auto-save manager"""
    global _app_auto_save_manager
    _app_auto_save_manager = AppAutoSaveManager(app)
    return _app_auto_save_manager 
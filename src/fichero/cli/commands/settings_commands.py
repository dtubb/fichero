"""
CLI Settings Commands - Schema-Driven Configuration

Reads settings_schema.yml to generate dynamic CLI configure commands.
Provides comprehensive settings management from command line using
the same validation and structure as the GUI.
"""

import logging
from fichero.utils import yaml_compat as yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import typer
from rich.console import Console
from rich.table import Table

from fichero.core.error_handler import create_cli_error_handler
from fichero.config.core.settings import get_app_settings

logger = logging.getLogger(__name__)


class CLISettingsCommands:
    """Schema-driven CLI settings configuration commands"""
    
    def __init__(self, director, console: Console):
        self.director = director
        self.console = console
        self.error_handler = create_cli_error_handler(console)
        self.settings_schema = self._load_settings_schema()
        
    def _load_settings_schema(self) -> Dict[str, Any]:
        """Load the settings schema from YAML file"""
        try:
            # Find schema file relative to this module
            schema_path = Path(__file__).parent.parent.parent / "resources" / "config_ui_schemas" / "settings_schema.yml"
            
            if not schema_path.exists():
                logger.error(f"Settings schema not found: {schema_path}")
                return {}
                
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = yaml.safe_load(f)
                logger.info(f"✅ Loaded settings schema with {len(schema.get('sections', []))} sections")
                return schema
                
        except Exception as e:
            logger.error(f"Failed to load settings schema: {e}")
            return {}
    
    def _get_all_fields(self) -> List[Dict[str, Any]]:
        """Extract all fields from the schema with their metadata"""
        fields = []
        
        def extract_fields_from_sections(sections):
            for section in sections:
                # Handle nested sections
                if 'sections' in section:
                    extract_fields_from_sections(section['sections'])
                
                # Handle fields in this section
                if 'fields' in section:
                    for field in section['fields']:
                        if field.get('type') != 'button':  # Skip buttons
                            fields.append(field)
        
        if 'sections' in self.settings_schema:
            extract_fields_from_sections(self.settings_schema['sections'])
            
        return fields
    
    def configure_backend(self, backend: str):
        """Configure backend type (python or redis/celery)"""
        try:
            if backend not in ['python', 'redis', 'celery']:
                self.console.print("❌ Invalid backend. Choose 'python' or 'redis/celery'", style="red")
                return False
                
            # Normalize celery to redis for consistency
            normalized_backend = 'redis' if backend == 'celery' else backend
            
            # Get current settings
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            app_settings.set_setting('workers.backend', normalized_backend)
            
            # Save settings
            success = app_settings.save()
            if success:
                self.console.print(f"✅ Backend updated to: {backend}", style="green")
                return True
            else:
                self.console.print(f"❌ Failed to save backend setting", style="red")
                return False
                
        except Exception as e:
            self.error_handler.handle_general_exception(e, "configuring backend")
            return False
    
    def configure_workers(self, cpu_workers: Optional[int] = None, io_workers: Optional[int] = None):
        """Configure worker counts"""
        try:
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            
            if cpu_workers is not None:
                if cpu_workers < 1 or cpu_workers > 32:
                    self.console.print("❌ CPU workers must be between 1 and 32", style="red")
                    return False
                app_settings.set_setting('workers.cpu_workers', cpu_workers)
                self.console.print(f"✅ CPU workers set to: {cpu_workers}", style="green")
            
            if io_workers is not None:
                if io_workers < 1 or io_workers > 128:
                    self.console.print("❌ I/O workers must be between 1 and 128", style="red")
                    return False
                app_settings.set_setting('workers.io_workers', io_workers)
                self.console.print(f"✅ I/O workers set to: {io_workers}", style="green")
            
            # Save settings
            success = app_settings.save()
            if not success:
                self.console.print("❌ Failed to save worker settings", style="red")
                return False
                
            return True
            
        except Exception as e:
            self.error_handler.handle_general_exception(e, "configuring workers")
            return False
    
    def configure_api_key(self, provider: str, api_key: str):
        """Configure API key for a provider"""
        try:
            # Validate provider
            valid_providers = ['openai', 'qwen', 'claude', 'huggingface']
            if provider not in valid_providers:
                self.console.print(f"❌ Invalid provider. Choose from: {', '.join(valid_providers)}", style="red")
                return False
            
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            app_settings.set_setting(f'api_servers.{provider}.api_key', api_key)
            
            # Save settings
            success = app_settings.save()
            if success:
                # Show masked key for security
                masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
                self.console.print(f"✅ {provider.title()} API key updated: {masked_key}", style="green")
                return True
            else:
                self.console.print(f"❌ Failed to save {provider} API key", style="red")
                return False
                
        except Exception as e:
            self.error_handler.handle_general_exception(e, f"configuring {provider} API key")
            return False
    
    def configure_preference(self, setting_path: str, value: Any):
        """Configure a preference setting"""
        try:
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            app_settings.set_setting(setting_path, value)
            
            # Save settings
            success = app_settings.save()
            if success:
                self.console.print(f"✅ {setting_path} updated to: {value}", style="green")
                return True
            else:
                self.console.print(f"❌ Failed to save {setting_path}", style="red")
                return False
                
        except Exception as e:
            self.error_handler.handle_general_exception(e, f"configuring {setting_path}")
            return False
    
    def show_current_settings(self, show_api_keys: bool = False):
        """Display current settings in comprehensive formatted tables"""
        try:
            app_settings = get_app_settings(self.director.app if hasattr(self.director, 'app') else None)
            
            # === BACKEND & PERFORMANCE SETTINGS ===
            backend_table = Table(title="Backend & Performance Settings")
            backend_table.add_column("Setting", style="cyan")
            backend_table.add_column("Value", style="green")
            backend_table.add_column("Description", style="yellow")
            
            # Backend settings
            backend = app_settings.get_setting('workers.backend', 'python')
            cpu_workers = app_settings.get_setting('workers.cpu_workers', 4)
            io_workers = app_settings.get_setting('workers.io_workers', 16)
            
            backend_table.add_row("Backend", backend, "Processing backend type")
            backend_table.add_row("CPU Workers", str(cpu_workers), "CPU-intensive processing workers")
            backend_table.add_row("I/O Workers", str(io_workers), "I/O workers for API calls")
            
            self.console.print(backend_table)
            
            # === DEFAULTS & PREFERENCES ===
            prefs_table = Table(title="Defaults & Preferences")
            prefs_table.add_column("Setting", style="cyan")
            prefs_table.add_column("Value", style="green")
            prefs_table.add_column("Description", style="yellow")
            
            # Defaults
            default_plan = app_settings.get_setting('defaults.plan', 'Catalogue')
            default_workflow = app_settings.get_setting('defaults.workflow', '00) default')
            
            prefs_table.add_row("Default Plan", default_plan, "Plan used when none specified")
            prefs_table.add_row("Default Workflow", default_workflow, "Workflow used when none specified")
            
            # Preferences
            language = app_settings.get_setting('preferences.language', 'en')
            folder_order = app_settings.get_setting('preferences.folder_processing_order', 'alphabetical')
            
            prefs_table.add_row("Language", language, "Interface language")
            prefs_table.add_row("Folder Order", folder_order, "Folder processing order")
            
            self.console.print(prefs_table)
            
            # === API SERVERS ===
            api_table = Table(title="API Server Configuration")
            api_table.add_column("Provider", style="cyan")
            api_table.add_column("Base URL", style="blue")
            api_table.add_column("API Key Status", style="green")
            if show_api_keys:
                api_table.add_column("Key Preview", style="yellow")
            
            # All API providers with their URLs
            providers = {
                'openai': 'OpenAI',
                'qwen': 'Qwen (Alibaba)',
                'claude': 'Claude (Anthropic)',
                'huggingface': 'Hugging Face',
                'ollama': 'Ollama (Local)',
                'lmstudio': 'LM Studio (Local)',
                'blackfish': 'Blackfish (Custom)'
            }
            
            for provider_key, provider_name in providers.items():
                base_url = app_settings.get_setting(f'api_servers.{provider_key}.base_url', '—')
                api_key = app_settings.get_setting(f'api_servers.{provider_key}.api_key', '')
                
                # API key status
                if api_key:
                    key_status = "✅ Set"
                    if show_api_keys:
                        preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
                else:
                    key_status = "❌ Not set"
                    if show_api_keys:
                        preview = "—"
                
                # Add row
                if show_api_keys:
                    api_table.add_row(provider_name, base_url, key_status, preview)
                else:
                    api_table.add_row(provider_name, base_url, key_status)
            
            self.console.print(api_table)
            
            # === SUMMARY ===
            summary_table = Table(title="Configuration Summary")
            summary_table.add_column("Category", style="cyan")
            summary_table.add_column("Status", style="green")
            
            # Count configured API keys
            configured_keys = 0
            for provider in ['openai', 'qwen', 'claude', 'huggingface']:
                if app_settings.get_setting(f'api_servers.{provider}.api_key', ''):
                    configured_keys += 1
            
            summary_table.add_row("Backend", f"✅ {backend.title()}")
            summary_table.add_row("Workers", f"✅ {cpu_workers} CPU, {io_workers} I/O")
            summary_table.add_row("Defaults", f"✅ {default_plan} / {default_workflow}")
            summary_table.add_row("API Keys", f"✅ {configured_keys}/4 configured")
            summary_table.add_row("Language", f"✅ {language.upper()}")
            
            self.console.print(summary_table)
            
            return True
            
        except Exception as e:
            self.error_handler.handle_general_exception(e, "showing settings")
            return False
    
    def show_available_options(self):
        """Show all available configuration options from schema"""
        try:
            if not self.settings_schema:
                self.console.print("❌ Settings schema not available", style="red")
                return False
            
            table = Table(title="Available Configuration Options")
            table.add_column("Command", style="cyan")
            table.add_column("Description", style="green")
            table.add_column("Example", style="yellow")
            
            # Add common commands
            table.add_row("--backend", "Set backend type", "fichero configure --backend python")
            table.add_row("--cpu-workers", "Set CPU worker count", "fichero configure --cpu-workers 8")
            table.add_row("--io-workers", "Set I/O worker count", "fichero configure --io-workers 16")
            table.add_row("--language", "Set interface language", "fichero configure --language es")
            table.add_row("--folder-order", "Set folder processing order", "fichero configure --folder-order least_images_first")
            table.add_row("--openai-key", "Set OpenAI API key", "fichero configure --openai-key sk-xxx")
            table.add_row("--qwen-key", "Set Qwen API key", "fichero configure --qwen-key sk-yyy")
            table.add_row("--claude-key", "Set Claude API key", "fichero configure --claude-key sk-ant-zzz")
            table.add_row("--show", "Show current settings", "fichero configure --show")
            table.add_row("--show-api-keys", "Show current settings with API keys", "fichero configure --show-api-keys")
            
            self.console.print(table)
            return True
            
        except Exception as e:
            self.error_handler.handle_general_exception(e, "showing available options")
            return False 
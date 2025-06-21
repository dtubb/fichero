import os
import multiprocessing
import platform
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .loader import ConfigLoader

logger = logging.getLogger(__name__)



class AppSettings:
    """Simplified settings manager with clear fallback hierarchy"""
    
    def __init__(self, app=None):
        self.app = app
        self._init_encryption()
        self.settings = self.load_settings()
    
    def _init_encryption(self):
        """Initialize encryption key using machine-specific salt"""
        try:
            machine_id = platform.node()
            salt = machine_id.encode()
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
            self.fernet = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            self.fernet = None
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt a string value"""
        if not value or not self.fernet:
            return value
        try:
            return self.fernet.encrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt value: {e}")
            return value
    
    def _decrypt_value(self, encrypted: str) -> str:
        """Decrypt an encrypted string value"""
        if not encrypted or not self.fernet:
            return encrypted
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt value: {e}")
            return encrypted
    
    def _encrypt_api_keys(self, settings: Dict):
        """Encrypt API keys in settings"""
        api_servers = settings.get("api_servers", {})
        for provider in api_servers:
            if "api_key" in api_servers[provider]:
                api_servers[provider]["api_key"] = self._encrypt_value(api_servers[provider]["api_key"])
    
    def _decrypt_api_keys(self, settings: Dict):
        """Decrypt API keys in settings"""
        api_servers = settings.get("api_servers", {})
        for provider in api_servers:
            if "api_key" in api_servers[provider]:
                api_servers[provider]["api_key"] = self._decrypt_value(api_servers[provider]["api_key"])
    
    def load_settings(self) -> Dict:
        """
        Simple settings loading hierarchy:
        1. Currently active settings file (via AppPreferences)
        2. Default settings file
        3. Environment variables (for API keys)  
        4. Calculated defaults (for workers)
        """
        settings = {}
        
        # 1. Try to load from currently active file via AppPreferences
        try:
            # Import here to avoid circular dependency
            from .app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            active_file = app_prefs.get_active_settings_file()
            
            if active_file and active_file.exists():
                # Load the file and then decrypt API keys
                settings = ConfigLoader.load_config_file(active_file)
                self._decrypt_api_keys(settings)  # Decrypt after loading
                logger.info(f"Loaded settings from active file: {active_file.name}")
                
                # Sync API keys to shared data for cross-process access
                self._sync_api_keys_to_shared_data(settings)
                
                return settings
        except Exception as e:
            logger.warning(f"Failed to load from active settings file: {e}")
        
        # 2. Try to load default settings as base
        default_path = self._get_default_settings_path()
        if default_path and default_path.exists():
            try:
                settings = ConfigLoader.load_config_file(default_path)
                logger.info(f"Loaded default settings from {default_path}")
                
                # Set this as the active settings file if none was set
                try:
                    from .app_preferences import get_app_preferences
                    app_prefs = get_app_preferences(self.app)
                    if not app_prefs.get_active_settings_file():
                        app_prefs.set_active_settings_file(default_path)
                        logger.info(f"Set default settings as active: {default_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to set default settings as active: {e}")
                    
            except Exception as e:
                logger.warning(f"Failed to load default settings: {e}")
                settings = self._get_fallback_settings()
        else:
            settings = self._get_fallback_settings()
        
        # 3. Override API keys with environment variables if settings are empty
        self._apply_env_overrides(settings)
        
        # 4. Calculate worker defaults if not set
        self._ensure_worker_defaults(settings)
        
        # 5. Sync API keys to shared data for cross-process access
        self._sync_api_keys_to_shared_data(settings)
        
        return settings
    
    def _get_default_settings_path(self) -> Optional[Path]:
        """Get path to default settings file"""
        if self.app and hasattr(self.app, 'paths'):
            return self.app.paths.app / "resources" / "config_defaults" / "settings" / "Default Settings.yml"
        else:
            return Path(__file__).parent.parent.parent / "resources" / "config_defaults" / "settings" / "Default Settings.yml"
    

    
    def _get_fallback_settings(self) -> Dict:
        """Hardcoded fallback settings if no files found"""
        return {
            "title": "Fallback Application Settings",
            "description": "Calculated application settings",
            "preferences": {
                "language": "en"
            },
            "workers": {
                "backend": "python",
                "cpu_workers": 4,
                "io_workers": 8,
                "memory_per_worker_mb": 2048
            },
            "api_servers": {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1"
                },
                "qwen": {
                    "api_key": "",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
                },
                "claude": {
                    "api_key": "",
                    "base_url": "https://api.anthropic.com"
                },
                "ollama": {
                    "base_url": "http://localhost:11434"
                },
                "lmstudio": {
                    "base_url": "http://localhost:1234/v1"
                }
            }
        }
    
    def _apply_env_overrides(self, settings: Dict):
        """Override API keys with environment variables if settings are empty"""
        api_servers = settings.get("api_servers", {})
        
        # Only override if settings are empty
        for provider, env_vars in [
            ("openai", ["OPENAI_API_KEY"]),
            ("qwen", ["DASHSCOPE_API_KEY", "QWEN_API_KEY"]),
            ("claude", ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"])
        ]:
            if provider in api_servers and not api_servers[provider].get("api_key"):
                for env_var in env_vars:
                    env_value = os.getenv(env_var)
                    if env_value:
                        api_servers[provider]["api_key"] = env_value
                        break
    
    def _ensure_worker_defaults(self, settings: Dict):
        """Calculate worker defaults based on system if not set"""
        workers = settings.get("workers", {})
        
        cpu_count = multiprocessing.cpu_count()
        is_m1_mac = self._detect_m1_mac()
        
        if "cpu_workers" not in workers or workers["cpu_workers"] <= 0:
            workers["cpu_workers"] = max(1, cpu_count // 2)
        
        if "io_workers" not in workers or workers["io_workers"] <= 0:
            workers["io_workers"] = max(4, cpu_count * 2)
        
        if "memory_per_worker_mb" not in workers or workers["memory_per_worker_mb"] <= 0:
            workers["memory_per_worker_mb"] = 2048
        
        settings["workers"] = workers
    
    def _detect_m1_mac(self) -> bool:
        """Detect if running on Apple Silicon Mac"""
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return False
        try:
            result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                  capture_output=True, text=True)
            return 'Apple' in result.stdout
        except:
            return False
    
    def _sync_api_keys_to_shared_data(self, settings: Dict):
        """Sync API keys to shared data for cross-process access"""
        try:
            from fichero.shared_data import get_shared_data
            
            # Use the backend preference from settings to avoid creating wrong global instance
            backend_type = settings.get("workers", {}).get("backend", "python")
            prefer_backend = "redis" if backend_type == "redis" else "manager"
            
            shared_data = get_shared_data(prefer_backend=prefer_backend)
            
            api_servers = settings.get("api_servers", {})
            logger.info(f"Syncing API keys to shared data ({shared_data.backend_name}) for {len(api_servers)} providers")
            
            for provider, config in api_servers.items():
                api_key = config.get("api_key")
                if api_key and api_key.strip():
                    # Store as structured setting: "api_key:provider" (permanent)
                    shared_data.set_setting(f"api_key:{provider}", api_key)
                    logger.info(f"✅ Synced {provider} API key to shared data")
                else:
                    logger.debug(f"⚠️ Skipping {provider} - empty or missing API key")
        except Exception as e:
            logger.error(f"❌ Failed to sync API keys to shared data: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Convenience getter methods
    def get_worker_config(self) -> Dict:
        """Get worker configuration"""
        return self.settings.get("workers", {})
    
    def get_api_servers(self) -> Dict:
        """Get all API server configurations"""
        return self.settings.get("api_servers", {})
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a specific provider"""
        api_servers = self.get_api_servers()
        return api_servers.get(provider, {}).get("api_key")
    
    def get_api_config(self, provider: str) -> Dict:
        """Get full API configuration for a provider"""
        api_servers = self.get_api_servers()
        return api_servers.get(provider, {})
    
    def get_cpu_workers(self) -> int:
        """Get number of CPU workers"""
        return self.get_worker_config().get("cpu_workers", 4)
    
    def get_io_workers(self) -> int:
        """Get number of IO workers"""
        return self.get_worker_config().get("io_workers", 8)
    
    def get_memory_per_worker(self) -> int:
        """Get memory limit per worker in MB"""
        return self.get_worker_config().get("memory_per_worker_mb", 2048)
    
    def get_backend_type(self) -> str:
        """Get the processing backend type (python or redis)"""
        return self.get_worker_config().get("backend", "python")
    
    def save_settings(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Save settings with API key encryption"""
        try:
            # Create a copy to avoid modifying the original data
            encrypted_data = data.copy()
            
            # Encrypt API keys before saving
            self._encrypt_api_keys(encrypted_data)
            
            # Save using ConfigLoader
            from .loader import ConfigLoader
            ConfigLoader.save_config_file(file_path, encrypted_data)
            
            logger.info(f"✅ Saved settings with encrypted API keys to: {file_path.name}")
            
            # Update our internal settings and sync to shared data
            self.settings = data  # Keep unencrypted version in memory
            self._sync_api_keys_to_shared_data(self.settings)
            
            # Update active file reference
            try:
                from .app_preferences import get_app_preferences
                app_prefs = get_app_preferences(self.app)
                app_prefs.set_active_settings_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to update active settings file reference: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save settings: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


# Global settings instance (will be initialized when needed)
_app_settings = None

def get_app_settings(app=None) -> AppSettings:
    """Get global app settings instance"""
    global _app_settings
    if _app_settings is None:
        _app_settings = AppSettings(app)
    return _app_settings

def reload_settings(app=None):
    """Force reload of settings"""
    global _app_settings
    _app_settings = AppSettings(app)
    return _app_settings 
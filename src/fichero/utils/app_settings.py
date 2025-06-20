import os
import srsly
import multiprocessing
import platform
import subprocess
import logging
import json
import time
from pathlib import Path
from typing import Dict, Optional, Any, Union
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .shared_data import get_shared_data, DataType

logger = logging.getLogger(__name__)



class AppSettings:
    """Central settings manager for Fichero app with proper fallback hierarchy"""
    
    def __init__(self, app=None):
        self.app = app
        self._init_encryption()  # Initialize encryption first
        # Initialize shared data manager with proper Toga data directory
        data_dir = None
        if self.app and hasattr(self.app, 'paths'):
            data_dir = self.app.paths.data / "shared_data"
        self.shared_data = get_shared_data(namespace="fichero", default_ttl=3600, data_dir=data_dir)
        self.settings = self.load_settings()  # Then load settings
    
    def _init_encryption(self):
        """Initialize encryption key using machine-specific salt"""
        try:
            # Generate a machine-specific salt
            machine_id = platform.node()  # Get machine name
            salt = machine_id.encode()
            
            # Use PBKDF2 to derive a key from the machine ID
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
            self.fernet = Fernet(key)
            logger.info("Encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            # Create a dummy Fernet instance that does nothing
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
            return ""
    
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
        Load settings with fallback hierarchy:
        1. Shared store (if available)
        2. Default settings (resources/default_app_settings.json)  
        3. Environment variables (for API keys)
        4. Calculated defaults (for workers)
        """
        settings = {}
        
        # 1. Try to load from shared data first
        shared_settings = self.shared_data.get(DataType.SETTINGS, "main_config")
        if shared_settings is not None:
            logger.info("Loaded settings from shared data")
            # Decrypt API keys from shared settings
            self._decrypt_api_keys(shared_settings)
            return shared_settings
        
        # 2. Try to load default settings as base
        if self.app:
            default_path = self.app.paths.app / "resources" / "default_app_settings.json"
        else:
            # Fallback path when no app context
            default_path = Path(__file__).parent / "resources" / "default_app_settings.json"
        
        if default_path.exists():
            try:
                settings = srsly.read_json(default_path)
                logger.info(f"Loaded default settings from {default_path}")
            except Exception as e:
                logger.warning(f"Failed to load default settings: {e}")
                settings = self._get_fallback_settings()
        else:
            logger.warning(f"Default settings not found at {default_path}")
            settings = self._get_fallback_settings()
        
        # 3. Override API keys with environment variables if available, but only if settings are empty
        self._apply_env_overrides(settings)
        
        # 4. Calculate worker defaults if not set
        self._ensure_worker_defaults(settings)
        
        # 5. Set environment variables from loaded settings
        self._set_env_from_settings(settings)
        
        # Save to shared data for future use (encrypt API keys first)
        settings_for_shared = settings.copy()
        self._encrypt_api_keys(settings_for_shared)
        self.shared_data.set(DataType.SETTINGS, "main_config", settings_for_shared, immediate_save=True)
        
        return settings
    
    def save_settings(self, settings: Dict):
        """Save settings to shared data store only"""
        # Create a copy of settings to encrypt
        settings_to_save = settings.copy()
        # Encrypt API keys before saving
        self._encrypt_api_keys(settings_to_save)
        
        # Save to shared data store only
        self.shared_data.set(DataType.SETTINGS, "main_config", settings_to_save, immediate_save=True)
        logger.info("Saved settings to shared data store")
        
        # Set environment variables for scripts to use
        self._set_env_from_settings(settings)
    
    def _set_env_from_settings(self, settings: Dict):
        """Set environment variables from settings for scripts to use"""
        api_servers = settings.get("api_servers", {})
        
        # OpenAI
        if "openai" in api_servers and api_servers["openai"]["api_key"]:
            os.environ["OPENAI_API_KEY"] = api_servers["openai"]["api_key"]
            logger.info("Set OpenAI API key in environment")
        
        # Qwen
        if "qwen" in api_servers and api_servers["qwen"]["api_key"]:
            os.environ["DASHSCOPE_API_KEY"] = api_servers["qwen"]["api_key"]
            logger.info("Set Qwen API key in environment")
        
        # Claude
        if "claude" in api_servers and api_servers["claude"]["api_key"]:
            os.environ["ANTHROPIC_API_KEY"] = api_servers["claude"]["api_key"]
            logger.info("Set Claude API key in environment")
    
    def _get_fallback_settings(self) -> Dict:
        """Hardcoded fallback settings if no files found"""
        return {
            "workers": {
                "cpu_workers": 4,
                "io_workers": 8,
                "memory_per_worker_mb": 2048
            },
            "api_servers": {
                "openai": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1"
                },
                "qwen": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
                }
            }
        }
    
    def _merge_settings(self, base: Dict, override: Dict) -> Dict:
        """Deep merge settings dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        return result
    
    def _apply_env_overrides(self, settings: Dict):
        """Override API keys with environment variables if available, but only if settings are empty"""
        api_servers = settings.get("api_servers", {})
        
        # OpenAI
        if "openai" in api_servers:
            if not api_servers["openai"]["api_key"]:  # Only if settings are empty
                openai_key = os.getenv("OPENAI_API_KEY")
                if openai_key:
                    api_servers["openai"]["api_key"] = openai_key
                    logger.info("Using OpenAI API key from environment (no key in settings)")
        
        # Qwen (try multiple env var names)
        if "qwen" in api_servers:
            if not api_servers["qwen"]["api_key"]:  # Only if settings are empty
                qwen_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
                if qwen_key:
                    api_servers["qwen"]["api_key"] = qwen_key
                    logger.info("Using Qwen API key from environment (no key in settings)")
        
        # Claude (if we add it later)
        if "claude" in api_servers:
            if not api_servers["claude"]["api_key"]:  # Only if settings are empty
                claude_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
                if claude_key:
                    api_servers["claude"]["api_key"] = claude_key
                    logger.info("Using Claude API key from environment (no key in settings)")
    
    def _ensure_worker_defaults(self, settings: Dict):
        """Calculate worker defaults based on system if not set"""
        workers = settings.get("workers", {})
        
        # Get CPU count and detect architecture (same logic as director.py)
        cpu_count = multiprocessing.cpu_count()
        is_m1_mac = self._detect_m1_mac()
        
        # Calculate defaults if not set
        if "cpu_workers" not in workers or workers["cpu_workers"] <= 0:
            if is_m1_mac:
                workers["cpu_workers"] = max(1, cpu_count // 2)
            else:
                workers["cpu_workers"] = max(1, cpu_count // 2)
        
        if "io_workers" not in workers or workers["io_workers"] <= 0:
            if is_m1_mac:
                workers["io_workers"] = max(4, cpu_count * 2)
            else:
                workers["io_workers"] = max(4, cpu_count * 2)
        
        if "memory_per_worker_mb" not in workers or workers["memory_per_worker_mb"] <= 0:
            workers["memory_per_worker_mb"] = 2048
        
        settings["workers"] = workers
        logger.info(f"Worker config: CPU={workers['cpu_workers']}, IO={workers['io_workers']}, Memory={workers['memory_per_worker_mb']}MB")
    
    def _detect_m1_mac(self) -> bool:
        """Detect if running on Apple Silicon Mac (same logic as director.py)"""
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return False
        try:
            result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                  capture_output=True, text=True)
            return 'Apple' in result.stdout
        except:
            return False
    
    # Getter methods for easy access
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
    
    def is_api_enabled(self, provider: str) -> bool:
        """Check if an API provider is enabled"""
        config = self.get_api_config(provider)
        return config.get("enabled", False) and bool(config.get("api_key"))
    
    def get_cpu_workers(self) -> int:
        """Get number of CPU workers"""
        return self.get_worker_config().get("cpu_workers", 4)
    
    def get_io_workers(self) -> int:
        """Get number of IO workers"""
        return self.get_worker_config().get("io_workers", 8)
    
    def get_memory_per_worker(self) -> int:
        """Get memory limit per worker in MB"""
        return self.get_worker_config().get("memory_per_worker_mb", 2048)
    
    # Generic shared data methods
    def set_shared_setting(self, key: str, value: Any, ttl: Optional[int] = None, encrypt_api_keys: bool = False) -> bool:
        """Set any setting in shared data with optional encryption
        
        Args:
            key: Setting key
            value: Setting value (will be JSON serialized)
            ttl: Time to live in seconds (None uses default)
            encrypt_api_keys: Whether to encrypt API keys in the value
        
        Returns:
            True if successful
        """
        try:
            value_to_store = value
            if encrypt_api_keys and isinstance(value, dict):
                value_to_store = value.copy()
                self._encrypt_api_keys(value_to_store)
            
            return self.shared_data.set(DataType.SETTINGS, key, value_to_store, ttl)
        except Exception as e:
            logger.error(f"Failed to set shared setting {key}: {e}")
            return False
    
    def get_shared_setting(self, key: str, default: Any = None, decrypt_api_keys: bool = False) -> Any:
        """Get any setting from shared data with optional decryption
        
        Args:
            key: Setting key
            default: Default value if not found
            decrypt_api_keys: Whether to decrypt API keys in the value
        
        Returns:
            The setting value or default
        """
        try:
            value = self.shared_data.get(DataType.SETTINGS, key, default)
            
            if decrypt_api_keys and isinstance(value, dict) and value != default:
                value = value.copy()
                self._decrypt_api_keys(value)
            
            return value
        except Exception as e:
            logger.error(f"Failed to get shared setting {key}: {e}")
            return default
    
    def delete_shared_setting(self, key: str) -> bool:
        """Delete a setting from shared data
        
        Args:
            key: Setting key to delete
        
        Returns:
            True if successful
        """
        return self.shared_data.delete(DataType.SETTINGS, key)
    
    def list_shared_settings(self, pattern: str = "*") -> list:
        """List all shared settings matching pattern
        
        Args:
            pattern: Pattern to match (supports wildcards)
        
        Returns:
            List of setting keys
        """
        return self.shared_data.keys(DataType.SETTINGS, pattern)
    
    def get_shared_data_info(self) -> Dict[str, Any]:
        """Get information about the shared data manager
        
        Returns:
            Dictionary with data manager information
        """
        return self.shared_data.get_info()
    
    # Direct access to SharedDataManager for advanced use cases
    @property
    def shared_store(self):
        """Backward compatibility: access to shared data manager"""
        return self.shared_data

# Global settings instance (will be initialized when needed)
_app_settings = None

def get_app_settings(app=None) -> AppSettings:
    """Get global app settings instance"""
    global _app_settings
    if _app_settings is None:
        _app_settings = AppSettings(app)
    return _app_settings

def reload_settings(app=None):
    """Force reload of settings (useful after settings window changes)"""
    global _app_settings
    _app_settings = AppSettings(app)
    return _app_settings 

"""
USAGE EXAMPLES - SHARED SETTINGS:

# Basic shared settings usage
settings = get_app_settings(app)

# Store user preferences with TTL
settings.set_shared_setting("user_theme", "dark", ttl=3600)
settings.set_shared_setting("window_size", {"width": 1200, "height": 800})
settings.set_shared_setting("recent_files", ["/path/to/file1.txt"], ttl=86400)

# Get settings with defaults
theme = settings.get_shared_setting("user_theme", default="light")
window_size = settings.get_shared_setting("window_size", default={"width": 800, "height": 600})

# Handle API keys securely
api_config = {
    "openai": {"api_key": "sk-...", "model": "gpt-4"},
    "claude": {"api_key": "sk-ant-...", "model": "claude-3"}
}
settings.set_shared_setting("ai_config", api_config, encrypt_api_keys=True)
retrieved_config = settings.get_shared_setting("ai_config", decrypt_api_keys=True)

# List and manage settings
all_settings = settings.list_shared_settings()  # Get all keys
theme_settings = settings.list_shared_settings("*theme*")  # Pattern matching
settings.delete_shared_setting("old_config")  # Cleanup

# Get system info
info = settings.get_shared_data_info()
print(f"Using {info['backend']} backend with {info['settings_count']} settings")

# Direct access to shared data manager for advanced use cases
shared_data = settings.shared_data
shared_data.set_setting("temp_flag", True, ttl=300)  # 5 minutes
if shared_data.get_setting("temp_flag", False):
    print("Temporary flag is still active")

# PERSISTENCE & AUTO-SAVE:
# Shared data automatically persists to ~/.fichero/shared_data/ in JSONL format
shared_data.save_to_disk()  # Manual save
shared_data.auto_save(interval=300)  # Auto-save every 5 minutes

# EXPANDING THE SYSTEM:
# When you need progress tracking, output streaming, etc., simply:
# 1. Uncomment the data types in shared_data.py
# 2. Add the specific methods you need  
# 3. Use them like: shared_data.set_progress(), shared_data.append_output(), etc.
""" 
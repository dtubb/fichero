"""
Settings File Manager
Handles settings-specific file operations and business logic
"""

import yaml
import platform
import base64
from pathlib import Path
from typing import Dict, Any, List
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .file_manager import FileManager

logger = logging.getLogger(__name__)


class SettingsManager(FileManager):
    """
    ULTRA SIMPLE settings manager: One class does everything.
    
    🔄 FLOW:
    GUI requests data → load_file() → decrypt → return decrypted data
    GUI saves data → save_file() → encrypt → save to disk
    
    ✅ BENEFITS:
    - No cache (files are tiny)
    - No dependencies (self-contained encryption)
    - No multiple sources of truth
    - Always fresh from disk
    - Always decrypted for GUI
    """
    
    def __init__(self, app=None):
        super().__init__(app)
        self._init_encryption()
    
    def get_file_type(self) -> str:
        """Get the file type name"""
        return "settings"
    
    def get_file_extensions(self) -> List[str]:
        """Get supported file extensions for settings"""
        return ['.yml', '.yaml', '.json']
    
    def get_default_template(self) -> Dict[str, Any]:
        """Get default data structure for new settings files"""
        return {
            "title": "Custom Application Settings",
            "description": "User-defined application settings",
            "preferences": {
                "language": "en"
            },
            "workers": {
                "backend": "python",
                "cpu_workers": 4,
                "io_workers": 16,
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
                },
                "blackfish": {
                    "base_url": "https://blackfish.example.com"
                },
                "huggingface": {
                    "api_key": "",
                    "base_url": "https://api-inference.huggingface.co"
                }
            }
        }
    
    def load_file(self, file_path: Path) -> Dict[str, Any]:
        """SUPER SIMPLE: Load file, decrypt, return to GUI - no dependencies"""
        try:
            # Load file directly
            from .loader import ConfigLoader
            file_data = ConfigLoader.load_config_file(file_path)
            
            # Decrypt API keys directly here - no dependencies
            self._decrypt_api_keys_simple(file_data)
            
            # Merge with defaults
            default_data = self.get_default_template()
            complete_data = self._merge_settings(default_data, file_data)
            
            # Sync DECRYPTED API keys to shared data for tools
            self._sync_api_keys_to_shared_data(complete_data)
            
            logger.info(f"✅ Loaded and decrypted settings: {file_path.name}")
            return complete_data
            
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            return self.get_default_template()
    

    
    def save_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """SUPER SIMPLE: Take GUI data, encrypt, save to file - no dependencies"""
        try:
            # Make a copy to encrypt
            encrypted_data = data.copy()
            
            # Encrypt API keys directly here - no dependencies
            self._encrypt_api_keys_simple(encrypted_data)
            
            # Save directly
            from .loader import ConfigLoader
            ConfigLoader.save_config_file(file_path, encrypted_data)
            
            # Sync DECRYPTED API keys to shared data for tools
            self._sync_api_keys_to_shared_data(data)
            
            logger.info(f"✅ Saved encrypted settings to {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    # ==================== ENCRYPTION METHODS ====================
    
    def _init_encryption(self):
        """Initialize encryption key"""
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
            logger.debug("✅ Encryption initialized")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            self.fernet = None
    
    def _encrypt_api_keys_simple(self, settings: Dict):
        """Encrypt API keys in settings - simple version"""
        api_servers = settings.get("api_servers", {})
        for provider in api_servers:
            if "api_key" in api_servers[provider]:
                api_key = api_servers[provider]["api_key"]
                if api_key and not self._looks_encrypted_simple(api_key):
                    encrypted = self._encrypt_value_simple(api_key)
                    api_servers[provider]["api_key"] = encrypted
                    logger.debug(f"🔒 Encrypted {provider} API key")
    
    def _decrypt_api_keys_simple(self, settings: Dict):
        """Decrypt API keys in settings - simple version"""
        api_servers = settings.get("api_servers", {})
        for provider in api_servers:
            if "api_key" in api_servers[provider]:
                api_key = api_servers[provider]["api_key"]
                if api_key and self._looks_encrypted_simple(api_key):
                    decrypted = self._decrypt_value_simple(api_key)
                    api_servers[provider]["api_key"] = decrypted
                    logger.info(f"🔓 Decrypted {provider} API key: {decrypted[:10]}...{decrypted[-4:] if len(decrypted) > 4 else ''}")
                else:
                    logger.info(f"⚠️ {provider} key doesn't look encrypted: {api_key[:10] if api_key else 'empty'}...")
    
    def _encrypt_value_simple(self, value: str) -> str:
        """Encrypt a string value"""
        if not value or not self.fernet:
            return value
        try:
            return self.fernet.encrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt value: {e}")
            return value
    
    def _decrypt_value_simple(self, encrypted: str) -> str:
        """Decrypt an encrypted string value"""
        if not encrypted or not self.fernet:
            return encrypted
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt value: {e}")
            return encrypted
    
    def _looks_encrypted_simple(self, value: str) -> bool:
        """Check if a value looks like encrypted data - simple version"""
        if not value:
            return False
        
        # Real API keys are usually 20-60 chars
        # Encrypted data is usually 100+ chars and starts with gAAAAA
        if len(value) > 70 and value.startswith('gAAAAA'):
            logger.debug(f"✅ Looks encrypted: length={len(value)}, starts with gAAAAA")
            return True
        
        logger.debug(f"❌ Doesn't look encrypted: length={len(value)}, starts with {value[:10]}...")
        return False
    
    def _sync_api_keys_to_shared_data(self, settings: Dict):
        """Sync DECRYPTED API keys to shared data for tools to use"""
        try:
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data()
            
            api_servers = settings.get("api_servers", {})
            logger.info(f"🔄 Syncing {len(api_servers)} API keys to shared data ({shared_data.backend_name})")
            
            for provider, config in api_servers.items():
                api_key = config.get("api_key")
                if api_key and api_key.strip():
                    # DEBUG: Check if we're accidentally syncing encrypted data
                    is_encrypted = self._looks_encrypted_simple(api_key)
                    logger.info(f"🔍 SYNC DEBUG: {provider} key is_encrypted={is_encrypted}, key={api_key[:20]}...{api_key[-10:]} (len={len(api_key)})")
                    
                    if is_encrypted:
                        logger.error(f"🚨 CRITICAL: Trying to sync ENCRYPTED {provider} key to shared data!")
                        # Force decrypt it here
                        decrypted_key = self._decrypt_value_simple(api_key)
                        logger.info(f"🔓 FIXED: Force decrypted {provider}: {decrypted_key[:10]}...{decrypted_key[-4:] if len(decrypted_key) > 4 else ''}")
                        shared_data.set_setting(f"api_key:{provider}", decrypted_key)
                    else:
                        # Store DECRYPTED key for tools
                        shared_data.set_setting(f"api_key:{provider}", api_key)
                        logger.info(f"✅ Synced {provider} API key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 4 else ''}")
                else:
                    logger.debug(f"⚠️ Skipping {provider} - empty or missing API key")
                    
        except Exception as e:
            logger.error(f"❌ Failed to sync API keys to shared data: {e}")
    
    def _merge_settings(self, base: Dict, override: Dict) -> Dict:
        """Deep merge settings dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        return result
    

    
    def get_active_file(self) -> Path:
        """Get the currently active settings file"""
        try:
            # Use app preferences for active file tracking
            from .app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            return app_prefs.get_active_settings_file()
        except Exception as e:
            logger.error(f"Failed to get active settings file: {e}")
            return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """Set the active settings file"""
        try:
            # Use app preferences for active file tracking
            from .app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            success = app_prefs.set_active_settings_file(file_path)
            
            if success:
                logger.info(f"Set active settings file: {file_path.name}")
            return success
        except Exception as e:
            logger.error(f"Failed to set active settings file: {e}")
            return False 
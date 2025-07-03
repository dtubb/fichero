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
    SIMPLIFIED settings manager: User file → Default file fallback.
    
    🔄 FLOW:
    GUI requests data → load_file() → decrypt → return decrypted data
    GUI saves data → save_file() → encrypt → save to disk
    
    ✅ BENEFITS:
    - No active file tracking (just use user file)
    - No complex hierarchy (file → fallback only)
    - No AppPreferences dependency
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
        """SIMPLE: Load file, decrypt, return to GUI - no dependencies"""
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
        """SIMPLE: Take GUI data, encrypt, save to file - no dependencies"""
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
    
    def load_settings(self) -> Dict[str, Any]:
        """SIMPLE: Load settings with user file → default file fallback"""
        try:
            # 1. Try user settings file
            user_file = self.get_user_settings_path()
            logger.info(f"Looking for user settings at: {user_file}")
            if user_file and user_file.exists():
                logger.info(f"Found user settings file: {user_file}")
                return self.load_file(user_file)
            
            # 2. Fallback to default file
            default_file = self.get_default_settings_path()
            logger.info(f"Looking for default settings at: {default_file}")
            if default_file and default_file.exists():
                logger.info(f"Found default settings file: {default_file}")
                return self.load_file(default_file)
            
            # 3. Return template if no files exist
            logger.info("No settings files found, using default template")
            return self.get_default_template()
            
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            return self.get_default_template()
    
    def save_settings(self, data: Dict[str, Any]) -> bool:
        """SIMPLE: Save to user settings file"""
        try:
            user_file = self.get_user_settings_path()
            logger.info(f"Saving settings to: {user_file}")
            if user_file:
                success = self.save_file(user_file, data)
                if success:
                    logger.info(f"✅ Settings saved successfully to {user_file}")
                else:
                    logger.error(f"❌ Failed to save settings to {user_file}")
                return success
            logger.error("No user settings path available")
            return False
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def get_user_settings_path(self) -> Path:
        """Get the path to the user settings file"""
        try:
            # Use proper user settings directory, not Toga's config path
            if self.app and hasattr(self.app, 'paths'):
                # Use app.paths.data for user settings (same as other config files)
                logger.info(f"App paths: data={self.app.paths.data}, app={self.app.paths.app}, config={self.app.paths.config}")
                user_dir = self.app.paths.data / "settings"
                user_dir.mkdir(parents=True, exist_ok=True)
                user_file = user_dir / "settings.yml"
                logger.info(f"User settings path: {user_file}")
                return user_file
            else:
                # Fallback for CLI usage
                cli_path = Path.home() / ".fichero" / "settings.yml"
                logger.info(f"CLI settings path: {cli_path}")
                return cli_path
        except Exception as e:
            logger.error(f"Failed to get user settings path: {e}")
            return None
    
    def get_default_settings_path(self) -> Path:
        """Get the path to the default settings file"""
        try:
            if self.app and hasattr(self.app, 'paths'):
                default_path = self.app.paths.app / "resources" / "config_defaults" / "settings" / "default.settings.yml"
                logger.info(f"Default settings path: {default_path}")
                return default_path
            else:
                # Fallback for CLI usage
                cli_default_path = Path(__file__).parent.parent.parent / "resources" / "config_defaults" / "settings" / "default.settings.yml"
                logger.info(f"CLI default settings path: {cli_default_path}")
                return cli_default_path
        except Exception as e:
            logger.error(f"Failed to get default settings path: {e}")
            return None
    
    def delete_user_settings(self):
        """Delete the user settings file (do not touch default file)"""
        try:
            user_file = self.get_user_settings_path()
            if user_file and user_file.exists():
                user_file.unlink()
                logger.info(f"Deleted user settings file: {user_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete user settings file: {e}")
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
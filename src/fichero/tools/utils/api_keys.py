"""
API Key Management Utility for Tools
Provides four-tier fallback hierarchy for API key lookup:
1. CLI argument (development/testing override)
2. Shared data (production/app usage)
3. File-based persistence (Manager backend fallback)
4. Environment variable (fallback)
"""

import os
import json
from typing import Optional
from pathlib import Path

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from tool_logger import get_tool_logger

tool_logger = get_tool_logger('api_keys')


def _read_manager_persistence_file(provider: str) -> Optional[str]:
    """
    Read API key from Manager backend's persistence files
    This is used when subprocess can't access Manager shared memory
    """
    try:
        # Discover app data directory (same logic as base.py)
        from fichero.shared_data.backends.base import discover_app_data_directory
        app_data_dir = discover_app_data_directory()
        persistence_file = app_data_dir / "shared_data" / "fichero_settings.jsonl"
        
        if not persistence_file.exists():
            tool_logger.debug(f"Manager persistence file not found: {persistence_file}")
            return None
        
        # Read JSONL format - each line is a separate entry
        try:
            import srsly
            entries = list(srsly.read_jsonl(persistence_file))
        except ImportError:
            # Fallback to manual JSONL reading if srsly not available
            entries = []
            with open(persistence_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        
        # Look for the API key
        for entry in entries:
            key = entry.get("key")
            value = entry.get("value")
            
            if key == f"api_key:{provider}" and value:
                tool_logger.info(f"🔑 Using Manager persistence file for {provider} API key")
                return value
        
        tool_logger.debug(f"No {provider} API key found in Manager persistence file")
        return None
        
    except Exception as e:
        tool_logger.debug(f"Failed to read Manager persistence file for {provider}: {e}")
        return None


def get_api_key(provider: str, cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get API key using four-tier fallback hierarchy:
    1. CLI argument (if provided)
    2. Shared data (production/app usage)
    3. File-based persistence (Manager backend fallback)
    4. Environment variable (fallback)
    
    Args:
        provider: API provider name ("openai", "qwen", "claude", "huggingface")
        cli_arg: CLI argument value if provided
        
    Returns:
        API key string or None if not found
    """
    # 1. CLI argument (development/testing override)
    if cli_arg:
        tool_logger.info(f"🔑 Using CLI argument for {provider} API key")
        return cli_arg
    
    # 2. Shared data (production/app usage) with direct Redis fallback
    api_key = None
    try:
        from fichero.shared_data import get_shared_data
        shared_data = get_shared_data()
        api_key = shared_data.get_setting(f"api_key:{provider}")
        if api_key:
            tool_logger.info(f"🔑 Using shared data for {provider} API key ({shared_data.backend_name})")
            return api_key
        else:
            tool_logger.debug(f"No {provider} API key found in shared data")
    except Exception as e:
        tool_logger.debug(f"Shared data not available for {provider}: {e}")
        
        # Direct Redis fallback for subprocess execution
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            redis_key = f"fichero:settings:api_key:{provider}"
            api_key_bytes = r.get(redis_key)
            if api_key_bytes:
                api_key = api_key_bytes.decode('utf-8').strip('"')
                if api_key and api_key.strip():
                    tool_logger.info(f"🔑 Using direct Redis for {provider} API key")
                    return api_key
            tool_logger.debug(f"No {provider} API key found in direct Redis")
        except Exception as redis_e:
            tool_logger.debug(f"Direct Redis not available for {provider}: {redis_e}")
    
    # 3. File-based persistence (Manager backend fallback for subprocesses)
    api_key = _read_manager_persistence_file(provider)
    if api_key:
        return api_key
    
    # 4. Environment variable (fallback)
    env_var_map = {
        "openai": "OPENAI_API_KEY",
        "qwen": "DASHSCOPE_API_KEY", 
        "claude": "ANTHROPIC_API_KEY",
        "huggingface": "HUGGINGFACE_TOKEN"
    }
    
    env_var = env_var_map.get(provider)
    if env_var:
        api_key = os.getenv(env_var)
        if api_key:
            tool_logger.info(f"🔑 Using environment variable {env_var} for {provider} API key")
            return api_key
        else:
            tool_logger.debug(f"Environment variable {env_var} not set for {provider}")
    else:
        tool_logger.debug(f"No environment variable mapping for {provider}")
    
    tool_logger.warning(f"❌ No API key found for {provider}")
    return None


# Convenience functions for specific providers
def get_openai_key(cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get OpenAI API key with fallback hierarchy
    
    Args:
        cli_arg: CLI argument value (--openai-api-key)
        
    Returns:
        OpenAI API key or None
    """
    return get_api_key("openai", cli_arg)


def get_qwen_key(cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get Qwen API key with fallback hierarchy
    
    Args:
        cli_arg: CLI argument value (--api-key or --qwen-api-key)
        
    Returns:
        Qwen API key or None
    """
    return get_api_key("qwen", cli_arg)


def get_claude_key(cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get Claude API key with fallback hierarchy
    
    Args:
        cli_arg: CLI argument value (--claude-api-key)
        
    Returns:
        Claude API key or None
    """
    return get_api_key("claude", cli_arg)


def get_huggingface_token(cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get HuggingFace token with fallback hierarchy
    
    Args:
        cli_arg: CLI argument value (--huggingface-token)
        
    Returns:
        HuggingFace token or None
    """
    return get_api_key("huggingface", cli_arg)


def ensure_api_key(provider: str, cli_arg: Optional[str] = None, required: bool = True) -> str:
    """
    Get API key and raise error if not found and required
    
    Args:
        provider: API provider name
        cli_arg: CLI argument value if provided
        required: Whether to raise error if key not found
        
    Returns:
        API key string
        
    Raises:
        ValueError: If key not found and required=True
    """
    api_key = get_api_key(provider, cli_arg)
    if not api_key and required:
        raise ValueError(f"API key for {provider} is required but not found")
    return api_key


def ensure_openai_key(cli_arg: Optional[str] = None) -> str:
    """Get OpenAI API key or raise error"""
    return ensure_api_key("openai", cli_arg)


def ensure_qwen_key(cli_arg: Optional[str] = None) -> str:
    """Get Qwen API key or raise error"""
    return ensure_api_key("qwen", cli_arg)


def ensure_claude_key(cli_arg: Optional[str] = None) -> str:
    """Get Claude API key or raise error"""
    return ensure_api_key("claude", cli_arg)


def ensure_huggingface_token(cli_arg: Optional[str] = None) -> str:
    """Get HuggingFace token or raise error"""
    return ensure_api_key("huggingface", cli_arg)


def debug_api_key_sources(provider: str) -> dict:
    """
    Debug API key sources for troubleshooting
    
    Args:
        provider: API provider name
        
    Returns:
        Dictionary with debug information
    """
    debug_info = {
        "provider": provider,
        "sources_checked": [],
        "found_in": None,
        "error": None
    }
    
    try:
        # Check CLI argument (would be passed in)
        debug_info["sources_checked"].append("cli_argument")
        
        # Check shared data
        try:
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data()
            api_key = shared_data.get_setting(f"api_key:{provider}")
            if api_key:
                debug_info["found_in"] = "shared_data"
                debug_info["backend"] = shared_data.backend_name
            debug_info["sources_checked"].append("shared_data")
        except Exception as e:
            debug_info["sources_checked"].append("shared_data (error)")
            debug_info["shared_data_error"] = str(e)
        
        # Check direct Redis
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            redis_key = f"fichero:settings:api_key:{provider}"
            api_key_bytes = r.get(redis_key)
            if api_key_bytes and not debug_info["found_in"]:
                debug_info["found_in"] = "direct_redis"
            debug_info["sources_checked"].append("direct_redis")
        except Exception as e:
            debug_info["sources_checked"].append("direct_redis (error)")
            debug_info["redis_error"] = str(e)
        
        # Check persistence file
        try:
            from fichero.shared_data.backends.base import discover_app_data_directory
            app_data_dir = discover_app_data_directory()
            persistence_file = app_data_dir / "shared_data" / "fichero_settings.jsonl"
            if persistence_file.exists():
                debug_info["sources_checked"].append("persistence_file")
                debug_info["persistence_file_path"] = str(persistence_file)
            else:
                debug_info["sources_checked"].append("persistence_file (not_found)")
        except Exception as e:
            debug_info["sources_checked"].append("persistence_file (error)")
            debug_info["persistence_error"] = str(e)
        
        # Check environment variable
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "qwen": "DASHSCOPE_API_KEY", 
            "claude": "ANTHROPIC_API_KEY",
            "huggingface": "HUGGINGFACE_TOKEN"
        }
        env_var = env_var_map.get(provider)
        if env_var:
            api_key = os.getenv(env_var)
            if api_key and not debug_info["found_in"]:
                debug_info["found_in"] = "environment"
            debug_info["sources_checked"].append(f"environment_{env_var}")
        
    except Exception as e:
        debug_info["error"] = str(e)
    
    return debug_info 
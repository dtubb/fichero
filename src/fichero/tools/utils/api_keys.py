"""
API Key Management Utility for Tools
Provides three-tier fallback hierarchy for API key lookup:
1. CLI argument (development/testing override)
2. Shared data (production/app usage)
3. Environment variable (fallback)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_api_key(provider: str, cli_arg: Optional[str] = None) -> Optional[str]:
    """
    Get API key using three-tier fallback hierarchy:
    1. CLI argument (if provided)
    2. Shared data (production/app usage)
    3. Environment variable (fallback)
    
    Args:
        provider: API provider name ("openai", "qwen", "claude", "huggingface")
        cli_arg: CLI argument value if provided
        
    Returns:
        API key string or None if not found
    """
    # 1. CLI argument (development/testing override)
    if cli_arg:
        logger.info(f"🔑 Using CLI argument for {provider} API key")
        return cli_arg
    
    # 2. Shared data (production/app usage) with direct Redis fallback
    api_key = None
    try:
        from fichero.shared_data import get_shared_data
        shared_data = get_shared_data()
        api_key = shared_data.get_setting(f"api_key:{provider}")
        if api_key:
            logger.info(f"🔑 Using shared data for {provider} API key ({shared_data.backend_name})")
            return api_key
        else:
            logger.debug(f"No {provider} API key found in shared data")
    except Exception as e:
        logger.debug(f"Shared data not available for {provider}: {e}")
        
        # Direct Redis fallback for subprocess execution
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            redis_key = f"fichero:settings:api_key:{provider}"
            api_key_bytes = r.get(redis_key)
            if api_key_bytes:
                api_key = api_key_bytes.decode('utf-8').strip('"')
                if api_key and api_key.strip():
                    logger.info(f"🔑 Using direct Redis for {provider} API key")
                    return api_key
            logger.debug(f"No {provider} API key found in direct Redis")
        except Exception as redis_e:
            logger.debug(f"Direct Redis not available for {provider}: {redis_e}")
    
    # 3. Environment variable (fallback)
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
            logger.info(f"🔑 Using environment variable {env_var} for {provider} API key")
            return api_key
        else:
            logger.debug(f"Environment variable {env_var} not set for {provider}")
    else:
        logger.debug(f"No environment variable mapping for {provider}")
    
    logger.warning(f"❌ No API key found for {provider}")
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
        ValueError: If required=True and no API key found
    """
    api_key = get_api_key(provider, cli_arg)
    if required and not api_key:
        raise ValueError(f"{provider.title()} API key required. Set via CLI argument, app settings, or environment variable.")
    return api_key


# Provider-specific ensure functions
def ensure_openai_key(cli_arg: Optional[str] = None) -> str:
    """Get OpenAI API key, raise error if not found"""
    return ensure_api_key("openai", cli_arg)


def ensure_qwen_key(cli_arg: Optional[str] = None) -> str:
    """Get Qwen API key, raise error if not found"""
    return ensure_api_key("qwen", cli_arg)


def ensure_claude_key(cli_arg: Optional[str] = None) -> str:
    """Get Claude API key, raise error if not found"""
    return ensure_api_key("claude", cli_arg)


def ensure_huggingface_token(cli_arg: Optional[str] = None) -> str:
    """Get HuggingFace token, raise error if not found"""
    return ensure_api_key("huggingface", cli_arg)


def debug_api_key_sources(provider: str) -> dict:
    """
    Debug function to show all available API key sources for a provider
    
    Args:
        provider: API provider name
        
    Returns:
        Dictionary with all source information
    """
    result = {
        "provider": provider,
        "sources": {}
    }
    
    # Check shared data
    try:
        from fichero.shared_data import get_shared_data
        shared_data = get_shared_data()
        shared_key = shared_data.get_setting(f"api_key:{provider}")
        result["sources"]["shared_data"] = {
            "available": bool(shared_key),
            "value": f"{shared_key[:10]}..." if shared_key else None
        }
    except Exception as e:
        result["sources"]["shared_data"] = {
            "available": False,
            "error": str(e)
        }
    
    # Check environment variable
    env_var_map = {
        "openai": "OPENAI_API_KEY",
        "qwen": "DASHSCOPE_API_KEY", 
        "claude": "ANTHROPIC_API_KEY",
        "huggingface": "HUGGINGFACE_TOKEN"
    }
    
    env_var = env_var_map.get(provider)
    if env_var:
        env_key = os.getenv(env_var)
        result["sources"]["environment"] = {
            "variable": env_var,
            "available": bool(env_key),
            "value": f"{env_key[:10]}..." if env_key else None
        }
    else:
        result["sources"]["environment"] = {
            "available": False,
            "error": f"No environment variable mapping for {provider}"
        }
    
    # Determine which source would be used
    if result["sources"]["shared_data"]["available"]:
        result["active_source"] = "shared_data"
    elif result["sources"]["environment"]["available"]:
        result["active_source"] = "environment"
    else:
        result["active_source"] = None
        
    return result 
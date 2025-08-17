"""
YAML Compatibility Module

Provides a unified yaml interface that works across all platforms,
including iOS where PyYAML is not available.
"""

import logging

logger = logging.getLogger(__name__)

# Try to import yaml libraries with proper fallback for iOS
try:
    # Try ruamel.yaml first (available on iOS)
    from ruamel.yaml import YAML
    _yaml_impl = YAML()
    _yaml_impl.preserve_quotes = True
    
    def safe_load(stream):
        """Load YAML safely using ruamel.yaml"""
        return _yaml_impl.load(stream)
    
    def safe_dump(data, stream=None, **kwargs):
        """Dump YAML safely using ruamel.yaml"""
        if stream is None:
            import io
            stream = io.StringIO()
            _yaml_impl.dump(data, stream)
            return stream.getvalue()
        else:
            _yaml_impl.dump(data, stream)
    
    def load(stream):
        """Load YAML using ruamel.yaml"""
        return _yaml_impl.load(stream)
    
    def dump(data, stream=None, **kwargs):
        """Dump YAML using ruamel.yaml"""
        return safe_dump(data, stream, **kwargs)
    
    YAML_AVAILABLE = True
    logger.info("Using ruamel.yaml for YAML operations")

except ImportError:
    try:
        # Fallback to PyYAML (not available on iOS)
        import yaml as _pyyaml
        
        def safe_load(stream):
            """Load YAML safely using PyYAML"""
            return _pyyaml.safe_load(stream)
        
        def safe_dump(data, stream=None, **kwargs):
            """Dump YAML safely using PyYAML"""
            return _pyyaml.safe_dump(data, stream=stream, **kwargs)
        
        def load(stream):
            """Load YAML using PyYAML"""
            return _pyyaml.safe_load(stream)
        
        def dump(data, stream=None, **kwargs):
            """Dump YAML using PyYAML"""
            return _pyyaml.safe_dump(data, stream=stream, **kwargs)
        
        YAML_AVAILABLE = True
        logger.info("Using PyYAML for YAML operations")
        
    except ImportError:
        # No YAML library available - create stubs
        def safe_load(stream):
            """Stub YAML loader - returns empty dict"""
            logger.warning("No YAML library available, returning empty dict")
            return {}
        
        def safe_dump(data, stream=None, **kwargs):
            """Stub YAML dumper - returns empty string"""
            logger.warning("No YAML library available, cannot dump data")
            if stream is None:
                return ""
            else:
                stream.write("")
        
        def load(stream):
            """Stub YAML loader - returns empty dict"""
            return safe_load(stream)
        
        def dump(data, stream=None, **kwargs):
            """Stub YAML dumper - returns empty string"""
            return safe_dump(data, stream, **kwargs)
        
        YAML_AVAILABLE = False
        logger.warning("No YAML library available - using stubs")

# Export the interface
__all__ = ['safe_load', 'safe_dump', 'load', 'dump', 'YAML_AVAILABLE'] 
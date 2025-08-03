"""
Utils package for document processing scripts.

This package contains utility modules used by the processing tools.
"""

# Import commonly used utilities to make them available at package level
from fichero.batch import BatchProcessor
from fichero.processor import process_file
from fichero.segment_handler import SegmentHandler
from fichero.image_format import (
    ImageFormat, 
    save_image, 
    load_image, 
    get_supported_extensions_list, 
    validate_format,
    get_supported_extensions
)
from fichero.files import (
    get_image_files, 
    ensure_dirs, 
    get_relative_path,
    batch_check_files
)
from fichero.manifest import ManifestProcessor
from fichero.progress import ProcessingProgress, ProgressTracker
from fichero.api_keys import get_qwen_key, get_openai_key, get_claude_key

# LLM utilities (imported lazily due to dependencies)
try:
    from fichero.llm_utils import (
        LLMBackend, 
        ChatGPTBackend, 
        ClaudeBackend, 
        QwenBackend, 
        LMStudioBackend, 
        OllamaBackend,
        get_llm_backend, 
        load_prompt_config,
        LLMProcessor
    )
    from fichero.hierarchy import DocumentHierarchy
    
    __all__ = [
        # Batch processing
        'BatchProcessor', 'process_file',
        # File handling
        'SegmentHandler', 'get_image_files', 'ensure_dirs', 'get_relative_path', 'batch_check_files',
        # Image processing
        'ImageFormat', 'save_image', 'load_image', 'get_supported_extensions_list', 'validate_format', 'get_supported_extensions',
        # Manifest and progress
        'ManifestProcessor', 'ProcessingProgress', 'ProgressTracker',
        # API keys
        'get_qwen_key', 'get_openai_key', 'get_claude_key',
        # LLM utilities
        'LLMBackend', 'ChatGPTBackend', 'ClaudeBackend', 'QwenBackend', 'LMStudioBackend', 'OllamaBackend',
        'get_llm_backend', 'load_prompt_config', 'LLMProcessor',
        # Document hierarchy
        'DocumentHierarchy'
    ]
    
except ImportError:
    # If LLM dependencies aren't available, export the basic utilities
    __all__ = [
        # Batch processing
        'BatchProcessor', 'process_file',
        # File handling
        'SegmentHandler', 'get_image_files', 'ensure_dirs', 'get_relative_path', 'batch_check_files',
        # Image processing
        'ImageFormat', 'save_image', 'load_image', 'get_supported_extensions_list', 'validate_format', 'get_supported_extensions',
        # Manifest and progress
        'ManifestProcessor', 'ProcessingProgress', 'ProgressTracker',
        # API keys
        'get_qwen_key', 'get_openai_key', 'get_claude_key'
    ] 
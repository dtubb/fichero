import os
import torch
from fichero_cli import load_execution_config

def get_best_device():
    """Determine the best available device for model inference."""
    # Check if CPU is forced through environment variable
    force_cpu = os.environ.get('FICHERO_FORCE_CPU', '0') == '1'
    if force_cpu:
        rich_log("info", "Force CPU mode enabled via environment - using CPU for inference")
        return "cpu"
    
    # Check if CPU is forced through config
    try:
        execution_config = load_execution_config()
        hardware_config = execution_config.get('hardware', {})
        if hardware_config.get('force_cpu', False):
            rich_log("info", "Force CPU mode enabled via config - using CPU for inference")
            return "cpu"
    except Exception as e:
        rich_log("warning", f"Could not check execution config for force_cpu: {e}")
    
    # If not forced to CPU, check available devices
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        rich_log("info", "Using MPS (Metal Performance Shaders) for GPU acceleration")
        return "mps"
    elif torch.cuda.is_available():
        rich_log("info", "Using CUDA for GPU acceleration")
        return "cuda"
    else:
        rich_log("info", "Using CPU for inference")
        return "cpu" 
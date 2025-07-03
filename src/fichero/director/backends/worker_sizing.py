"""
Simple Worker Sizing Utility

Provides smart defaults for worker counts and memory based on system resources.
"""

import multiprocessing
import platform
import logging
from typing import Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker configuration with reasoning"""
    cpu_workers: int
    io_workers: int

    reasoning: str


def get_optimal_workers(backend_type: str = "python") -> WorkerConfig:
    """
    Get optimal worker configuration for current system
    
    Args:
        backend_type: 'python' or 'celery'
    
    Returns:
        WorkerConfig with optimal settings
    """
    cpu_count = multiprocessing.cpu_count()
    is_apple_silicon = _is_apple_silicon()
    
    # Simple, effective logic
    if is_apple_silicon:
        # Apple Silicon: Conservative for thermal management
        cpu_workers = max(2, cpu_count // 2)
        io_workers = min(8, cpu_count)
        memory_mb = 2048
        reason = f"Apple Silicon ({cpu_count} cores): Conservative settings for efficiency"
    elif cpu_count >= 12:
        # High-end system
        cpu_workers = max(4, cpu_count // 2)
        io_workers = min(16, cpu_count * 2)
        memory_mb = 2048
        reason = f"High-end system ({cpu_count} cores): Aggressive settings"
    elif cpu_count >= 8:
        # Mid-range system
        cpu_workers = max(3, cpu_count // 2)
        io_workers = min(12, cpu_count * 2)
        memory_mb = 2048
        reason = f"Mid-range system ({cpu_count} cores): Balanced settings"
    else:
        # Entry-level system
        cpu_workers = max(2, cpu_count // 2)
        io_workers = min(8, cpu_count * 2)
        memory_mb = 1024
        reason = f"Entry-level system ({cpu_count} cores): Conservative settings"
    
    # Backend-specific limits
    if backend_type == "python":
        cpu_workers = min(cpu_workers, 8)   # ProcessPool reasonable limit
        io_workers = min(io_workers, 16)    # ThreadPool reasonable limit
    else:  # celery
        cpu_workers = min(cpu_workers, 12)  # Celery can handle more
        io_workers = min(io_workers, 32)
    
    return WorkerConfig(
        cpu_workers=cpu_workers,
        io_workers=io_workers,

        reasoning=reason
    )


def _is_apple_silicon() -> bool:
    """Check if running on Apple Silicon"""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False
    
    try:
        import subprocess
        result = subprocess.run(
            ['sysctl', '-n', 'machdep.cpu.brand_string'],
            capture_output=True, text=True, timeout=2
        )
        return 'Apple' in result.stdout
    except Exception:
        return False


def suggest_backend() -> str:
    """Suggest the best backend for current system"""
    cpu_count = multiprocessing.cpu_count()
    
    # For most users: Python is simpler and works great
    if cpu_count <= 8:
        return "python"
    
    # High-end systems: Could benefit from Celery, but Python is still fine
    return "python"  # Default to simplicity


# Legacy compatibility
def get_optimal_config(workload_type: str = "mixed", backend_type: str = "python") -> WorkerConfig:
    """Legacy compatibility - ignores workload_type for simplicity"""
    return get_optimal_workers(backend_type) 
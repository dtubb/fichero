"""
Director Monitoring System

Unified task monitoring with rich metadata tracking.
Provides both CLI and GUI displays for task progress and system monitoring.
"""

# Core unified monitoring system
from .task_monitor import TaskMonitor, TaskInfo

# Display systems
try:
    from .displays.cli_display import CLITaskDisplay
    CLI_DISPLAY_AVAILABLE = True
except ImportError:
    CLI_DISPLAY_AVAILABLE = False

# Legacy compatibility (for gradual migration)
try:
    from .activity_monitor.base import GlobalActivityMonitor, GlobalTaskInfo, BackendInfo
    LEGACY_ACTIVITY_MONITOR_AVAILABLE = True
except ImportError:
    LEGACY_ACTIVITY_MONITOR_AVAILABLE = False

try:
    from .progress_tracker.base import CoreProgressTracker, ProgressStage, TaskProgress
    LEGACY_PROGRESS_TRACKER_AVAILABLE = True
except ImportError:
    LEGACY_PROGRESS_TRACKER_AVAILABLE = False

__all__ = [
    # New unified system
    'TaskMonitor',
    'TaskInfo',
]

# Add CLI display exports if available
if CLI_DISPLAY_AVAILABLE:
    __all__.extend([
        'CLITaskDisplay',
    ])

# Add legacy exports for backward compatibility
if LEGACY_ACTIVITY_MONITOR_AVAILABLE:
    __all__.extend([
        'GlobalActivityMonitor',
        'GlobalTaskInfo', 
        'BackendInfo'
    ])

if LEGACY_PROGRESS_TRACKER_AVAILABLE:
    __all__.extend([
        'CoreProgressTracker',
        'ProgressStage',
        'TaskProgress'
    ]) 
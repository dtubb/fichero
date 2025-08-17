"""
Activity Monitor Window Package

Desktop window and mobile view for monitoring document processing activity.
Shows real-time task status, worker health, and performance metrics.
"""

from fichero.windows.activity_monitor.activity_window import ActivityMonitorWindow
from fichero.windows.activity_monitor.activity_content import ActivityMonitorContent
from fichero.windows.activity_monitor.mobile_view import ActivityMonitorMobileView

__all__ = [
    'ActivityMonitorWindow',
    'ActivityMonitorContent',
    'ActivityMonitorMobileView'
] 
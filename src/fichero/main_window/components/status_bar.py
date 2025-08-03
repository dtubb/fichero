"""
Status Bar Component for Main Window

Handles status display and collection count.
"""

import toga
from toga.style import Pack
from toga.constants import ROW

import gettext


class StatusBarComponent:
    """Status bar component"""
    
    def __init__(self):
        """Initialize status bar component"""
        self.status_label = None
        self.count_label = None
        self.container = None
    
    def create(self):
        """Create the status bar UI"""
        status_bar = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(10, 0, 0, 0)
            )
        )
        
        # Status label
        self.status_label = toga.Label(
            _("main_window_status_ready"),
            style=Pack(flex=1)
        )
        
        # Collection count
        self.count_label = toga.Label(
            _("main_window_count_zero"),
            style=Pack(margin=(0, 0, 0, 10))
        )
        
        status_bar.add(self.status_label)
        status_bar.add(self.count_label)
        
        self.container = status_bar
        return status_bar
    
    def set_status(self, status: str):
        """Set the status text"""
        if self.status_label:
            self.status_label.text = status
    
    def set_count(self, count: int, total: int = None):
        """Set the collection count"""
        if self.count_label:
            if total is not None:
                self.count_label.text = _("main_window_count_filtered").format(
                    count=count, total=total
                )
            else:
                self.count_label.text = _("main_window_count_total").format(count=count) 
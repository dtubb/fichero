"""
Plans Content Component - Shared UI Logic

This component contains the plans UI logic and can be used
in both desktop windows and mobile views. It handles plan
configuration and management.
"""

import logging
from typing import Dict, Any
from pathlib import Path
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

# Import backend dependencies (keep where they are)
from fichero.config.core.plans_file_manager import PlansManager

logger = logging.getLogger(__name__)


class PlansContent:
    """Plans content component that can be used in windows or as content replacement"""
    
    def __init__(self, app):
        """Initialize the plans content"""
        self.app = app
        
        # Create plans manager
        self.file_manager = PlansManager(app)
        
        # UI state
        self.main_container = None
        
        logger.info("PlansContent initialized")
    
    def create_file_manager(self):
        """Create and return the plans file manager"""
        return PlansManager(self.app)
    
    def get_schema(self):
        """Get the UI schema for plans (placeholder for now)"""
        # For now, return a simple schema
        return {
            "title": "Plans",
            "sections": [
                {
                    "title": "Plan Configuration",
                    "fields": [
                        {
                            "name": "title",
                            "type": "text",
                            "label": "Plan Title"
                        },
                        {
                            "name": "description", 
                            "type": "multiline_text",
                            "label": "Description"
                        }
                    ]
                }
            ]
        }
    
    def create(self):
        """Create the plans content UI"""
        # Create main container
        self.main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=10
            )
        )
        
        # Add title
        title = toga.Label(
            "Plans",
            style=Pack(
                font_size=18,
                font_weight='bold',
                margin_bottom=20
            )
        )
        self.main_container.add(title)
        
        # Add content area
        content_area = self._create_content_area()
        self.main_container.add(content_area)
        
        return self.main_container
    

    
    def _create_content_area(self):
        """Create the main content area"""
        # Load data
        data = self.load_plans()
        
        # Create scrollable content area
        scroll_container = toga.ScrollContainer(
            style=Pack(flex=1)
        )
        
        content_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=10
            )
        )
        
        # Plan title field
        if 'title' in data:
            title_label = toga.Label("Plan Title:", style=Pack(margin_bottom=5))
            content_box.add(title_label)
            
            title_input = toga.TextInput(
                value=data.get('title', ''),
                style=Pack(margin_bottom=15, flex=1)
            )
            content_box.add(title_input)
        
        # Plan description field
        if 'description' in data:
            desc_label = toga.Label("Description:", style=Pack(margin_bottom=5))
            content_box.add(desc_label)
            
            desc_input = toga.MultilineTextInput(
                value=data.get('description', ''),
                style=Pack(margin_bottom=15, flex=1, height=100)
            )
            content_box.add(desc_input)
        
        # Variables section
        if 'vars' in data and data['vars']:
            vars_label = toga.Label("Variables:", style=Pack(margin_bottom=10, font_weight='bold'))
            content_box.add(vars_label)
            
            for key, value in data['vars'].items():
                var_box = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
                
                key_label = toga.Label(f"{key}:", style=Pack(flex=0, width=100, margin_right=10))
                var_box.add(key_label)
                
                value_input = toga.TextInput(
                    value=str(value),
                    style=Pack(flex=1)
                )
                var_box.add(value_input)
                
                content_box.add(var_box)
        
        # Workflows section
        if 'workflows' in data and data['workflows']:
            workflows_label = toga.Label("Workflows:", style=Pack(margin=(20, 0, 10, 0), font_weight='bold'))
            content_box.add(workflows_label)
            
            for workflow_name, workflow_data in data['workflows'].items():
                workflow_box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10))
                
                wf_title = toga.Label(f"• {workflow_name}", style=Pack(font_weight='bold', margin_bottom=5))
                workflow_box.add(wf_title)
                
                if 'description' in workflow_data:
                    wf_desc = toga.Label(workflow_data['description'], style=Pack(margin_left=20, margin_bottom=5))
                    workflow_box.add(wf_desc)
                
                content_box.add(workflow_box)
        
        scroll_container.content = content_box
        return scroll_container
    
    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data"""
        # Store data for later use
        self.original_data = data.copy()
        logger.info(f"Plans data populated: {len(data)} keys")
    
    def load_plans(self):
        """Load plans"""
        try:
            if self.file_manager:
                # Try to get default template
                return self.file_manager.get_default_template()
        except Exception as e:
            logger.error(f"Failed to load plans: {e}")
        
        # Fallback to basic template
        return {
            "title": "New Project",
            "description": "A new project plan",
            "vars": {
                "name": "untitled_project",
                "language": "en",
                "version": "1.0.0"
            },
            "workflows": {
                "default": {
                    "description": "Default workflow",
                    "steps": []
                }
            }
        }
    
    def save_plans(self):
        """Save plans (placeholder for now)"""
        logger.info("Save plans called")
        return True
    
    def refresh(self):
        """Refresh the plans display"""
        logger.info("Refresh plans called")
    
    def get_current_data(self):
        """Get current data from UI (placeholder for now)"""
        return self.load_plans() 
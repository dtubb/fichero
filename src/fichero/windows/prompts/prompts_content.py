"""
Prompts Content Component - Shared UI Logic

This component contains the prompts UI logic and can be used
in both desktop windows and mobile views. It handles prompt
configuration and management.
"""

import logging
from typing import Dict, Any
from pathlib import Path
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

# Import backend dependencies (keep where they are)
from fichero.config.core.prompts_file_manager import PromptsManager

logger = logging.getLogger(__name__)


class PromptsContent:
    """Prompts content component that can be used in windows or as content replacement"""
    
    def __init__(self, app):
        """Initialize the prompts content"""
        self.app = app
        
        # Create prompts manager
        self.file_manager = PromptsManager(app)
        
        # UI state
        self.main_container = None
        
        logger.info("PromptsContent initialized")
    
    def create_file_manager(self):
        """Create and return the prompts file manager"""
        return PromptsManager(self.app)
    
    def get_schema(self):
        """Get the UI schema for prompts (placeholder for now)"""
        # For now, return a simple schema
        return {
            "title": "Prompts",
            "sections": [
                {
                    "title": "Prompt Collection",
                    "fields": [
                        {
                            "name": "title",
                            "type": "text",
                            "label": "Collection Title"
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
        """Create the prompts content UI"""
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
            "Prompts",
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
        data = self.load_prompts()
        
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
        
        # Collection title field
        if 'title' in data:
            title_label = toga.Label("Collection Title:", style=Pack(margin_bottom=5))
            content_box.add(title_label)
            
            title_input = toga.TextInput(
                value=data.get('title', ''),
                style=Pack(margin_bottom=15, flex=1)
            )
            content_box.add(title_input)
        
        # Collection description field
        if 'description' in data:
            desc_label = toga.Label("Description:", style=Pack(margin_bottom=5))
            content_box.add(desc_label)
            
            desc_input = toga.MultilineTextInput(
                value=data.get('description', ''),
                style=Pack(margin_bottom=15, flex=1, height=100)
            )
            content_box.add(desc_input)
        
        # Prompts section
        if 'prompts' in data and data['prompts']:
            prompts_label = toga.Label("Prompts:", style=Pack(margin_bottom=10, font_weight='bold'))
            content_box.add(prompts_label)
            
            for i, prompt in enumerate(data['prompts']):
                prompt_box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=15))
                
                # Prompt name
                if 'name' in prompt:
                    name_label = toga.Label(f"Prompt {i+1}: {prompt['name']}", 
                                          style=Pack(font_weight='bold', margin_bottom=5))
                    prompt_box.add(name_label)
                
                # Prompt description
                if 'description' in prompt:
                    desc_label = toga.Label(prompt['description'], 
                                          style=Pack(margin_left=20, margin_bottom=5))
                    prompt_box.add(desc_label)
                
                # Prompt text
                if 'text' in prompt:
                    text_label = toga.Label("Text:", style=Pack(margin_left=20, margin_bottom=5))
                    prompt_box.add(text_label)
                    
                    text_input = toga.MultilineTextInput(
                        value=prompt['text'],
                        style=Pack(margin_left=20, margin_bottom=10, flex=1, height=80),
                        readonly=True
                    )
                    prompt_box.add(text_input)
                
                content_box.add(prompt_box)
        
        scroll_container.content = content_box
        return scroll_container
    
    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data"""
        # Store data for later use
        self.original_data = data.copy()
        logger.info(f"Prompts data populated: {len(data)} keys")
    
    def load_prompts(self):
        """Load prompts"""
        try:
            if self.file_manager:
                # Try to get default template
                return self.file_manager.get_default_template()
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
        
        # Fallback to basic template
        return {
            "title": "New Prompts Collection",
            "description": "A collection of LLM prompts",
            "prompts": [
                {
                    "name": "Default",
                    "text": "Please help me with the following task:",
                    "description": "A basic prompt template"
                },
                {
                    "name": "Analyze",
                    "text": "Please analyze the following content and provide insights:",
                    "description": "Analysis prompt"
                }
            ]
        }
    
    def save_prompts(self):
        """Save prompts (placeholder for now)"""
        logger.info("Save prompts called")
        return True
    
    def refresh(self):
        """Refresh the prompts display"""
        logger.info("Refresh prompts called")
    
    def get_current_data(self):
        """Get current data from UI (placeholder for now)"""
        return self.load_prompts() 
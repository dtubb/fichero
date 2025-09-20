"""
Transcription Selector Component

UI component for adding transcriptions to the library.
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class TranscriptionSelector:
    """Transcription selector component"""
    
    def __init__(self, app):
        """Initialize transcription selector"""
        self.app = app
        self.on_transcription_added: Optional[Callable] = None
    
    def create(self):
        """Create the transcription selector UI"""
        container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Transcription input
        self.transcription_input = toga.MultilineTextInput(
            placeholder="Enter transcription text...",
            style=Pack(flex=1, margin=(0, 10, 0, 0), height=100)
        )
        container.add(self.transcription_input)
        
        # Add transcription button
        add_button = toga.Button(
            "Add Transcription",
            on_press=self._on_add_transcription,
            style=Pack(flex=0)
        )
        container.add(add_button)
        
        return container
    
    def _on_add_transcription(self, widget):
        """Handle transcription addition"""
        text = self.transcription_input.value.strip()
        if text and self.on_transcription_added:
            self.on_transcription_added(text)
            self.transcription_input.value = ""
    
    def register_callback(self, callback: Callable):
        """Register callback for when transcription is added"""
        self.on_transcription_added = callback

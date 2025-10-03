"""
Navigation state management for Fichero

Defines the navigation contexts and state tracking.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class NavigationContext(Enum):
    """Defines the different navigation contexts in the app"""
    LIBRARY = "library"
    COLLECTION = "collection"
    PREVIEW = "preview"
    # Modal views
    SETTINGS = "settings"
    ACTIVITY_MONITOR = "activity_monitor"
    PROCESSING = "processing"
    PLANS = "plans"
    PROMPTS = "prompts"
    ABOUT = "about"
    ADD = "add"
    RENAME = "rename"


@dataclass
class NavigationState:
    """Represents the current navigation state"""
    context: NavigationContext
    collection_id: Optional[str] = None
    collection_name: Optional[str] = None
    current_path: str = ""  # For hierarchical navigation within collections
    file_path: Optional[str] = None  # For preview context
    metadata: Dict[str, Any] = None
    # Edit mode state preservation
    edit_mode_state: Optional[str] = None  # "normal", "edit", "multi_select"
    edit_context: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.edit_context is None:
            self.edit_context = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization"""
        return {
            'context': self.context.value,
            'collection_id': self.collection_id,
            'collection_name': self.collection_name,
            'current_path': self.current_path,
            'file_path': self.file_path,
            'metadata': self.metadata.copy(),
            'edit_mode_state': self.edit_mode_state,
            'edit_context': self.edit_context.copy()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NavigationState':
        """Create state from dictionary"""
        return cls(
            context=NavigationContext(data['context']),
            collection_id=data.get('collection_id'),
            collection_name=data.get('collection_name'),
            current_path=data.get('current_path', ''),
            file_path=data.get('file_path'),
            metadata=data.get('metadata', {}),
            edit_mode_state=data.get('edit_mode_state'),
            edit_context=data.get('edit_context', {})
        )

    def copy(self) -> 'NavigationState':
        """Create a copy of this state"""
        return NavigationState(
            context=self.context,
            collection_id=self.collection_id,
            collection_name=self.collection_name,
            current_path=self.current_path,
            file_path=self.file_path,
            metadata=self.metadata.copy(),
            edit_mode_state=self.edit_mode_state,
            edit_context=self.edit_context.copy()
        )


class NavigationHistory:
    """Manages navigation history and back navigation"""

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.history: List[NavigationState] = []
        self.current_index: int = -1

    def push(self, state: NavigationState):
        """Push a new state to history"""
        # Remove any forward history if we're not at the end
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]

        # Add new state
        self.history.append(state.copy())
        self.current_index = len(self.history) - 1

        # Limit history size
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
            self.current_index = len(self.history) - 1

        logger.debug(f"Navigation history: pushed {state.context.value}, history size: {len(self.history)}")

    def can_go_back(self) -> bool:
        """Check if we can go back in history"""
        return self.current_index > 0

    def can_go_forward(self) -> bool:
        """Check if we can go forward in history"""
        return self.current_index < len(self.history) - 1

    def go_back(self) -> Optional[NavigationState]:
        """Go back one step in history"""
        if self.can_go_back():
            self.current_index -= 1
            state = self.history[self.current_index]
            logger.debug(f"Navigation history: went back to {state.context.value}")
            return state.copy()
        return None

    def go_forward(self) -> Optional[NavigationState]:
        """Go forward one step in history"""
        if self.can_go_forward():
            self.current_index += 1
            state = self.history[self.current_index]
            logger.debug(f"Navigation history: went forward to {state.context.value}")
            return state.copy()
        return None

    def get_current(self) -> Optional[NavigationState]:
        """Get the current state"""
        if 0 <= self.current_index < len(self.history):
            return self.history[self.current_index].copy()
        return None

    def clear(self):
        """Clear all history"""
        self.history.clear()
        self.current_index = -1
        logger.debug("Navigation history cleared")
"""
App State Manager
Handles session state persistence with async-safe atomic writes.
Manages UI state like current collection, selected items, window layout, etc.
"""

import json
import logging
import asyncio
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages application session state with atomic, async-safe persistence.

    Features:
    - Async-safe writes using asyncio.Lock
    - Atomic file writes with backup for crash recovery
    - Schema validation with sensible defaults
    - Automatic migration from older state formats
    """

    def __init__(self, app=None):
        """
        Initialize state manager.

        Args:
            app: Toga application instance (provides app.paths.data)
        """
        self.app = app
        self._state_file = self._get_state_file_path()
        self._state = self._load_state()
        self._lock = asyncio.Lock()

        logger.info(f"StateManager initialized with state file: {self._state_file}")

    def _get_state_file_path(self) -> Path:
        """Get path to state file using Toga app paths"""
        # Import here to avoid circular dependency
        from fichero.config.core.app_preferences import discover_app_data_directory

        app_data_dir = discover_app_data_directory(self.app)
        return app_data_dir / "app_state.json"

    def _default_state(self) -> Dict[str, Any]:
        """Return default state structure"""
        return {
            "version": "1.0",
            "session": {
                "last_collection_id": None,
                "last_item_id": None,
                "preview_visible": False,
                "column_visibility": {
                    "library": True,
                    "collection": True,
                    "preview": False,
                    "adjust": False
                }
            },
            "window": {
                "size": None,
                "position": None,
                "is_maximized": False
            },
            "layout": {
                "main_layout": {},
                "preview_layout": {}
            },
            "ui_preferences": {
                "show_path_bar": True,
                "show_status_bar": True,
                "collection_sort_key": "name",
                "collection_sort_reverse": False
            },
            "last_saved": None
        }

    def _validate_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate state structure and fill in missing keys with defaults.

        Args:
            state: State dictionary to validate

        Returns:
            Validated state with all required keys
        """
        default = self._default_state()

        # Ensure top-level keys exist
        for key in default:
            if key not in state:
                state[key] = default[key]
                logger.debug(f"Added missing top-level key: {key}")

        # Validate nested structures
        if not isinstance(state.get("session"), dict):
            state["session"] = default["session"]

        if not isinstance(state.get("window"), dict):
            state["window"] = default["window"]

        if not isinstance(state.get("layout"), dict):
            state["layout"] = default["layout"]

        if not isinstance(state.get("ui_preferences"), dict):
            state["ui_preferences"] = default["ui_preferences"]

        # Ensure session keys exist
        for key in default["session"]:
            if key not in state["session"]:
                state["session"][key] = default["session"][key]

        # Ensure window keys exist
        for key in default["window"]:
            if key not in state["window"]:
                state["window"][key] = default["window"][key]

        return state

    def _load_state(self) -> Dict[str, Any]:
        """
        Load state from file with backup fallback.

        Returns:
            State dictionary (validated)
        """
        # Try loading main state file
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    validated = self._validate_state(state)
                    logger.info("✅ Loaded state from file")
                    return validated
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")

            # Try loading backup
            try:
                backup_file = self._state_file.with_suffix('.bak')
                if backup_file.exists():
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                        validated = self._validate_state(state)
                        logger.info("✅ Recovered state from backup file")
                        return validated
            except Exception as backup_error:
                logger.error(f"Failed to load backup state: {backup_error}")

        # Return default state if all else fails
        logger.info("Creating new default state")
        return self._default_state()

    async def save_state(self):
        """
        Save state to file with atomic write and backup.

        Uses async lock to prevent concurrent writes.
        Writes to temp file, backs up existing, then atomic rename.
        """
        async with self._lock:
            try:
                # Update last saved timestamp
                self._state["last_saved"] = datetime.now().isoformat()

                # Ensure parent directory exists
                self._state_file.parent.mkdir(parents=True, exist_ok=True)

                # Write to temporary file first (use parent / name to avoid suffix issues)
                temp_file = self._state_file.parent / (self._state_file.name + '.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self._state, f, indent=2, ensure_ascii=False)
                    f.flush()  # Ensure data is written to disk

                # Backup existing state file
                if self._state_file.exists():
                    backup_file = self._state_file.parent / (self._state_file.name + '.bak')
                    shutil.copy2(self._state_file, backup_file)

                # Atomic rename (overwrites existing file)
                temp_file.replace(self._state_file)

                logger.debug("✅ State saved successfully")

            except Exception as e:
                logger.error(f"Failed to save state: {e}")
                import traceback
                traceback.print_exc()

    # Session state accessors

    def get_last_collection_id(self) -> Optional[str]:
        """Get ID of last viewed collection"""
        return self._state["session"].get("last_collection_id")

    def set_last_collection_id(self, collection_id: Optional[str]):
        """Set ID of last viewed collection"""
        self._state["session"]["last_collection_id"] = collection_id

    def get_last_item_id(self) -> Optional[str]:
        """Get ID of last viewed item"""
        return self._state["session"].get("last_item_id")

    def set_last_item_id(self, item_id: Optional[str]):
        """Set ID of last viewed item"""
        self._state["session"]["last_item_id"] = item_id

    def get_preview_visible(self) -> bool:
        """Check if preview pane was visible"""
        return self._state["session"].get("preview_visible", False)

    def set_preview_visible(self, visible: bool):
        """Set preview pane visibility state"""
        self._state["session"]["preview_visible"] = visible

    def get_column_visibility(self, column_name: str) -> bool:
        """Get visibility state of a column"""
        return self._state["session"]["column_visibility"].get(column_name, True)

    def set_column_visibility(self, column_name: str, visible: bool):
        """Set visibility state of a column"""
        self._state["session"]["column_visibility"][column_name] = visible

    # Window state accessors

    def get_window_size(self) -> Optional[tuple]:
        """Get saved window size as (width, height)"""
        size = self._state["window"].get("size")
        if size and isinstance(size, list) and len(size) == 2:
            return tuple(size)
        return None

    def set_window_size(self, width: int, height: int):
        """Set window size"""
        self._state["window"]["size"] = [width, height]

    def get_window_position(self) -> Optional[tuple]:
        """Get saved window position as (x, y)"""
        pos = self._state["window"].get("position")
        if pos and isinstance(pos, list) and len(pos) == 2:
            return tuple(pos)
        return None

    def set_window_position(self, x: int, y: int):
        """Set window position"""
        self._state["window"]["position"] = [x, y]

    def get_window_maximized(self) -> bool:
        """Check if window was maximized"""
        return self._state["window"].get("is_maximized", False)

    def set_window_maximized(self, maximized: bool):
        """Set window maximized state"""
        self._state["window"]["is_maximized"] = maximized

    # Layout state accessors

    def get_main_layout_state(self) -> Dict[str, Any]:
        """Get main layout state"""
        return self._state["layout"].get("main_layout", {})

    def set_main_layout_state(self, layout_state: Dict[str, Any]):
        """Set main layout state"""
        self._state["layout"]["main_layout"] = layout_state

    def get_preview_layout_state(self) -> Dict[str, Any]:
        """Get preview layout state"""
        return self._state["layout"].get("preview_layout", {})

    def set_preview_layout_state(self, layout_state: Dict[str, Any]):
        """Set preview layout state"""
        self._state["layout"]["preview_layout"] = layout_state

    # UI preferences accessors

    def get_ui_preference(self, key: str, default=None):
        """Get UI preference value"""
        return self._state["ui_preferences"].get(key, default)

    def set_ui_preference(self, key: str, value: Any):
        """Set UI preference value"""
        self._state["ui_preferences"][key] = value

    # Convenience methods

    def get_session_state(self) -> Dict[str, Any]:
        """Get complete session state"""
        return self._state["session"].copy()

    def clear_session_state(self):
        """Clear session state (but keep window/layout state)"""
        self._state["session"] = self._default_state()["session"]
        logger.info("Session state cleared")

    def reset_to_defaults(self):
        """Reset all state to defaults"""
        self._state = self._default_state()
        logger.info("State reset to defaults")

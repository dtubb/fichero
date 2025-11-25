"""
App State Manager
Handles session state persistence with async-safe atomic writes.
Manages UI state like current collection, selected items, window layout, etc.

Version 3.0 consolidates app_preferences.json into app_state.json and adds:
- Multi-window state tracking
- Preview viewer state (zoom, scroll, rotation)
- Pane content tracking (what's loaded in each pane)
"""

import json
import logging
import asyncio
import shutil
import math
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Current state version
STATE_VERSION = "3.0"


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
        self._lock = None  # Lazy initialization to avoid event loop issues

        logger.info(f"StateManager initialized with state file: {self._state_file}")

    def _get_state_file_path(self) -> Path:
        """Get path to state file using Toga app paths"""
        # Import here to avoid circular dependency
        try:
            from fichero.config.core.app_preferences import discover_app_data_directory
            app_data_dir = discover_app_data_directory(self.app)
            return app_data_dir / "app_state.json"
        except ImportError as e:
            logger.warning(f"Could not import app_preferences: {e}")
            # Fallback to a default location
            from pathlib import Path
            fallback_dir = Path.home() / ".fichero"
            fallback_dir.mkdir(exist_ok=True)
            return fallback_dir / "app_state.json"

    def _default_state(self) -> Dict[str, Any]:
        """Return default state structure"""
        return {
            "version": STATE_VERSION,
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
            # Multi-window state tracking (v3.0)
            "windows": {
                # Per-window state by identifier
                # e.g., "main": {"x": 100, "y": 100, "width": 1200, "height": 800, ...}
            },
            # Migrated from app_preferences.json (v3.0)
            "preferences": {
                "active_settings_file": None,
                "recent_documents": [],
                "open_documents": [],
                "last_used_directories": {},
                "preferred_plan": None,
                "preferred_workflow": None
            },
            # Preview viewer state - zoom/scroll restored on restart (v3.0)
            "preview_viewer_state": {
                "scale": 1.0,
                "rotation": 0,
                "scroll_x": 0,
                "scroll_y": 0
            },
            # Pane content tracking - what's loaded in each pane (v3.0)
            "pane_content": {
                "library": {
                    "selected_collection_id": None,
                    "scroll_position": 0
                },
                "collection": {
                    "collection_id": None,
                    "selected_item_id": None,
                    "scroll_position": 0
                },
                "preview_image": {
                    "item_id": None
                },
                "preview_metadata": {
                    "item_id": None,
                    "scroll_position": 0
                },
                "adjust": {
                    "item_id": None,
                    "active_tab": "crop"
                }
            },
            # Legacy window state (kept for backwards compatibility)
            "window": {
                "size": None,
                "position": None,
                "is_maximized": False,
                "display_id": None,
                "display_bounds": None,
                "state_change_count": 0
            },
            "pane_visibility": {
                # Keys match actual layout manager column names (lowercase)
                # Column names: "Library", "Collection", "PreviewImage", "PreviewMetadata", "Adjust"
                "library": True,
                "collection": True,
                "previewimage": True,      # Image preview pane
                "previewmetadata": True,   # Metadata preview pane
                "adjust": False,           # Adjust/Info pane (right sidebar)
                # Legacy keys kept for backward compatibility
                "sidebar": True,           # Alias for library
                "preview": True,           # Legacy - maps to previewimage
                "inspector": False,        # Alias for adjust
                "status_bar": True,
                "toolbar": True
            },
            "layout": {
                "main_layout": {},
                "preview_layout": {},
                "dimensions": {
                    "sidebar_width": 200,
                    "collection_width": 300,
                    "preview_width": None,
                    "inspector_width": 250
                },
                "proportions": {
                    "preview_ratio": 0.6,
                    "sidebar_proportion": 0.2,
                    "collection_proportion": 0.3,
                    "preview_proportion": 0.5
                },
                "split_orientation": "horizontal",
                "focus_state": {
                    "active_pane": None,
                    "last_focused_pane": None
                }
            },
            "preview_config": {
                "layout_type": "side_by_side",
                "ratio_presets": {
                    "balanced": 0.5,
                    "content_focused": 0.6,
                    "image_focused": 0.4,
                    "wide_content": 0.75,
                    "wide_image": 0.25
                },
                "current_preset": "wide_content",
                "custom_ratio": None,
                "context_preservation": True
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
        Handles migration from older state formats.

        Args:
            state: State dictionary to validate

        Returns:
            Validated state with all required keys
        """
        default = self._default_state()

        # Handle version migration
        version = state.get("version", "1.0")
        if version == "1.0":
            state = self._migrate_from_v1(state)
            version = "2.0"
            logger.info("Migrated state from version 1.0 to 2.0")

        if version == "2.0":
            state = self._migrate_from_v2(state)
            logger.info("Migrated state from version 2.0 to 3.0")

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

        if not isinstance(state.get("pane_visibility"), dict):
            state["pane_visibility"] = default["pane_visibility"]

        if not isinstance(state.get("preview_config"), dict):
            state["preview_config"] = default["preview_config"]

        if not isinstance(state.get("ui_preferences"), dict):
            state["ui_preferences"] = default["ui_preferences"]

        # Recursively ensure all nested keys exist
        def merge_nested(target: dict, source: dict):
            for key, value in source.items():
                if key not in target:
                    target[key] = value
                elif isinstance(value, dict) and isinstance(target[key], dict):
                    merge_nested(target[key], value)

        merge_nested(state["session"], default["session"])
        merge_nested(state["window"], default["window"])
        merge_nested(state["layout"], default["layout"])
        merge_nested(state["pane_visibility"], default["pane_visibility"])
        merge_nested(state["preview_config"], default["preview_config"])
        merge_nested(state["ui_preferences"], default["ui_preferences"])

        # Validate numeric values
        self._validate_numeric_values(state)

        return state

    def _migrate_from_v1(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate state from version 1.0 to 2.0.

        Args:
            state: Version 1.0 state dictionary

        Returns:
            Migrated state dictionary
        """
        # Start with default v2.0 structure
        new_state = self._default_state()

        # Preserve existing data
        if "session" in state:
            new_state["session"].update(state["session"])

        if "window" in state:
            # Migrate existing window state
            for key in ["size", "position", "is_maximized"]:
                if key in state["window"]:
                    new_state["window"][key] = state["window"][key]

        if "layout" in state:
            new_state["layout"]["main_layout"] = state["layout"].get("main_layout", {})
            new_state["layout"]["preview_layout"] = state["layout"].get("preview_layout", {})

        if "ui_preferences" in state:
            new_state["ui_preferences"].update(state["ui_preferences"])

        # Migrate column_visibility to pane_visibility
        if "session" in state and "column_visibility" in state["session"]:
            col_vis = state["session"]["column_visibility"]
            new_state["pane_visibility"]["sidebar"] = col_vis.get("library", True)
            new_state["pane_visibility"]["collection"] = col_vis.get("collection", True)
            new_state["pane_visibility"]["preview"] = col_vis.get("preview", False)
            new_state["pane_visibility"]["inspector"] = col_vis.get("adjust", False)

        new_state["version"] = "2.0"
        return new_state

    def _migrate_from_v2(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate state from version 2.0 to 3.0.

        Adds:
        - windows: Multi-window state tracking
        - preferences: Migrated from app_preferences.json
        - preview_viewer_state: Zoom/scroll state
        - pane_content: What's loaded in each pane

        Args:
            state: Version 2.0 state dictionary

        Returns:
            Migrated state dictionary
        """
        default = self._default_state()

        # Add new v3.0 sections if missing
        if "windows" not in state:
            state["windows"] = default["windows"]

        if "preferences" not in state:
            state["preferences"] = default["preferences"]
            # Try to migrate from app_preferences.json
            self._migrate_app_preferences(state)

        if "preview_viewer_state" not in state:
            state["preview_viewer_state"] = default["preview_viewer_state"]

        if "pane_content" not in state:
            state["pane_content"] = default["pane_content"]

        state["version"] = STATE_VERSION
        return state

    def _migrate_app_preferences(self, state: Dict[str, Any]):
        """
        Migrate data from app_preferences.json into state.

        This is called during v2 -> v3 migration to consolidate files.
        """
        try:
            # Find app_preferences.json
            prefs_file = self._state_file.parent / "app_preferences.json"
            if not prefs_file.exists():
                logger.debug("No app_preferences.json found to migrate")
                return

            with open(prefs_file, 'r', encoding='utf-8') as f:
                prefs = json.load(f)

            # Migrate preferences data
            if "preferences" not in state:
                state["preferences"] = {}

            prefs_section = state["preferences"]
            prefs_section["active_settings_file"] = prefs.get("active_settings_file")
            prefs_section["recent_documents"] = prefs.get("recent_documents", [])
            prefs_section["open_documents"] = prefs.get("open_documents", [])
            prefs_section["last_used_directories"] = prefs.get("last_used_directories", {})
            prefs_section["preferred_plan"] = prefs.get("preferred_plan")
            prefs_section["preferred_workflow"] = prefs.get("preferred_workflow")

            # Migrate window positions to new windows section
            old_window_positions = prefs.get("window_positions", {})
            if old_window_positions and "windows" in state:
                for window_id, pos in old_window_positions.items():
                    state["windows"][window_id] = pos

            logger.info(f"Migrated app_preferences.json to app_state.json")

            # Rename the old file instead of deleting
            backup_path = prefs_file.with_suffix('.json.migrated')
            prefs_file.rename(backup_path)
            logger.info(f"Renamed old preferences file to {backup_path}")

        except Exception as e:
            logger.warning(f"Failed to migrate app_preferences.json: {e}")

    def _validate_ratio(self, value: Any, min_val: float = 0.1, max_val: float = 0.9, default: float = 0.5) -> float:
        """
        Validate and clamp ratio values to prevent NaN, infinity, and extreme values.

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            default: Default value if validation fails

        Returns:
            Valid ratio value between min_val and max_val
        """
        # Handle None or non-numeric values
        if value is None or not isinstance(value, (int, float)):
            logger.warning(f"Invalid ratio value {value}, using default {default}")
            return default

        # Handle NaN
        if math.isnan(value):
            logger.warning(f"Ratio value is NaN, using default {default}")
            return default

        # Handle infinity
        if math.isinf(value):
            logger.warning(f"Ratio value is infinite, using default {default}")
            return default

        # Clamp to valid range
        if value < min_val:
            logger.debug(f"Ratio value {value} below minimum {min_val}, clamping")
            return min_val
        elif value > max_val:
            logger.debug(f"Ratio value {value} above maximum {max_val}, clamping")
            return max_val

        return float(value)

    def _validate_dimension(self, value: Any, min_val: int = 50) -> Optional[int]:
        """
        Validate dimension values to prevent negative or extreme values.

        Args:
            value: Value to validate
            min_val: Minimum allowed value

        Returns:
            Valid dimension value or None
        """
        if value is None:
            return None

        if not isinstance(value, (int, float)):
            logger.warning(f"Invalid dimension value {value}, using None")
            return None

        # Handle NaN and infinity
        if math.isnan(value) or math.isinf(value):
            logger.warning(f"Dimension value is NaN or infinite: {value}, using None")
            return None

        # Ensure positive and reasonable
        if value < min_val:
            logger.debug(f"Dimension value {value} below minimum {min_val}, clamping")
            return min_val

        # Cap at reasonable maximum (10000px should be enough for any display)
        if value > 10000:
            logger.warning(f"Dimension value {value} extremely large, clamping to 10000")
            return 10000

        return int(value)

    def _validate_numeric_values(self, state: Dict[str, Any]):
        """
        Validate numeric values are within reasonable ranges using comprehensive validation.

        Args:
            state: State dictionary to validate
        """
        # Validate proportions are between 0 and 1
        proportions = state["layout"]["proportions"]
        for key, value in proportions.items():
            proportions[key] = self._validate_ratio(value, 0.1, 0.9, 0.5)

        # Validate preview ratio presets
        presets = state["preview_config"]["ratio_presets"]
        for key, value in presets.items():
            presets[key] = self._validate_ratio(value, 0.1, 0.9, 0.5)

        # Validate dimensions are positive
        dimensions = state["layout"]["dimensions"]
        for key, value in dimensions.items():
            if value is not None:
                dimensions[key] = self._validate_dimension(value, 100)

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

    def _get_or_create_lock(self):
        """Get or create the async lock, handling cases where no event loop exists."""
        if self._lock is None:
            try:
                # Try to get the current event loop
                asyncio.get_running_loop()
                self._lock = asyncio.Lock()
            except RuntimeError:
                # No event loop is running, we'll handle this in save_state
                pass
        return self._lock

    async def save_state(self):
        """
        Save state to file with atomic write and backup.

        Uses async lock to prevent concurrent writes.
        Writes to temp file, backs up existing, then atomic rename.
        """
        lock = self._get_or_create_lock()
        if lock is None:
            # No event loop available, fall back to synchronous save
            logger.debug("No event loop available, using synchronous save")
            self._save_state_sync()
            return

        async with lock:
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

                logger.debug("✅ State saved successfully (async)")

            except Exception as e:
                logger.error(f"Failed to save state (async): {e}")
                import traceback
                traceback.print_exc()

    def _save_state_sync(self):
        """
        Synchronous version of save_state for when no event loop is available.
        """
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

            logger.debug("✅ State saved successfully (sync)")

        except Exception as e:
            logger.error(f"Failed to save state (sync): {e}")
            import traceback
            traceback.print_exc()

    def save_state_sync(self):
        """
        Public synchronous save method for use when async is not available.
        """
        self._save_state_sync()

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

    # =========================================================================
    # DEPRECATED: Legacy single-window methods (use multi-window API instead)
    # The methods below write to the "window" section for backwards compatibility.
    # New code should use get_window_state(window_id) and set_window_state(window_id, state)
    # which write to the "windows" section with per-window tracking.
    # =========================================================================

    def get_window_size(self) -> Optional[tuple]:
        """Get saved window size as (width, height)

        DEPRECATED: Use get_window_state(window_id)['width'/'height'] instead.
        """
        size = self._state["window"].get("size")
        if size and isinstance(size, list) and len(size) == 2:
            return tuple(size)
        return None

    def set_window_size(self, width: int, height: int):
        """Set window size

        DEPRECATED: Use set_window_state(window_id, {...}) instead.
        """
        self._state["window"]["size"] = [width, height]

    def get_window_position(self) -> Optional[tuple]:
        """Get saved window position as (x, y)

        DEPRECATED: Use get_window_state(window_id)['x'/'y'] instead.
        """
        pos = self._state["window"].get("position")
        if pos and isinstance(pos, list) and len(pos) == 2:
            return tuple(pos)
        return None

    def set_window_position(self, x: int, y: int):
        """Set window position

        DEPRECATED: Use set_window_state(window_id, {...}) instead.
        """
        self._state["window"]["position"] = [x, y]

    def get_window_maximized(self) -> bool:
        """Check if window was maximized

        DEPRECATED: Use get_window_state(window_id) instead.
        """
        return self._state["window"].get("is_maximized", False)

    def set_window_maximized(self, maximized: bool):
        """Set window maximized state

        DEPRECATED: Use set_window_state(window_id, {...}) instead.
        """
        self._state["window"]["is_maximized"] = maximized

    def get_window_display_id(self) -> Optional[str]:
        """Get saved display ID for multi-monitor support

        DEPRECATED: Use get_window_state(window_id)['display_id'] instead.
        """
        return self._state["window"].get("display_id")

    def set_window_display_id(self, display_id: Optional[str]):
        """Set display ID for multi-monitor support

        DEPRECATED: Use set_window_state(window_id, {...}) instead.
        """
        self._state["window"]["display_id"] = display_id

    def get_window_display_bounds(self) -> Optional[dict]:
        """Get saved display bounds for position validation"""
        return self._state["window"].get("display_bounds")

    def set_window_display_bounds(self, bounds: Optional[dict]):
        """Set display bounds for position validation"""
        self._state["window"]["display_bounds"] = bounds

    def increment_window_state_changes(self):
        """Increment window state change counter for tracking"""
        self._state["window"]["state_change_count"] = \
            self._state["window"].get("state_change_count", 0) + 1

    def get_window_state_change_count(self) -> int:
        """Get window state change count"""
        return self._state["window"].get("state_change_count", 0)

    def validate_window_position(self, x: int, y: int) -> tuple:
        """
        Validate window position against display bounds.

        Args:
            x: Window x position
            y: Window y position

        Returns:
            Validated (x, y) position tuple
        """
        bounds = self.get_window_display_bounds()
        if not bounds:
            return (x, y)  # No bounds info, return as-is

        # Ensure window is visible on screen
        min_x = bounds.get("x", 0)
        min_y = bounds.get("y", 0)
        max_x = bounds.get("width", 1920) - 100  # Leave 100px for window controls
        max_y = bounds.get("height", 1080) - 100

        validated_x = max(min_x, min(x, max_x))
        validated_y = max(min_y, min(y, max_y))

        return (validated_x, validated_y)

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

    # Pane visibility accessors

    def get_pane_visibility(self, pane_name: str) -> bool:
        """
        Get visibility state of a pane.

        Args:
            pane_name: Name of the pane (sidebar, collection, preview, inspector, status_bar, toolbar)

        Returns:
            True if pane is visible, False otherwise
        """
        return self._state["pane_visibility"].get(pane_name, True)

    def set_pane_visibility(self, pane_name: str, visible: bool):
        """
        Set visibility state of a pane.

        Args:
            pane_name: Name of the pane
            visible: True to show, False to hide
        """
        self._state["pane_visibility"][pane_name] = visible

    def toggle_pane_visibility(self, pane_name: str) -> bool:
        """
        Toggle visibility state of a pane.

        Args:
            pane_name: Name of the pane to toggle

        Returns:
            New visibility state
        """
        current = self.get_pane_visibility(pane_name)
        new_state = not current
        self.set_pane_visibility(pane_name, new_state)
        return new_state

    def get_all_pane_visibility(self) -> Dict[str, bool]:
        """Get visibility states for all panes"""
        return self._state["pane_visibility"].copy()

    def set_all_pane_visibility(self, visibility_states: Dict[str, bool]):
        """
        Set visibility states for multiple panes.

        Args:
            visibility_states: Dictionary mapping pane names to visibility states
        """
        for pane_name, visible in visibility_states.items():
            self.set_pane_visibility(pane_name, visible)

    # Layout dimensions and proportions accessors

    def get_pane_dimension(self, dimension_name: str) -> Optional[int]:
        """
        Get saved dimension for a pane.

        Args:
            dimension_name: Name of dimension (sidebar_width, collection_width, etc.)

        Returns:
            Dimension in pixels, or None if not set
        """
        return self._state["layout"]["dimensions"].get(dimension_name)

    def set_pane_dimension(self, dimension_name: str, value: Optional[int]):
        """
        Set dimension for a pane with comprehensive validation.

        Args:
            dimension_name: Name of dimension
            value: Dimension in pixels, or None to unset
        """
        validated_value = self._validate_dimension(value, 50) if value is not None else None
        self._state["layout"]["dimensions"][dimension_name] = validated_value
        logger.debug(f"Set pane dimension {dimension_name} to {validated_value}")

    def get_layout_proportion(self, proportion_name: str) -> float:
        """
        Get layout proportion value.

        Args:
            proportion_name: Name of proportion (preview_ratio, sidebar_proportion, etc.)

        Returns:
            Proportion value between 0.1 and 0.9
        """
        return self._state["layout"]["proportions"].get(proportion_name, 0.5)

    def set_layout_proportion(self, proportion_name: str, value: float):
        """
        Set layout proportion value with comprehensive validation.

        Args:
            proportion_name: Name of proportion
            value: Proportion value (will be validated and clamped to 0.1-0.9)
        """
        validated_value = self._validate_ratio(value, 0.1, 0.9, 0.5)
        self._state["layout"]["proportions"][proportion_name] = validated_value
        logger.debug(f"Set layout proportion {proportion_name} to {validated_value}")

    def get_split_orientation(self) -> str:
        """Get split pane orientation (horizontal or vertical)"""
        return self._state["layout"].get("split_orientation", "horizontal")

    def set_split_orientation(self, orientation: str):
        """
        Set split pane orientation.

        Args:
            orientation: Either 'horizontal' or 'vertical'
        """
        if orientation in ["horizontal", "vertical"]:
            self._state["layout"]["split_orientation"] = orientation

    def get_active_pane(self) -> Optional[str]:
        """Get currently active/focused pane"""
        return self._state["layout"]["focus_state"].get("active_pane")

    def set_active_pane(self, pane_name: Optional[str]):
        """
        Set currently active/focused pane.

        Args:
            pane_name: Name of the active pane, or None
        """
        focus_state = self._state["layout"]["focus_state"]
        if focus_state.get("active_pane") != pane_name:
            focus_state["last_focused_pane"] = focus_state.get("active_pane")
        focus_state["active_pane"] = pane_name

    def get_last_focused_pane(self) -> Optional[str]:
        """Get last focused pane (useful for focus restoration)"""
        return self._state["layout"]["focus_state"].get("last_focused_pane")

    # Preview configuration accessors

    def get_preview_layout_type(self) -> str:
        """Get preview layout type (side_by_side, stacked, etc.)"""
        return self._state["preview_config"].get("layout_type", "side_by_side")

    def set_preview_layout_type(self, layout_type: str):
        """
        Set preview layout type.

        Args:
            layout_type: Layout type string
        """
        self._state["preview_config"]["layout_type"] = layout_type

    def get_preview_ratio_presets(self) -> Dict[str, float]:
        """Get all preview ratio presets"""
        return self._state["preview_config"]["ratio_presets"].copy()

    def get_preview_ratio_preset(self, preset_name: str) -> Optional[float]:
        """
        Get specific preview ratio preset.

        Args:
            preset_name: Name of the preset (balanced, content_focused, etc.)

        Returns:
            Ratio value or None if preset doesn't exist
        """
        return self._state["preview_config"]["ratio_presets"].get(preset_name)

    def set_preview_ratio_preset(self, preset_name: str, ratio: float):
        """
        Set preview ratio preset with comprehensive validation.

        Args:
            preset_name: Name of the preset
            ratio: Ratio value (will be validated and clamped to 0.1-0.9)
        """
        validated_ratio = self._validate_ratio(ratio, 0.1, 0.9, 0.5)
        self._state["preview_config"]["ratio_presets"][preset_name] = validated_ratio
        logger.debug(f"Set preview ratio preset {preset_name} to {validated_ratio}")

    def get_current_preview_preset(self) -> str:
        """Get name of currently active preview ratio preset"""
        return self._state["preview_config"].get("current_preset", "content_focused")

    def set_current_preview_preset(self, preset_name: str):
        """
        Set current preview ratio preset and apply its ratio.

        Args:
            preset_name: Name of the preset to activate
        """
        if preset_name in self._state["preview_config"]["ratio_presets"]:
            self._state["preview_config"]["current_preset"] = preset_name
            # Also update the active preview ratio
            ratio = self._state["preview_config"]["ratio_presets"][preset_name]
            self.set_layout_proportion("preview_ratio", ratio)

    def get_custom_preview_ratio(self) -> Optional[float]:
        """Get custom preview ratio (if not using a preset)"""
        return self._state["preview_config"].get("custom_ratio")

    def set_custom_preview_ratio(self, ratio: Optional[float]):
        """
        Set custom preview ratio with comprehensive validation.

        Args:
            ratio: Custom ratio value, or None to clear
        """
        if ratio is not None:
            ratio = self._validate_ratio(ratio, 0.1, 0.9, 0.5)
        self._state["preview_config"]["custom_ratio"] = ratio
        if ratio is not None:
            # Clear current preset when using custom ratio
            self._state["preview_config"]["current_preset"] = "custom"
            self.set_layout_proportion("preview_ratio", ratio)
        logger.debug(f"Set custom preview ratio to {ratio}")

    def get_preview_context_preservation(self) -> bool:
        """Check if preview context should be preserved across selections"""
        return self._state["preview_config"].get("context_preservation", True)

    def set_preview_context_preservation(self, preserve: bool):
        """
        Set preview context preservation setting.

        Args:
            preserve: True to preserve context, False to reset on each selection
        """
        self._state["preview_config"]["context_preservation"] = preserve

    def apply_preview_preset_ratio(self, preset_name: str) -> bool:
        """
        Apply a preview preset ratio and make it current.

        Args:
            preset_name: Name of the preset to apply

        Returns:
            True if preset was applied, False if preset doesn't exist
        """
        ratio = self.get_preview_ratio_preset(preset_name)
        if ratio is not None:
            self.set_current_preview_preset(preset_name)
            return True
        return False

    # Convenience methods for common layout operations

    def reset_layout_to_defaults(self):
        """Reset layout configuration to default values"""
        default = self._default_state()
        self._state["layout"] = default["layout"]
        self._state["pane_visibility"] = default["pane_visibility"]
        self._state["preview_config"] = default["preview_config"]
        logger.info("Layout configuration reset to defaults")

    def get_compact_layout_summary(self) -> Dict[str, Any]:
        """
        Get a compact summary of the current layout state for debugging.

        Returns:
            Dictionary with key layout information
        """
        return {
            "panes_visible": {
                name: visible for name, visible in self._state["pane_visibility"].items()
                if visible  # Only show visible panes
            },
            "dimensions": {
                name: dim for name, dim in self._state["layout"]["dimensions"].items()
                if dim is not None
            },
            "proportions": self._state["layout"]["proportions"],
            "active_pane": self.get_active_pane(),
            "preview_preset": self.get_current_preview_preset(),
            "split_orientation": self.get_split_orientation()
        }

    def save_layout_snapshot(self, snapshot_name: str):
        """
        Save current layout as a named snapshot.

        Args:
            snapshot_name: Name for the snapshot
        """
        snapshot = {
            "pane_visibility": self._state["pane_visibility"].copy(),
            "dimensions": self._state["layout"]["dimensions"].copy(),
            "proportions": self._state["layout"]["proportions"].copy(),
            "preview_config": self._state["preview_config"].copy(),
            "split_orientation": self.get_split_orientation()
        }

        if "layout_snapshots" not in self._state:
            self._state["layout_snapshots"] = {}

        self._state["layout_snapshots"][snapshot_name] = snapshot
        logger.info(f"Layout snapshot '{snapshot_name}' saved")

    def restore_layout_snapshot(self, snapshot_name: str) -> bool:
        """
        Restore layout from a named snapshot.

        Args:
            snapshot_name: Name of the snapshot to restore

        Returns:
            True if snapshot was restored, False if snapshot doesn't exist
        """
        snapshots = self._state.get("layout_snapshots", {})
        if snapshot_name not in snapshots:
            return False

        snapshot = snapshots[snapshot_name]

        # Restore layout state
        self._state["pane_visibility"] = snapshot["pane_visibility"].copy()
        self._state["layout"]["dimensions"] = snapshot["dimensions"].copy()
        self._state["layout"]["proportions"] = snapshot["proportions"].copy()
        self._state["preview_config"] = snapshot["preview_config"].copy()
        self.set_split_orientation(snapshot["split_orientation"])

        logger.info(f"Layout snapshot '{snapshot_name}' restored")
        return True

    def get_available_snapshots(self) -> list:
        """Get list of available layout snapshot names"""
        return list(self._state.get("layout_snapshots", {}).keys())

    # UI preferences accessors

    def get_ui_preference(self, key: str, default=None):
        """Get UI preference value"""
        return self._state["ui_preferences"].get(key, default)

    def set_ui_preference(self, key: str, value: Any):
        """Set UI preference value"""
        self._state["ui_preferences"][key] = value

    # Backwards compatibility methods (deprecated - use pane_visibility instead)
    # These are the main backward compatibility methods - keep these

    # Enhanced convenience methods

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

    def get_complete_state_summary(self) -> Dict[str, Any]:
        """
        Get a complete summary of all state for debugging and inspection.

        Returns:
            Dictionary containing all current state information
        """
        return {
            "version": self._state.get("version"),
            "window": {
                "size": self.get_window_size(),
                "position": self.get_window_position(),
                "maximized": self.get_window_maximized(),
                "display_id": self.get_window_display_id(),
                "state_changes": self.get_window_state_change_count()
            },
            "layout_summary": self.get_compact_layout_summary(),
            "session": {
                "last_collection": self.get_last_collection_id(),
                "last_item": self.get_last_item_id(),
                "preview_visible": self.get_preview_visible()
            },
            "preview_config": {
                "layout_type": self.get_preview_layout_type(),
                "current_preset": self.get_current_preview_preset(),
                "custom_ratio": self.get_custom_preview_ratio(),
                "context_preservation": self.get_preview_context_preservation()
            },
            "snapshots_available": self.get_available_snapshots(),
            "last_saved": self._state.get("last_saved")
        }

    def export_layout_config(self) -> Dict[str, Any]:
        """
        Export current layout configuration for sharing or backup.

        Returns:
            Dictionary containing exportable layout configuration
        """
        return {
            "version": "3.0",
            "pane_visibility": self.get_all_pane_visibility(),
            "dimensions": {
                name: self.get_pane_dimension(name)
                for name in ["sidebar_width", "collection_width", "preview_width", "inspector_width"]
            },
            "proportions": {
                name: self.get_layout_proportion(name)
                for name in ["preview_ratio", "sidebar_proportion", "collection_proportion", "preview_proportion"]
            },
            "split_orientation": self.get_split_orientation(),
            "preview_config": {
                "layout_type": self.get_preview_layout_type(),
                "ratio_presets": self.get_preview_ratio_presets(),
                "current_preset": self.get_current_preview_preset(),
                "custom_ratio": self.get_custom_preview_ratio(),
                "context_preservation": self.get_preview_context_preservation()
            }
        }

    def import_layout_config(self, config: Dict[str, Any]) -> bool:
        """
        Import layout configuration from exported config.

        Args:
            config: Exported layout configuration dictionary

        Returns:
            True if import was successful, False otherwise
        """
        try:
            # Validate config structure (accept v2.0 or v3.0 for backward compatibility)
            if not isinstance(config, dict) or config.get("version") not in ("2.0", "3.0"):
                logger.warning("Invalid layout config format")
                return False

            # Import pane visibility
            if "pane_visibility" in config:
                self.set_all_pane_visibility(config["pane_visibility"])

            # Import dimensions
            if "dimensions" in config:
                for name, value in config["dimensions"].items():
                    if value is not None:
                        self.set_pane_dimension(name, value)

            # Import proportions
            if "proportions" in config:
                for name, value in config["proportions"].items():
                    self.set_layout_proportion(name, value)

            # Import other settings
            if "split_orientation" in config:
                self.set_split_orientation(config["split_orientation"])

            # Import preview config
            if "preview_config" in config:
                preview_cfg = config["preview_config"]
                if "layout_type" in preview_cfg:
                    self.set_preview_layout_type(preview_cfg["layout_type"])
                if "ratio_presets" in preview_cfg:
                    for name, ratio in preview_cfg["ratio_presets"].items():
                        self.set_preview_ratio_preset(name, ratio)
                if "current_preset" in preview_cfg:
                    self.set_current_preview_preset(preview_cfg["current_preset"])
                if "custom_ratio" in preview_cfg:
                    self.set_custom_preview_ratio(preview_cfg["custom_ratio"])
                if "context_preservation" in preview_cfg:
                    self.set_preview_context_preservation(preview_cfg["context_preservation"])

            logger.info("Layout configuration imported successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to import layout config: {e}")
            return False

    # =========================================================================
    # Multi-window state accessors (v3.0)
    # =========================================================================

    def get_window_state(self, window_id: str) -> Optional[Dict[str, Any]]:
        """
        Get saved state for a specific window.

        Args:
            window_id: Window identifier (e.g., "main", "inspector", "settings")

        Returns:
            Window state dict or None if not saved
        """
        return self._state.get("windows", {}).get(window_id)

    def set_window_state(self, window_id: str, state: Dict[str, Any]):
        """
        Save state for a specific window.

        Args:
            window_id: Window identifier
            state: Window state dict with x, y, width, height, is_visible, etc.
        """
        if "windows" not in self._state:
            self._state["windows"] = {}
        self._state["windows"][window_id] = state
        logger.debug(f"Saved window state for: {window_id}")

    def get_all_window_states(self) -> Dict[str, Dict[str, Any]]:
        """Get all saved window states."""
        return self._state.get("windows", {}).copy()

    def clear_window_state(self, window_id: str):
        """Clear saved state for a specific window."""
        if "windows" in self._state and window_id in self._state["windows"]:
            del self._state["windows"][window_id]
            logger.debug(f"Cleared window state for: {window_id}")

    # =========================================================================
    # Preferences accessors (migrated from app_preferences.json) (v3.0)
    # =========================================================================

    def get_active_settings_file(self) -> Optional[str]:
        """Get the currently active settings file path."""
        return self._state.get("preferences", {}).get("active_settings_file")

    def set_active_settings_file(self, file_path: Optional[str]):
        """Set the active settings file path."""
        if "preferences" not in self._state:
            self._state["preferences"] = {}
        self._state["preferences"]["active_settings_file"] = file_path

    def get_recent_documents(self) -> List[str]:
        """Get list of recent documents."""
        return self._state.get("preferences", {}).get("recent_documents", [])

    def add_recent_document(self, document_path: str):
        """Add a document to recent documents list (max 10)."""
        if "preferences" not in self._state:
            self._state["preferences"] = {"recent_documents": []}
        recent = self._state["preferences"].get("recent_documents", [])

        # Remove if already in list
        if document_path in recent:
            recent.remove(document_path)

        # Add to front
        recent.insert(0, document_path)

        # Keep only last 10
        self._state["preferences"]["recent_documents"] = recent[:10]

    def get_open_documents(self) -> List[str]:
        """Get list of documents that should be restored on startup."""
        return self._state.get("preferences", {}).get("open_documents", [])

    def set_open_documents(self, document_paths: List[str]):
        """Save list of currently open documents for session restoration."""
        if "preferences" not in self._state:
            self._state["preferences"] = {}
        self._state["preferences"]["open_documents"] = document_paths

    def get_last_used_directory(self, key: str) -> Optional[str]:
        """Get last used directory for a specific purpose."""
        return self._state.get("preferences", {}).get("last_used_directories", {}).get(key)

    def set_last_used_directory(self, key: str, directory: str):
        """Set last used directory for a specific purpose."""
        if "preferences" not in self._state:
            self._state["preferences"] = {}
        if "last_used_directories" not in self._state["preferences"]:
            self._state["preferences"]["last_used_directories"] = {}
        self._state["preferences"]["last_used_directories"][key] = directory

    def get_preferred_plan(self) -> Optional[str]:
        """Get user's preferred default plan."""
        return self._state.get("preferences", {}).get("preferred_plan")

    def set_preferred_plan(self, plan_name: Optional[str]):
        """Set user's preferred default plan."""
        if "preferences" not in self._state:
            self._state["preferences"] = {}
        self._state["preferences"]["preferred_plan"] = plan_name

    def get_preferred_workflow(self) -> Optional[str]:
        """Get user's preferred default workflow."""
        return self._state.get("preferences", {}).get("preferred_workflow")

    def set_preferred_workflow(self, workflow_name: Optional[str]):
        """Set user's preferred default workflow."""
        if "preferences" not in self._state:
            self._state["preferences"] = {}
        self._state["preferences"]["preferred_workflow"] = workflow_name

    # =========================================================================
    # Preview viewer state accessors (v3.0)
    # =========================================================================

    def get_preview_viewer_state(self) -> Dict[str, Any]:
        """
        Get saved preview viewer state (zoom, scroll, rotation).

        Returns:
            Dict with scale, rotation, scroll_x, scroll_y
        """
        default = {
            "scale": 1.0,
            "rotation": 0,
            "scroll_x": 0,
            "scroll_y": 0
        }
        return self._state.get("preview_viewer_state", default)

    def set_preview_viewer_state(self, state: Dict[str, Any]):
        """
        Save preview viewer state.

        Args:
            state: Dict with scale, rotation, scroll_x, scroll_y
        """
        self._state["preview_viewer_state"] = {
            "scale": state.get("scale", 1.0),
            "rotation": state.get("rotation", 0),
            "scroll_x": state.get("scroll_x", 0),
            "scroll_y": state.get("scroll_y", 0)
        }
        logger.debug(f"Saved preview viewer state: scale={state.get('scale')}")

    def reset_preview_viewer_state(self):
        """Reset preview viewer state to defaults."""
        self._state["preview_viewer_state"] = {
            "scale": 1.0,
            "rotation": 0,
            "scroll_x": 0,
            "scroll_y": 0
        }

    # =========================================================================
    # Pane content state accessors (v3.0)
    # =========================================================================

    def get_pane_content(self, pane_name: str) -> Dict[str, Any]:
        """
        Get content state for a specific pane.

        Args:
            pane_name: Name of pane (library, collection, preview_image, preview_metadata, adjust)

        Returns:
            Pane content state dict
        """
        defaults = {
            "library": {"selected_collection_id": None, "scroll_position": 0},
            "collection": {"collection_id": None, "selected_item_id": None, "scroll_position": 0},
            "preview_image": {"item_id": None},
            "preview_metadata": {"item_id": None, "scroll_position": 0},
            "adjust": {"item_id": None, "active_tab": "crop"}
        }
        pane_content = self._state.get("pane_content", {})
        return pane_content.get(pane_name, defaults.get(pane_name, {}))

    def set_pane_content(self, pane_name: str, content: Dict[str, Any]):
        """
        Set content state for a specific pane.

        Args:
            pane_name: Name of pane
            content: Pane content state dict
        """
        if "pane_content" not in self._state:
            self._state["pane_content"] = {}
        self._state["pane_content"][pane_name] = content

    def update_pane_content(self, pane_name: str, **kwargs):
        """
        Update specific fields in pane content state.

        Args:
            pane_name: Name of pane
            **kwargs: Fields to update
        """
        current = self.get_pane_content(pane_name)
        current.update(kwargs)
        self.set_pane_content(pane_name, current)

    def get_library_pane_content(self) -> Dict[str, Any]:
        """Get library pane content state."""
        return self.get_pane_content("library")

    def set_library_selected_collection(self, collection_id: Optional[str]):
        """Set selected collection in library pane."""
        self.update_pane_content("library", selected_collection_id=collection_id)

    def get_collection_pane_content(self) -> Dict[str, Any]:
        """Get collection pane content state."""
        return self.get_pane_content("collection")

    def set_collection_pane_state(self, collection_id: Optional[str], item_id: Optional[str] = None):
        """Set collection pane state."""
        self.update_pane_content("collection", collection_id=collection_id, selected_item_id=item_id)

    def get_preview_pane_content(self) -> Dict[str, Any]:
        """Get preview image pane content state."""
        return self.get_pane_content("preview_image")

    def set_preview_item_id(self, item_id: Optional[str]):
        """Set item loaded in preview panes."""
        self.update_pane_content("preview_image", item_id=item_id)
        self.update_pane_content("preview_metadata", item_id=item_id)

    def get_adjust_pane_content(self) -> Dict[str, Any]:
        """Get adjust pane content state."""
        return self.get_pane_content("adjust")

    def set_adjust_pane_state(self, item_id: Optional[str], active_tab: str = "crop"):
        """Set adjust pane state."""
        self.update_pane_content("adjust", item_id=item_id, active_tab=active_tab)

    def set_pane_scroll_position(self, pane_name: str, position: int):
        """Set scroll position for a pane."""
        self.update_pane_content(pane_name, scroll_position=position)

    def get_pane_scroll_position(self, pane_name: str) -> int:
        """Get scroll position for a pane."""
        return self.get_pane_content(pane_name).get("scroll_position", 0)

"""
Display Profiles for Preview Metadata Pane

Defines which metadata fields are visible for different item types.
Inspired by Tinderbox's "Displayed Attributes" / prototype system.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class DisplayProfile:
    """
    Defines which metadata fields are visible for an item type.

    Attributes:
        profile_id: Unique identifier for this profile
        item_type: Item type this profile applies to ("file", "folder", "url", etc.)
        visible_fields: Ordered list of field keys to display
        is_default: Whether this is the built-in default profile
    """
    profile_id: str
    item_type: str
    visible_fields: List[str] = field(default_factory=list)
    is_default: bool = True

    def add_field(self, field_key: str, position: Optional[int] = None) -> bool:
        """
        Add a field to visible fields.

        Args:
            field_key: Field key to add
            position: Optional position to insert at (appends if None)

        Returns:
            True if added, False if already present
        """
        if field_key in self.visible_fields:
            return False

        if position is not None and 0 <= position <= len(self.visible_fields):
            self.visible_fields.insert(position, field_key)
        else:
            self.visible_fields.append(field_key)
        return True

    def remove_field(self, field_key: str) -> bool:
        """
        Remove a field from visible fields.

        Args:
            field_key: Field key to remove

        Returns:
            True if removed, False if not present
        """
        if field_key not in self.visible_fields:
            return False
        self.visible_fields.remove(field_key)
        return True

    def move_field(self, field_key: str, new_position: int) -> bool:
        """
        Move a field to a new position.

        Args:
            field_key: Field key to move
            new_position: New position (0-indexed)

        Returns:
            True if moved, False if field not present
        """
        if field_key not in self.visible_fields:
            return False

        self.visible_fields.remove(field_key)
        new_position = max(0, min(new_position, len(self.visible_fields)))
        self.visible_fields.insert(new_position, field_key)
        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "profile_id": self.profile_id,
            "item_type": self.item_type,
            "visible_fields": self.visible_fields.copy(),
            "is_default": self.is_default
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'DisplayProfile':
        """Create from dictionary."""
        return cls(
            profile_id=data.get("profile_id", "unknown"),
            item_type=data.get("item_type", "file"),
            visible_fields=data.get("visible_fields", []).copy(),
            is_default=data.get("is_default", False)
        )


# Default profiles per item type
# These define which fields are shown by default for each item type

DEFAULT_PROFILES: Dict[str, DisplayProfile] = {
    "file": DisplayProfile(
        profile_id="file_default",
        item_type="file",
        visible_fields=["title", "date", "author", "description", "language"],
        is_default=True
    ),
    "folder": DisplayProfile(
        profile_id="folder_default",
        item_type="folder",
        visible_fields=["title", "description", "document_type", "date", "subjects"],
        is_default=True
    ),
    "url": DisplayProfile(
        profile_id="url_default",
        item_type="url",
        visible_fields=["title", "description", "provider", "rights", "reference"],
        is_default=True
    ),
    "camera": DisplayProfile(
        profile_id="camera_default",
        item_type="camera",
        visible_fields=["title", "date", "location", "description"],
        is_default=True
    ),
    "audio": DisplayProfile(
        profile_id="audio_default",
        item_type="audio",
        visible_fields=["title", "date", "author", "language", "description"],
        is_default=True
    ),
}


def get_default_profile(item_type: str) -> DisplayProfile:
    """
    Get the default display profile for an item type.

    Args:
        item_type: Item type ("file", "folder", "url", "camera", "audio")

    Returns:
        DisplayProfile for the item type, or file default if unknown type
    """
    if item_type in DEFAULT_PROFILES:
        # Return a copy to avoid modifying the defaults
        profile = DEFAULT_PROFILES[item_type]
        return DisplayProfile(
            profile_id=profile.profile_id,
            item_type=profile.item_type,
            visible_fields=profile.visible_fields.copy(),
            is_default=True
        )
    # Fall back to file profile for unknown types
    profile = DEFAULT_PROFILES["file"]
    return DisplayProfile(
        profile_id="file_default",
        item_type=item_type,
        visible_fields=profile.visible_fields.copy(),
        is_default=True
    )


def create_custom_profile(item_type: str, visible_fields: List[str]) -> DisplayProfile:
    """
    Create a custom display profile.

    Args:
        item_type: Item type this profile applies to
        visible_fields: Ordered list of field keys to display

    Returns:
        New DisplayProfile with is_default=False
    """
    return DisplayProfile(
        profile_id=f"{item_type}_custom",
        item_type=item_type,
        visible_fields=visible_fields.copy(),
        is_default=False
    )

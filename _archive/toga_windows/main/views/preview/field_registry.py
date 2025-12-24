"""
Metadata Field Registry for Preview Metadata Pane

Maps metadata schema fields to UI display information.
Pulls field definitions from the backend metadata_schemas module.

Now supports dynamic field discovery - fields that were extracted by
processing tools but are not in the predefined schemas will be
discovered from the database and shown in the UI.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, TYPE_CHECKING

# Import backend schemas
from fichero.library.metadata_schemas import (
    SCHEMA_REGISTRY,
    CATALOGUE_SCHEMA,
    TRANSCRIPTION_SCHEMA,
    FILE_INFO_SCHEMA,
    EXTERNAL_IIIF_SCHEMA,
)

if TYPE_CHECKING:
    from fichero.library.storage import LibraryStorage

logger = logging.getLogger(__name__)


@dataclass
class FieldInfo:
    """
    Information about a displayable metadata field.

    Attributes:
        key: Field key used in storage (e.g., "title", "date")
        label: Display label shown to user (e.g., "Title", "Date")
        description: Tooltip/help text explaining the field
        schema_type: Source schema ("catalogue", "transcription", etc.)
        field_type: Data type ("str", "int", "float", "list", "date")
        editable: Whether field can be edited by user
    """
    key: str
    label: str
    description: str
    schema_type: str
    field_type: str = "str"
    editable: bool = True


def _label_from_key(key: str) -> str:
    """Convert field key to display label."""
    return key.replace("_", " ").title()


class MetadataFieldRegistry:
    """
    Registry of all available metadata fields.

    Provides methods to query available fields for display in the metadata pane.
    Fields are organized by source schema (catalogue, transcription, etc.).
    """

    # Build FIELDS dict from backend schemas
    FIELDS: Dict[str, FieldInfo] = {}

    @classmethod
    def _init_fields(cls):
        """Initialize fields from backend schemas."""
        if cls.FIELDS:
            return  # Already initialized

        # Catalogue fields (primary editable fields) - add first, highest priority
        for field_def in CATALOGUE_SCHEMA.fields:
            cls.FIELDS[field_def.name] = FieldInfo(
                key=field_def.name,
                label=_label_from_key(field_def.name),
                description=field_def.description,
                schema_type="catalogue",
                field_type=field_def.field_type,
                editable=True
            )

        # Transcription fields (mostly read-only info) - skip duplicates
        for field_def in TRANSCRIPTION_SCHEMA.fields:
            if field_def.name == "text":
                continue  # Skip text - shown separately
            if field_def.name in cls.FIELDS:
                continue  # Skip duplicates (e.g., language)
            cls.FIELDS[field_def.name] = FieldInfo(
                key=field_def.name,
                label=_label_from_key(field_def.name),
                description=field_def.description,
                schema_type="transcription",
                field_type=field_def.field_type,
                editable=False
            )

        # External IIIF fields - skip duplicates
        for field_def in EXTERNAL_IIIF_SCHEMA.fields:
            if field_def.name == "manifest_url":
                continue  # Skip internal field
            if field_def.name in cls.FIELDS:
                continue  # Skip duplicates (e.g., description)
            cls.FIELDS[field_def.name] = FieldInfo(
                key=field_def.name,
                label=_label_from_key(field_def.name),
                description=field_def.description,
                schema_type="external_iiif",
                field_type=field_def.field_type,
                editable=False
            )

        # File info fields - skip duplicates
        for field_def in FILE_INFO_SCHEMA.fields:
            if field_def.name in cls.FIELDS:
                continue  # Skip duplicates
            cls.FIELDS[field_def.name] = FieldInfo(
                key=field_def.name,
                label=_label_from_key(field_def.name),
                description=field_def.description,
                schema_type="file_info",
                field_type=field_def.field_type,
                editable=False
            )

    @classmethod
    def get_field_info(cls, field_key: str) -> Optional[FieldInfo]:
        """
        Get FieldInfo for a specific field key.

        Args:
            field_key: The field key to look up

        Returns:
            FieldInfo if found, None otherwise
        """
        cls._init_fields()
        return cls.FIELDS.get(field_key)

    @classmethod
    def get_all_fields(cls) -> List[FieldInfo]:
        """Get all registered fields."""
        cls._init_fields()
        return list(cls.FIELDS.values())

    @classmethod
    def get_fields_by_schema(cls, schema_type: str) -> List[FieldInfo]:
        """
        Get all fields for a specific schema type.

        Args:
            schema_type: Schema type ("catalogue", "transcription", etc.)

        Returns:
            List of FieldInfo for that schema
        """
        cls._init_fields()
        return [f for f in cls.FIELDS.values() if f.schema_type == schema_type]

    @classmethod
    def get_editable_fields(cls) -> List[FieldInfo]:
        """Get all editable fields."""
        cls._init_fields()
        return [f for f in cls.FIELDS.values() if f.editable]

    @classmethod
    def get_catalogue_fields(cls) -> List[FieldInfo]:
        """Get all catalogue schema fields (primary editable fields)."""
        return cls.get_fields_by_schema("catalogue")

    @classmethod
    def get_available_fields(cls, item_type: str = None) -> List[FieldInfo]:
        """
        Get fields available for display in the metadata pane.

        Returns all fields from the registry.

        Args:
            item_type: Optional item type for filtering (not used currently)

        Returns:
            List of available FieldInfo
        """
        cls._init_fields()
        return list(cls.FIELDS.values())

    @classmethod
    def get_readonly_fields(cls) -> List[FieldInfo]:
        """Get all read-only fields (info/status fields)."""
        cls._init_fields()
        return [f for f in cls.FIELDS.values() if not f.editable]

    @classmethod
    def field_exists(cls, field_key: str) -> bool:
        """Check if a field key exists in the registry."""
        cls._init_fields()
        return field_key in cls.FIELDS

    @classmethod
    def get_field_label(cls, field_key: str) -> str:
        """
        Get the display label for a field.

        Args:
            field_key: Field key

        Returns:
            Display label, or the key itself if not found
        """
        field_info = cls.get_field_info(field_key)
        return field_info.label if field_info else field_key.replace("_", " ").title()

    @classmethod
    def get_all_field_keys(cls) -> List[str]:
        """Get list of all field keys."""
        cls._init_fields()
        return list(cls.FIELDS.keys())

    # -------------------------------------------------------------------------
    # Dynamic Field Discovery
    # -------------------------------------------------------------------------

    @classmethod
    def create_dynamic_field_info(cls, key: str, schema_type: str = "discovered") -> FieldInfo:
        """
        Create a FieldInfo for a dynamically discovered field.

        Used when a field exists in the database but is not in predefined schemas.

        Args:
            key: The field key from the database
            schema_type: The schema type (defaults to "discovered")

        Returns:
            FieldInfo for the dynamic field
        """
        return FieldInfo(
            key=key,
            label=_label_from_key(key),
            description=f"Dynamic field: {key}",
            schema_type=schema_type,
            field_type="str",  # Default to string for dynamic fields
            editable=True  # Allow editing of dynamic fields
        )

    @classmethod
    def get_dynamic_fields_for_item(cls, storage: 'LibraryStorage', item_id: str) -> List[FieldInfo]:
        """
        Get fields that exist in the database for an item but are not predefined.

        This discovers dynamic fields that were added by processing tools.

        Args:
            storage: LibraryStorage instance
            item_id: The item ID to query

        Returns:
            List of FieldInfo for discovered fields
        """
        cls._init_fields()
        discovered_fields = []

        try:
            # Get all keys from the database for this item
            db_keys = storage.get_metadata_keys_for_item(item_id)

            # Find keys that aren't in our predefined fields
            for key in db_keys:
                if key not in cls.FIELDS:
                    # Create dynamic field info
                    field_info = cls.create_dynamic_field_info(key)
                    discovered_fields.append(field_info)
                    logger.debug(f"Discovered dynamic field: {key}")

        except Exception as e:
            logger.error(f"Failed to get dynamic fields for item {item_id}: {e}")

        return discovered_fields

    @classmethod
    def get_all_dynamic_fields(cls, storage: 'LibraryStorage', collection_id: str = None) -> List[FieldInfo]:
        """
        Get all dynamic fields across the library or a collection.

        Args:
            storage: LibraryStorage instance
            collection_id: Optional collection ID to filter by

        Returns:
            List of FieldInfo for all discovered fields
        """
        cls._init_fields()
        discovered_fields = []
        seen_keys = set()

        try:
            # Get all unique keys from the database
            all_keys = storage.get_all_metadata_keys(collection_id=collection_id)

            for key_info in all_keys:
                key = key_info["key"]
                schema_type = key_info["schema_type"]

                # Skip if already in predefined fields or already seen
                if key in cls.FIELDS or key in seen_keys:
                    continue

                seen_keys.add(key)
                field_info = cls.create_dynamic_field_info(key, schema_type)
                discovered_fields.append(field_info)

        except Exception as e:
            logger.error(f"Failed to get all dynamic fields: {e}")

        return discovered_fields

    @classmethod
    def get_available_fields_with_discovery(
        cls,
        storage: 'LibraryStorage' = None,
        item_id: str = None,
        item_type: str = None
    ) -> List[FieldInfo]:
        """
        Get all available fields including dynamically discovered ones.

        This extends get_available_fields to include fields found in the database.

        Args:
            storage: LibraryStorage instance for dynamic discovery
            item_id: Optional item ID to discover fields for
            item_type: Optional item type for filtering

        Returns:
            List of all available FieldInfo (predefined + discovered)
        """
        cls._init_fields()

        # Start with predefined fields
        all_fields = list(cls.FIELDS.values())

        # Add discovered fields if storage is provided
        if storage:
            if item_id:
                dynamic_fields = cls.get_dynamic_fields_for_item(storage, item_id)
            else:
                dynamic_fields = cls.get_all_dynamic_fields(storage)

            # Add dynamic fields that aren't duplicates
            existing_keys = {f.key for f in all_fields}
            for field in dynamic_fields:
                if field.key not in existing_keys:
                    all_fields.append(field)

        return all_fields

    @classmethod
    def register_dynamic_field(cls, key: str, schema_type: str = "discovered",
                               label: str = None, editable: bool = True) -> FieldInfo:
        """
        Register a new dynamic field in the registry.

        This allows tools to register fields they create.

        Args:
            key: Field key
            schema_type: Schema type
            label: Display label (defaults to derived from key)
            editable: Whether field is editable

        Returns:
            The registered FieldInfo
        """
        cls._init_fields()

        if key in cls.FIELDS:
            return cls.FIELDS[key]

        field_info = FieldInfo(
            key=key,
            label=label or _label_from_key(key),
            description=f"Dynamic field: {key}",
            schema_type=schema_type,
            field_type="str",
            editable=editable
        )
        cls.FIELDS[key] = field_info
        logger.info(f"Registered dynamic field: {key}")
        return field_info

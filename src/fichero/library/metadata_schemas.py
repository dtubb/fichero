"""
Metadata Schema Definitions for Fichero Library

Defines structured schemas for common metadata types with validation rules.
Schemas support required/optional fields, type checking, and custom fields for extensibility.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FieldDefinition:
    """Defines a single metadata field with validation rules"""
    name: str
    field_type: str  # "str", "int", "float", "bool", "date", "list", "dict"
    required: bool = False
    min_value: Optional[float] = None  # For numeric types
    max_value: Optional[float] = None  # For numeric types
    min_length: Optional[int] = None  # For strings
    max_length: Optional[int] = None  # For strings
    allowed_values: Optional[List[Any]] = None  # Enum values
    pattern: Optional[str] = None  # Regex pattern for strings
    description: str = ""


@dataclass
class MetadataSchema:
    """Defines a complete metadata schema with all fields and validation rules"""
    schema_type: str
    schema_version: int = 1
    description: str = ""
    fields: List[FieldDefinition] = field(default_factory=list)
    allow_custom_fields: bool = True

    def get_required_fields(self) -> List[str]:
        """Get list of required field names"""
        return [f.name for f in self.fields if f.required]

    def get_optional_fields(self) -> List[str]:
        """Get list of optional field names"""
        return [f.name for f in self.fields if not f.required]

    def get_field(self, name: str) -> Optional[FieldDefinition]:
        """Get field definition by name"""
        for field_def in self.fields:
            if field_def.name == name:
                return field_def
        return None


# Predefined Schemas

TRANSCRIPTION_SCHEMA = MetadataSchema(
    schema_type="transcription",
    schema_version=1,
    description="Text transcription from document images",
    fields=[
        FieldDefinition(
            name="text",
            field_type="str",
            required=True,
            description="Transcribed text content"
        ),
        FieldDefinition(
            name="language",
            field_type="str",
            required=False,
            description="Language code (e.g., 'en', 'es', 'fr')"
        ),
        FieldDefinition(
            name="confidence",
            field_type="float",
            required=False,
            min_value=0.0,
            max_value=1.0,
            description="OCR/transcription confidence score (0-1)"
        ),
        FieldDefinition(
            name="word_count",
            field_type="int",
            required=False,
            min_value=0,
            description="Number of words in transcription"
        ),
        FieldDefinition(
            name="model",
            field_type="str",
            required=False,
            description="Model/engine used for transcription"
        ),
    ],
    allow_custom_fields=True
)

TRANSLATION_SCHEMA = MetadataSchema(
    schema_type="translation",
    schema_version=1,
    description="Translated text from source to target language",
    fields=[
        FieldDefinition(
            name="text",
            field_type="str",
            required=True,
            description="Translated text content"
        ),
        FieldDefinition(
            name="source_language",
            field_type="str",
            required=True,
            description="Source language code (e.g., 'es', 'fr')"
        ),
        FieldDefinition(
            name="target_language",
            field_type="str",
            required=True,
            description="Target language code (e.g., 'en')"
        ),
        FieldDefinition(
            name="engine",
            field_type="str",
            required=False,
            description="Translation engine used (e.g., 'google', 'deepl')"
        ),
        FieldDefinition(
            name="confidence",
            field_type="float",
            required=False,
            min_value=0.0,
            max_value=1.0,
            description="Translation confidence score (0-1)"
        ),
    ],
    allow_custom_fields=True
)

CATALOGUE_SCHEMA = MetadataSchema(
    schema_type="catalogue",
    schema_version=1,
    description="Catalog metadata for documents",
    fields=[
        FieldDefinition(
            name="title",
            field_type="str",
            required=False,
            description="Document title"
        ),
        FieldDefinition(
            name="description",
            field_type="str",
            required=False,
            description="Document description or summary"
        ),
        FieldDefinition(
            name="date",
            field_type="str",
            required=False,
            description="Document date (free text or ISO format)"
        ),
        FieldDefinition(
            name="author",
            field_type="str",
            required=False,
            description="Document author or creator"
        ),
        FieldDefinition(
            name="location",
            field_type="str",
            required=False,
            description="Location associated with document"
        ),
        FieldDefinition(
            name="document_type",
            field_type="str",
            required=False,
            description="Type of document (letter, report, etc.)"
        ),
        FieldDefinition(
            name="language",
            field_type="str",
            required=False,
            description="Document language"
        ),
        FieldDefinition(
            name="subjects",
            field_type="list",
            required=False,
            description="Subject terms or keywords"
        ),
    ],
    allow_custom_fields=True
)

NAMED_ENTITIES_SCHEMA = MetadataSchema(
    schema_type="named_entities",
    schema_version=1,
    description="Named entity recognition results",
    fields=[
        FieldDefinition(
            name="entity_type",
            field_type="str",
            required=True,
            allowed_values=["PERSON", "ORGANIZATION", "LOCATION", "DATE", "TIME", "MONEY", "PERCENT", "OTHER"],
            description="Type of named entity"
        ),
        FieldDefinition(
            name="entity_text",
            field_type="str",
            required=True,
            description="The entity mention text"
        ),
        FieldDefinition(
            name="confidence",
            field_type="float",
            required=False,
            min_value=0.0,
            max_value=1.0,
            description="NER confidence score (0-1)"
        ),
        FieldDefinition(
            name="start_position",
            field_type="int",
            required=False,
            description="Character position in source text"
        ),
        FieldDefinition(
            name="end_position",
            field_type="int",
            required=False,
            description="End character position in source text"
        ),
    ],
    allow_custom_fields=True
)

EXTERNAL_IIIF_SCHEMA = MetadataSchema(
    schema_type="external_iiif",
    schema_version=1,
    description="Metadata from IIIF manifests (British Library, etc.)",
    fields=[
        FieldDefinition(
            name="manifest_url",
            field_type="str",
            required=True,
            description="URL to IIIF manifest"
        ),
        FieldDefinition(
            name="label",
            field_type="str",
            required=False,
            description="Manifest label/title"
        ),
        FieldDefinition(
            name="description",
            field_type="str",
            required=False,
            description="Manifest description"
        ),
        FieldDefinition(
            name="rights",
            field_type="str",
            required=False,
            description="Rights statement or license"
        ),
        FieldDefinition(
            name="provider",
            field_type="str",
            required=False,
            description="Institution providing the manifest"
        ),
        FieldDefinition(
            name="collection",
            field_type="str",
            required=False,
            description="Collection name"
        ),
        FieldDefinition(
            name="reference",
            field_type="str",
            required=False,
            description="Reference or shelfmark"
        ),
    ],
    allow_custom_fields=True
)

FILE_INFO_SCHEMA = MetadataSchema(
    schema_type="file_info",
    schema_version=1,
    description="File metadata and technical information",
    fields=[
        FieldDefinition(
            name="file_path",
            field_type="str",
            required=False,
            description="File path or name"
        ),
        FieldDefinition(
            name="file_size",
            field_type="int",
            required=False,
            min_value=0,
            description="File size in bytes"
        ),
        FieldDefinition(
            name="file_hash",
            field_type="str",
            required=False,
            description="SHA256 hash of file content"
        ),
        FieldDefinition(
            name="mime_type",
            field_type="str",
            required=False,
            description="MIME type (e.g., 'image/jpeg')"
        ),
        FieldDefinition(
            name="width",
            field_type="int",
            required=False,
            min_value=1,
            description="Image/video width in pixels"
        ),
        FieldDefinition(
            name="height",
            field_type="int",
            required=False,
            min_value=1,
            description="Image/video height in pixels"
        ),
        FieldDefinition(
            name="format",
            field_type="str",
            required=False,
            description="File format (e.g., 'JPEG', 'PNG')"
        ),
    ],
    allow_custom_fields=True
)

STEP_RESULT_SCHEMA = MetadataSchema(
    schema_type="step_result",
    schema_version=1,
    description="Processing step results and parameters",
    fields=[
        FieldDefinition(
            name="tool_name",
            field_type="str",
            required=True,
            description="Name of the processing tool"
        ),
        FieldDefinition(
            name="status",
            field_type="str",
            required=True,
            allowed_values=["success", "failed", "partial", "skipped"],
            description="Processing status"
        ),
        FieldDefinition(
            name="output_paths",
            field_type="list",
            required=False,
            description="List of output file paths"
        ),
        FieldDefinition(
            name="processing_time",
            field_type="float",
            required=False,
            min_value=0.0,
            description="Processing time in seconds"
        ),
        FieldDefinition(
            name="error_message",
            field_type="str",
            required=False,
            description="Error message if failed"
        ),
    ],
    allow_custom_fields=True
)

# Crop tool specific schema
CROP_PARAMS_SCHEMA = MetadataSchema(
    schema_type="crop_params",
    schema_version=1,
    description="Crop tool parameters and results",
    fields=[
        FieldDefinition(
            name="method",
            field_type="str",
            required=False,
            allowed_values=["yolo", "paddleocr", "manual"],
            description="Crop detection method"
        ),
        FieldDefinition(
            name="x",
            field_type="int",
            required=False,
            description="Crop box X coordinate"
        ),
        FieldDefinition(
            name="y",
            field_type="int",
            required=False,
            description="Crop box Y coordinate"
        ),
        FieldDefinition(
            name="width",
            field_type="int",
            required=False,
            min_value=1,
            description="Crop box width"
        ),
        FieldDefinition(
            name="height",
            field_type="int",
            required=False,
            min_value=1,
            description="Crop box height"
        ),
        FieldDefinition(
            name="confidence",
            field_type="float",
            required=False,
            min_value=0.0,
            max_value=1.0,
            description="Detection confidence"
        ),
        FieldDefinition(
            name="angle",
            field_type="float",
            required=False,
            description="Rotation angle in degrees"
        ),
    ],
    allow_custom_fields=True
)

# Registry of all schemas
SCHEMA_REGISTRY: Dict[str, MetadataSchema] = {
    "transcription": TRANSCRIPTION_SCHEMA,
    "translation": TRANSLATION_SCHEMA,
    "catalogue": CATALOGUE_SCHEMA,
    "named_entities": NAMED_ENTITIES_SCHEMA,
    "external_iiif": EXTERNAL_IIIF_SCHEMA,
    "file_info": FILE_INFO_SCHEMA,
    "step_result": STEP_RESULT_SCHEMA,
    "crop_params": CROP_PARAMS_SCHEMA,
}


def get_schema(schema_type: str) -> Optional[MetadataSchema]:
    """Get schema by type name"""
    return SCHEMA_REGISTRY.get(schema_type)


def get_all_schema_types() -> List[str]:
    """Get list of all registered schema types"""
    return list(SCHEMA_REGISTRY.keys())


def register_schema(schema: MetadataSchema) -> None:
    """Register a new custom schema"""
    SCHEMA_REGISTRY[schema.schema_type] = schema

"""
Metadata Validator for Fichero Library

Validates metadata against defined schemas, including type checking, required fields,
value ranges, and custom validation rules.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from fichero.library.metadata_schemas import get_schema, FieldDefinition


class ValidationError(Exception):
    """Raised when metadata validation fails"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Field '{field}': {message}")


class ValidationResult:
    """Result of metadata validation"""
    def __init__(self):
        self.is_valid = True
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []

    def add_error(self, field: str, message: str):
        """Add a validation error"""
        self.is_valid = False
        self.errors.append(ValidationError(field, message))

    def add_warning(self, message: str):
        """Add a validation warning"""
        self.warnings.append(message)

    def __str__(self) -> str:
        """String representation of validation result"""
        if self.is_valid:
            msg = "Validation passed"
            if self.warnings:
                msg += f" with {len(self.warnings)} warning(s)"
            return msg
        else:
            msg = f"Validation failed with {len(self.errors)} error(s)"
            for error in self.errors:
                msg += f"\n  - {error}"
            if self.warnings:
                msg += f"\nWarnings: {', '.join(self.warnings)}"
            return msg


class MetadataValidator:
    """Validates metadata against schemas"""

    def validate(self, schema_type: str, metadata: Dict[str, Any],
                 allow_unknown_fields: bool = True) -> ValidationResult:
        """
        Validate metadata against a schema

        Args:
            schema_type: Type of schema to validate against
            metadata: Metadata dictionary to validate
            allow_unknown_fields: Whether to allow fields not in schema

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult()

        # Get schema
        schema = get_schema(schema_type)
        if not schema:
            result.add_error("schema", f"Unknown schema type: {schema_type}")
            return result

        # Check required fields
        for field_name in schema.get_required_fields():
            if field_name not in metadata:
                result.add_error(field_name, "Required field is missing")

        # Validate each field in metadata
        for field_name, value in metadata.items():
            field_def = schema.get_field(field_name)

            if not field_def:
                if not schema.allow_custom_fields and not allow_unknown_fields:
                    result.add_error(field_name, "Unknown field (not in schema)")
                elif not schema.allow_custom_fields:
                    result.add_warning(f"Custom field '{field_name}' (schema doesn't explicitly allow custom fields)")
                continue

            # Validate field value
            field_result = self._validate_field(field_def, value)
            if not field_result.is_valid:
                for error in field_result.errors:
                    result.add_error(error.field, error.message)
            for warning in field_result.warnings:
                result.add_warning(warning)

        return result

    def _validate_field(self, field_def: FieldDefinition, value: Any) -> ValidationResult:
        """Validate a single field value"""
        result = ValidationResult()

        # Allow None for optional fields
        if value is None:
            if field_def.required:
                result.add_error(field_def.name, "Required field cannot be None")
            return result

        # Type checking
        expected_type = self._get_python_type(field_def.field_type)
        if not isinstance(value, expected_type):
            result.add_error(
                field_def.name,
                f"Expected type {field_def.field_type}, got {type(value).__name__}"
            )
            return result  # Don't continue validation if type is wrong

        # Type-specific validation
        if field_def.field_type == "str":
            self._validate_string(field_def, value, result)
        elif field_def.field_type in ["int", "float"]:
            self._validate_numeric(field_def, value, result)
        elif field_def.field_type == "list":
            self._validate_list(field_def, value, result)
        elif field_def.field_type == "date":
            self._validate_date(field_def, value, result)

        # Allowed values (enum)
        if field_def.allowed_values and value not in field_def.allowed_values:
            result.add_error(
                field_def.name,
                f"Value '{value}' not in allowed values: {field_def.allowed_values}"
            )

        return result

    def _get_python_type(self, field_type: str) -> type:
        """Convert field type string to Python type"""
        type_mapping = {
            "str": str,
            "int": int,
            "float": (int, float),  # Allow int for float fields
            "bool": bool,
            "list": list,
            "dict": dict,
            "date": (str, datetime),  # Allow ISO string or datetime
        }
        return type_mapping.get(field_type, object)

    def _validate_string(self, field_def: FieldDefinition, value: str, result: ValidationResult):
        """Validate string field"""
        # Length checks
        if field_def.min_length is not None and len(value) < field_def.min_length:
            result.add_error(
                field_def.name,
                f"String length {len(value)} is less than minimum {field_def.min_length}"
            )

        if field_def.max_length is not None and len(value) > field_def.max_length:
            result.add_error(
                field_def.name,
                f"String length {len(value)} exceeds maximum {field_def.max_length}"
            )

        # Pattern check
        if field_def.pattern:
            if not re.match(field_def.pattern, value):
                result.add_error(
                    field_def.name,
                    f"String does not match required pattern: {field_def.pattern}"
                )

    def _validate_numeric(self, field_def: FieldDefinition, value: float, result: ValidationResult):
        """Validate numeric field (int or float)"""
        # Range checks
        if field_def.min_value is not None and value < field_def.min_value:
            result.add_error(
                field_def.name,
                f"Value {value} is less than minimum {field_def.min_value}"
            )

        if field_def.max_value is not None and value > field_def.max_value:
            result.add_error(
                field_def.name,
                f"Value {value} exceeds maximum {field_def.max_value}"
            )

    def _validate_list(self, field_def: FieldDefinition, value: List, result: ValidationResult):
        """Validate list field"""
        # Could add item type checking here if needed
        pass

    def _validate_date(self, field_def: FieldDefinition, value: Any, result: ValidationResult):
        """Validate date field"""
        if isinstance(value, str):
            # Try to parse ISO format date
            try:
                datetime.fromisoformat(value)
            except ValueError:
                result.add_warning(
                    f"Date string '{value}' is not in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                )


def validate_metadata(schema_type: str, metadata: Dict[str, Any],
                     allow_unknown_fields: bool = True) -> ValidationResult:
    """
    Convenience function to validate metadata

    Args:
        schema_type: Type of schema to validate against
        metadata: Metadata dictionary to validate
        allow_unknown_fields: Whether to allow fields not in schema

    Returns:
        ValidationResult with errors and warnings

    Example:
        >>> result = validate_metadata("transcription", {
        ...     "text": "Document text here",
        ...     "language": "en",
        ...     "confidence": 0.95
        ... })
        >>> if result.is_valid:
        ...     print("Metadata is valid!")
    """
    validator = MetadataValidator()
    return validator.validate(schema_type, metadata, allow_unknown_fields)


def validate_and_raise(schema_type: str, metadata: Dict[str, Any],
                      allow_unknown_fields: bool = True) -> None:
    """
    Validate metadata and raise exception if invalid

    Args:
        schema_type: Type of schema to validate against
        metadata: Metadata dictionary to validate
        allow_unknown_fields: Whether to allow fields not in schema

    Raises:
        ValidationError: If validation fails
    """
    result = validate_metadata(schema_type, metadata, allow_unknown_fields)
    if not result.is_valid:
        raise result.errors[0]  # Raise first error

from fichero.errors import ErrorCategory, ErrorSeverity, FicheroError, handle_error


def test_handle_error_preserves_message_context_and_cause() -> None:
    error = handle_error(
        ValueError("bad input"),
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.WARNING,
        context={"field": "title"},
    )

    assert isinstance(error, FicheroError)
    assert error.to_dict() == {
        "error": "bad input",
        "category": "validation",
        "severity": "warning",
        "type": "FicheroError",
        "context": {"field": "title"},
    }
    assert isinstance(error.original_exception, ValueError)

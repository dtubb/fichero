"""Coverage for the centralized error module ``fichero.errors`` (previously
untested). Pure logic: the typed error taxonomy, ``handle_error`` conversion,
and the ``log_and_recover`` / ``retry_on_failure`` decorators (retries use
``delay_seconds=0`` so no real sleeping / no network).
"""

from __future__ import annotations

import pytest

from fichero.errors import (
    APIError,
    ConfigurationError,
    DatabaseError,
    ErrorCategory,
    ErrorSeverity,
    FicheroError,
    FileSystemError,
    ValidationError,
    handle_error,
    log_and_recover,
    retry_on_failure,
)


# ===========================================================================
# FicheroError base + subclasses
# ===========================================================================


def test_base_error_defaults_and_message():
    err = FicheroError("something broke")
    assert err.category is ErrorCategory.UNKNOWN
    assert err.severity is ErrorSeverity.ERROR
    assert err.context == {}
    # The rendered exception message prefixes the category.
    assert "[UNKNOWN] something broke" in str(err)


def test_base_error_wraps_original_in_message():
    original = ValueError("root cause")
    err = FicheroError("wrapper", original_exception=original)
    assert "caused by: ValueError: root cause" in str(err)
    assert err.original_exception is original


def test_to_dict_shape():
    err = FicheroError("boom", category=ErrorCategory.NETWORK, context={"host": "x"})
    assert err.to_dict() == {
        "error": "boom",
        "category": "network",
        "severity": "error",
        "type": "FicheroError",
        "context": {"host": "x"},
    }


@pytest.mark.parametrize(
    "cls,category,severity",
    [
        (DatabaseError, ErrorCategory.DATABASE, ErrorSeverity.ERROR),
        (FileSystemError, ErrorCategory.FILE_SYSTEM, ErrorSeverity.ERROR),
        (ConfigurationError, ErrorCategory.CONFIGURATION, ErrorSeverity.CRITICAL),
    ],
)
def test_subclass_category_and_severity(cls, category, severity):
    err = cls("msg")
    assert err.category is category
    assert err.severity is severity


def test_validation_error_puts_field_in_context():
    err = ValidationError("bad value", field="email")
    assert err.category is ErrorCategory.VALIDATION
    assert err.severity is ErrorSeverity.WARNING
    assert err.context["field"] == "email"


def test_validation_error_without_field_has_empty_context():
    assert ValidationError("bad").context == {}


def test_api_error_status_code_and_http_exception():
    err = APIError("not found", status_code=404)
    assert err.category is ErrorCategory.API
    exc = err.to_http_exception()
    assert exc.status_code == 404
    assert exc.detail == "not found"


def test_api_error_defaults_to_500():
    assert APIError("boom").status_code == 500


# ===========================================================================
# handle_error
# ===========================================================================


def test_handle_error_passes_through_fichero_error():
    original = DatabaseError("db down")
    assert handle_error(original) is original


def test_handle_error_wraps_plain_exception():
    err = handle_error(ValueError("nope"), category=ErrorCategory.BUSINESS_LOGIC)
    assert isinstance(err, FicheroError)
    assert err.message == "nope"
    assert err.category is ErrorCategory.BUSINESS_LOGIC
    assert isinstance(err.original_exception, ValueError)


def test_handle_error_uses_default_message_for_empty():
    err = handle_error(Exception(""), default_message="fallback msg")
    assert err.message == "fallback msg"


def test_handle_error_stdlib_exception_maps_to_generic_unknown():
    # Regression / documentation: a raw stdlib exception (e.g. OSError) becomes a
    # GENERIC FicheroError with the passed/default category — the internal
    # error_classes mapping loop is currently inert (it only keys FicheroError
    # subclasses, which return earlier), so OSError does NOT become FileSystemError.
    err = handle_error(OSError("disk"))
    assert type(err) is FicheroError
    assert err.category is ErrorCategory.UNKNOWN


# ===========================================================================
# log_and_recover
# ===========================================================================


def test_recover_returns_value_on_success():
    @log_and_recover("op")
    def ok(a, b):
        return a + b

    assert ok(2, 3) == 5


def test_recover_returns_default_on_failure_without_recovery():
    @log_and_recover("op", default_return="DEFAULT")
    def boom():
        raise RuntimeError("x")

    assert boom() == "DEFAULT"


def test_recover_uses_recovery_action():
    @log_and_recover("op", recovery_action=lambda: "RECOVERED")
    def boom():
        raise RuntimeError("x")

    assert boom() == "RECOVERED"


def test_recover_falls_to_default_when_recovery_also_fails():
    def failing_recovery(*a, **k):
        raise RuntimeError("recovery broke")

    @log_and_recover("op", recovery_action=failing_recovery, default_return="DEF")
    def boom():
        raise RuntimeError("x")

    assert boom() == "DEF"


def test_recovery_action_receives_original_args():
    seen = {}

    def recovery(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return "r"

    @log_and_recover("op", recovery_action=recovery)
    def boom(a, b=0):
        raise RuntimeError("x")

    boom(1, b=2)
    assert seen == {"args": (1,), "kwargs": {"b": 2}}


# ===========================================================================
# retry_on_failure
# ===========================================================================


def test_retry_returns_immediately_on_success():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, delay_seconds=0)
    def ok():
        calls["n"] += 1
        return "done"

    assert ok() == "done"
    assert calls["n"] == 1


def test_retry_eventually_succeeds():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, delay_seconds=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("retry me")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_exhausted_raises_fichero_error():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=2, delay_seconds=0)
    def always():
        calls["n"] += 1
        raise ValueError("always")

    with pytest.raises(FicheroError) as exc:
        always()
    assert calls["n"] == 2
    assert exc.value.severity is ErrorSeverity.CRITICAL


def test_retry_non_retryable_raises_raw_immediately():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, delay_seconds=0, retryable_errors=(KeyError,))
    def boom():
        calls["n"] += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        boom()
    assert calls["n"] == 1  # not retried


def test_retry_respects_retryable_error_filter():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, delay_seconds=0, retryable_errors=(KeyError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise KeyError("retry")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2

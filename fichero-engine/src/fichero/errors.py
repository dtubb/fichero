"""
Fichero Error Handling Module

Centralized error handling for the Fichero backend application.
Provides standardized error types, logging, and recovery mechanisms.
"""

import logging
import time
from enum import Enum
from typing import Any, Optional
from fastapi import HTTPException, status

# Configure logging
logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Standard error categories for consistent error classification."""

    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    API = "api"
    VALIDATION = "validation"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Standard error severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FicheroError(Exception):
    """Base exception class for all Fichero errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self.original_exception = original_exception
        self.context = context or {}

        # Build full error message
        full_message = f"[{category.value.upper()}] {message}"
        if original_exception:
            full_message += f" (caused by: {type(original_exception).__name__}: {original_exception})"

        super().__init__(full_message)

        # Log the error based on severity
        self._log_error()

    def _log_error(self):
        """Log the error based on its severity."""
        log_method = getattr(logger, self.severity.value)
        log_method(
            "%s: %s (Category: %s, Severity: %s)",
            self.__class__.__name__,
            self.message,
            self.category.value,
            self.severity.value,
        )

        if self.original_exception:
            logger.debug(
                "Original exception: %s", self.original_exception, exc_info=True
            )

        if self.context:
            logger.debug("Error context: %s", self.context)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "type": self.__class__.__name__,
            "context": self.context,
        }


class DatabaseError(FicheroError):
    """Database-related errors."""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            original_exception=original_exception,
            context=context,
        )


class FileSystemError(FicheroError):
    """File system-related errors."""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            category=ErrorCategory.FILE_SYSTEM,
            severity=ErrorSeverity.ERROR,
            original_exception=original_exception,
            context=context,
        )


class APIError(FicheroError):
    """API-related errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            category=ErrorCategory.API,
            severity=ErrorSeverity.ERROR,
            original_exception=original_exception,
            context=context,
        )
        self.status_code = status_code

    def to_http_exception(self) -> HTTPException:
        """Convert to FastAPI HTTPException."""
        return HTTPException(status_code=self.status_code, detail=self.message)


class ValidationError(FicheroError):
    """Validation-related errors."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        context = context or {}
        if field:
            context["field"] = field

        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            original_exception=original_exception,
            context=context,
        )


class ConfigurationError(FicheroError):
    """Configuration-related errors."""

    def __init__(
        self,
        message: str,
        original_exception: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.CRITICAL,
            original_exception=original_exception,
            context=context,
        )


def handle_error(
    exception: Exception,
    default_message: str = "An unexpected error occurred",
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    context: Optional[dict[str, Any]] = None,
) -> FicheroError:
    """
    Standard error handler that converts any exception to a FicheroError.

    Args:
        exception: The original exception
        default_message: Default message if exception has no meaningful message
        category: Error category
        severity: Error severity
        context: Additional context for debugging

    Returns:
        FicheroError instance
    """
    message = str(exception) if str(exception) else default_message

    # Create appropriate error type based on exception type
    error_classes = {
        DatabaseError: DatabaseError,
        FileSystemError: FileSystemError,
        APIError: APIError,
        ValidationError: ValidationError,
        ConfigurationError: ConfigurationError,
    }

    # If it's already a FicheroError, just return it
    if isinstance(exception, FicheroError):
        return exception

    # Try to determine appropriate error class based on type
    for base_class, error_class in error_classes.items():
        if isinstance(exception, base_class):
            return error_class(message, original_exception=exception, context=context)

    # Default to generic FicheroError
    return FicheroError(
        message,
        category=category,
        severity=severity,
        original_exception=exception,
        context=context,
    )


def log_and_recover(
    operation_name: str,
    recovery_action: Optional[callable] = None,
    default_return: Any = None,
):
    """
    Decorator for functions that should log errors and attempt recovery.

    Args:
        operation_name: Name of the operation for logging
        recovery_action: Function to call for recovery (should return recovery value)
        default_return: Default value to return if no recovery action

    Returns:
        Decorator function
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error = handle_error(
                    e,
                    default_message=f"{operation_name} failed",
                    context={"operation": operation_name},
                )

                logger.warning(
                    "Operation '%s' failed: %s. Attempting recovery...",
                    operation_name,
                    error.message,
                )

                # Attempt recovery if recovery action is provided
                if recovery_action:
                    try:
                        recovery_result = recovery_action(*args, **kwargs)
                        logger.info(
                            "Operation '%s' recovered successfully", operation_name
                        )
                        return recovery_result
                    except Exception as recovery_error:
                        logger.error(
                            "Recovery failed for '%s': %s",
                            operation_name,
                            recovery_error,
                        )

                # Return default value if no recovery or recovery failed
                logger.warning(
                    "Operation '%s' failed with no recovery. Returning default value",
                    operation_name,
                )
                return default_return

        return wrapper

    return decorator


def retry_on_failure(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    retryable_errors: tuple = (Exception,),
    backoff_factor: float = 2.0,
):
    """
    Decorator for functions that should retry on failure.

    Args:
        max_attempts: Maximum number of retry attempts
        delay_seconds: Initial delay between retries in seconds
        retryable_errors: Tuple of exception types that should trigger retry
        backoff_factor: Multiplier for exponential backoff

    Returns:
        Decorator function
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_errors as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = delay_seconds * (backoff_factor ** (attempt - 1))
                        logger.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.2f seconds...",
                            attempt,
                            max_attempts,
                            func.__name__,
                            str(e),
                            delay,
                        )

                        # Sleep for the delay period
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            max_attempts,
                            func.__name__,
                            str(e),
                        )
                except Exception:
                    # Re-raise non-retryable exceptions immediately
                    raise

            # If we exhausted all attempts, raise the last exception
            if last_exception:
                raise handle_error(
                    last_exception,
                    default_message=f"{func.__name__} failed after {max_attempts} attempts",
                    severity=ErrorSeverity.CRITICAL,
                )

        return wrapper

    return decorator

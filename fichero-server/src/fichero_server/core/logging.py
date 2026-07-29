"""
Fichero Logging Module

Centralized logging configuration and utilities for the Fichero application.
Provides standardized logging setup, log rotation, and logging utilities.
"""

import logging
import logging.handlers
import os
import time
import sys
from typing import Any, Optional
from datetime import datetime
import json


class LogLevel:
    """Standard log levels for Fichero application."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogFormat:
    """Standard log formats."""

    # Standard format: [timestamp] [level] [module] message
    STANDARD = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # JSON format for structured logging
    JSON = None  # Will be set dynamically

    # Simple format for console
    SIMPLE = "%(levelname)s - %(message)s"

    # Detailed format with process and thread info
    DETAILED = "%(asctime)s - %(process)d - %(threadName)s - %(name)s - %(levelname)s - %(message)s"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.threadName,
        }

        # Add exception info if available
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data, ensure_ascii=False)

    def formatTime(
        self, record: logging.LogRecord, datefmt: Optional[str] = None
    ) -> str:
        """Format timestamp in ISO format."""
        return datetime.fromtimestamp(record.created).isoformat()


class FicheroLogger:
    """Centralized logger configuration for Fichero application."""

    def __init__(
        self,
        name: str = "fichero",
        log_level: int = LogLevel.INFO,
        log_file: Optional[str] = None,
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 5,
        use_json: bool = False,
    ):
        """
        Initialize Fichero logger.

        Args:
            name: Logger name
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Path to log file (None for console-only)
            max_bytes: Maximum log file size before rotation
            backup_count: Number of backup log files to keep
            use_json: Use JSON format for structured logging
        """
        self.name = name
        self.log_level = log_level
        self.log_file = log_file
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.use_json = use_json

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

        # Clear existing handlers to avoid duplicate logs
        self.logger.handlers.clear()

        # Set format based on configuration
        if use_json:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(LogFormat.STANDARD)

        # Add console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Add file handler if log_file is specified
        if log_file:
            # Create log directory if it doesn't exist
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            self.logger.info("Logging initialized to file: %s", log_file)

        self.logger.debug("FicheroLogger initialized for: %s", name)

    def get_logger(self) -> logging.Logger:
        """Get the configured logger instance."""
        return self.logger

    def log_with_context(
        self,
        level: int,
        message: str,
        context: Optional[dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Log message with additional context.

        Args:
            level: Log level
            message: Log message
            context: Additional context data
            kwargs: Additional keyword arguments
        """
        if context:
            # Add context to extra fields for JSON logging
            if self.use_json:
                extra = {"extra": context}
                self.logger.log(level, message, extra=extra)
            else:
                # For standard logging, add context to message
                context_str = ", ".join(f"{k}={v}" for k, v in context.items())
                full_message = f"{message} [context: {context_str}]"
                self.logger.log(level, full_message)
        else:
            self.logger.log(level, message)

    def debug(
        self, message: str, *args, context: Optional[dict[str, Any]] = None, **kwargs
    ):
        """Log debug message with optional context."""
        if context:
            self.log_with_context(LogLevel.DEBUG, message, context)
        else:
            self.logger.debug(message, *args, **kwargs)

    def info(
        self, message: str, *args, context: Optional[dict[str, Any]] = None, **kwargs
    ):
        """Log info message with optional context."""
        if context:
            self.log_with_context(LogLevel.INFO, message, context)
        else:
            self.logger.info(message, *args, **kwargs)

    def warning(
        self, message: str, *args, context: Optional[dict[str, Any]] = None, **kwargs
    ):
        """Log warning message with optional context."""
        if context:
            self.log_with_context(LogLevel.WARNING, message, context)
        else:
            self.logger.warning(message, *args, **kwargs)

    def error(
        self, message: str, *args, context: Optional[dict[str, Any]] = None, **kwargs
    ):
        """Log error message with optional context."""
        if context:
            self.log_with_context(LogLevel.ERROR, message, context)
        else:
            self.logger.error(message, *args, **kwargs)

    def critical(
        self, message: str, *args, context: Optional[dict[str, Any]] = None, **kwargs
    ):
        """Log critical message with optional context."""
        if context:
            self.log_with_context(LogLevel.CRITICAL, message, context)
        else:
            self.logger.critical(message, *args, **kwargs)

    def log_operation(
        self,
        operation: str,
        status: str,
        duration: Optional[float] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Log operation with status and timing information.

        Args:
            operation: Operation name
            status: Operation status (success, failure, etc.)
            duration: Operation duration in seconds
            context: Additional context data
        """
        log_context = context or {}
        log_context.update({"operation": operation, "status": status})

        if duration is not None:
            log_context["duration_seconds"] = round(duration, 4)

        message = f"Operation {operation} {status}"
        if duration is not None:
            message += f" in {duration:.4f}s"

        level = LogLevel.INFO if status == "success" else LogLevel.ERROR
        self.log_with_context(level, message, log_context)

    def log_api_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        context: Optional[dict[str, Any]] = None,
    ):
        """
        Log API request with timing and status information.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            status_code: HTTP status code
            duration: Request duration in seconds
            context: Additional context data
        """
        log_context = context or {}
        log_context.update(
            {
                "http_method": method,
                "api_path": path,
                "status_code": status_code,
                "duration_seconds": round(duration, 4),
            }
        )

        status_text = "success" if 200 <= status_code < 300 else "failure"
        level = LogLevel.INFO if status_text == "success" else LogLevel.WARNING

        message = f"API {method} {path} -> {status_code} in {duration:.4f}s"
        self.log_with_context(level, message, log_context)


def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    max_size_mb: int = 10,
    backup_count: int = 5,
    use_json: bool = False,
) -> FicheroLogger:
    """
    Configure global logging for Fichero application.

    Args:
        log_level: Log level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
        max_size_mb: Maximum log file size in MB
        backup_count: Number of backup files to keep
        use_json: Use JSON format for structured logging

    Returns:
        Configured FicheroLogger instance
    """
    # Convert log level string to logging level
    level_map = {
        "DEBUG": LogLevel.DEBUG,
        "INFO": LogLevel.INFO,
        "WARNING": LogLevel.WARNING,
        "ERROR": LogLevel.ERROR,
        "CRITICAL": LogLevel.CRITICAL,
    }

    log_level_upper = log_level.upper()
    if log_level_upper not in level_map:
        raise ValueError(
            f"Invalid log level: {log_level}. Must be one of: {list(level_map.keys())}"
        )

    # Configure logger
    logger = FicheroLogger(
        name="fichero",
        log_level=level_map[log_level_upper],
        log_file=log_file,
        max_bytes=max_size_mb * 1024 * 1024,  # Convert MB to bytes
        backup_count=backup_count,
        use_json=use_json,
    )

    return logger


def get_logger(name: str = "fichero") -> logging.Logger:
    """
    Get a logger with the specified name.

    Args:
        name: Logger name

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_operation(func):
    """
    Decorator to log operation execution with timing.

    Args:
        func: Function to decorate

    Returns:
        Decorated function
    """

    def wrapper(*args, **kwargs):

        logger = get_logger(func.__module__ or "fichero")
        operation_name = (
            f"{func.__module__}.{func.__name__}" if func.__module__ else func.__name__
        )

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            if hasattr(logger, "log_operation"):
                logger.log_operation(operation_name, "success", duration)
            else:
                logger.info(
                    "Operation %s completed successfully in %.4fs",
                    operation_name,
                    duration,
                )

            return result

        except Exception as e:
            duration = time.time() - start_time

            if hasattr(logger, "log_operation"):
                logger.log_operation(
                    operation_name, "failure", duration, {"error": str(e)}
                )
            else:
                logger.error(
                    "Operation %s failed after %.4fs: %s",
                    operation_name,
                    duration,
                    str(e),
                )

            raise

    return wrapper


def log_api_endpoint(func):
    """
    Decorator to log API endpoint execution with timing.

    Args:
        func: API endpoint function to decorate

    Returns:
        Decorated function
    """

    def wrapper(*args, **kwargs):
        from fastapi import Request

        # Extract request object if available
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

        logger = get_logger(func.__module__ or "fichero_server.api")

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            if request:
                method = request.method
                path = request.url.path
                status_code = 200  # Default success code

                if hasattr(logger, "log_api_request"):
                    logger.log_api_request(method, path, status_code, duration)
                else:
                    logger.info(
                        "API %s %s -> %d in %.4fs", method, path, status_code, duration
                    )

            return result

        except Exception as e:
            duration = time.time() - start_time

            if request:
                method = request.method
                path = request.url.path
                status_code = (
                    getattr(e, "status_code", 500) if hasattr(e, "status_code") else 500
                )

                if hasattr(logger, "log_api_request"):
                    logger.log_api_request(
                        method, path, status_code, duration, {"error": str(e)}
                    )
                else:
                    logger.error(
                        "API %s %s -> %d failed in %.4fs: %s",
                        method,
                        path,
                        status_code,
                        duration,
                        str(e),
                    )

            raise

    return wrapper


# Initialize default logger
_default_logger = None


def init_default_logger(
    log_level: str = "INFO", log_file: Optional[str] = None
) -> FicheroLogger:
    """
    Initialize default logger for the application.

    Args:
        log_level: Log level as string
        log_file: Path to log file

    Returns:
        Configured FicheroLogger instance
    """
    global _default_logger

    if _default_logger is None:
        _default_logger = configure_logging(log_level=log_level, log_file=log_file)

    return _default_logger


def get_default_logger() -> logging.Logger:
    """
    Get the default logger instance.

    Returns:
        Default logger instance
    """
    if _default_logger is None:
        init_default_logger()

    return _default_logger.get_logger()

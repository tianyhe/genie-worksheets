"""Logging configuration for the Genie system.

This module configures logging for the entire system using loguru.
It provides structured logging with contextual information and proper formatting.
"""

import sys
from typing import Any, Dict

from loguru import logger


def setup_logging(debug: bool = False) -> None:
    """Configure the logging system.

    This sets up loguru with proper formatting and log levels.

    Args:
        debug: Whether to enable debug logging
    """
    # Remove default handler
    logger.remove()

    # Define log format with timestamp, level, module, and message
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Add console handler with appropriate level
    level = "DEBUG" if debug else "INFO"
    logger.add(sys.stderr, format=log_format, level=level)

    # Add file handler for all logs
    logger.add(
        "logs/genie.log",
        format=log_format,
        level="DEBUG",
        rotation="1 day",
        retention="1 week",
        compression="zip",
    )

    # Add file handler for errors only
    logger.add(
        "logs/errors.log",
        format=log_format,
        level="ERROR",
        rotation="1 day",
        retention="1 month",
        compression="zip",
        filter=lambda record: record["level"].name == "ERROR",
    )


def log_context(context: Dict[str, Any], level: str = "DEBUG") -> None:
    """Log the current context state.

    Args:
        context: The context dictionary to log
        level: The log level to use
    """
    logger.log(level, "Current context state:")
    for key, value in context.items():
        if key == "__builtins__":
            continue
        logger.log(level, f"  {key}: {type(value)}")


def log_worksheet_state(worksheet: Any, level: str = "DEBUG") -> None:
    """Log the current state of a worksheet.

    Args:
        worksheet: The worksheet to log
        level: The log level to use
    """
    from worksheets.utils.field import get_genie_fields_from_ws

    logger.log(level, f"Worksheet state for {worksheet.__class__.__name__}:")
    for field in get_genie_fields_from_ws(worksheet):
        logger.log(
            level,
            f"  {field.name}: value={field.value}, "
            f"confirmed={field.confirmed}, "
            f"action_performed={field.action_performed}",
        )


def log_action_result(action: str, result: Any, level: str = "DEBUG") -> None:
    """Log the result of an action.

    Args:
        action: The action being performed
        result: The result of the action
        level: The log level to use
    """
    logger.log(level, f"Action result for {action}:")
    logger.log(level, f"  Result: {result}")
    logger.log(level, f"  Type: {type(result)}")


def log_validation_result(
    field_name: str,
    value: Any,
    is_valid: bool,
    reason: str = None,
    level: str = "DEBUG",
) -> None:
    """Log the result of a validation check.

    Args:
        field_name: The name of the field being validated
        value: The value being validated
        is_valid: Whether the validation passed
        reason: The reason for validation failure
        level: The log level to use
    """
    logger.log(level, f"Validation result for field {field_name}:")
    logger.log(level, f"  Value: {value}")
    logger.log(level, f"  Valid: {is_valid}")
    if reason:
        logger.log(level, f"  Reason: {reason}")


def log_code_execution(
    code: str, context_vars: Dict[str, Any], level: str = "DEBUG"
) -> None:
    """Log details about code being executed.

    Args:
        code: The code being executed
        context_vars: Variables available in the execution context
        level: The log level to use
    """
    logger.log(level, "Executing code:")
    logger.log(level, f"  Code: {code}")
    logger.log(level, "  Context variables:")
    for var, value in context_vars.items():
        if var == "__builtins__":
            continue
        logger.log(level, f"    {var}: {type(value)}")

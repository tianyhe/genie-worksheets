"""Utility functions for handling Genie fields.

This module provides utility functions for working with Genie fields,
including field extraction, comparison, and variable resolution.
"""

import inspect
from typing import Any, List, Optional

from loguru import logger


def get_genie_fields_from_ws(obj: Any) -> list:
    """Get all GenieField instances from a GenieWorksheet.

    Args:
        obj: The worksheet to get fields from

    Returns:
        List of GenieField instances
    """
    # logger.debug(f"Getting fields from worksheet: {obj.__class__.__name__}")
    fields = []

    try:
        for attr in obj._ordered_attributes:
            if not attr.startswith("_"):
                field = getattr(obj, attr)
                if (
                    hasattr(field, "__class__")
                    and field.__class__.__name__ == "GenieField"
                ):
                    logger.debug(f"Found field: {attr}")
                    fields.append(field)

        # logger.debug(f"Found {len(fields)} fields in worksheet")
        return fields
    except AttributeError as e:
        logger.error(f"Error getting fields from worksheet: {str(e)}")
        return []


def same_field(field1: Any, field2: Any) -> bool:
    """Check if two GenieField instances have the same values and confirmation status.

    Args:
        field1: The first field to compare
        field2: The second field to compare

    Returns:
        True if the fields are the same, False otherwise
    """
    logger.debug(f"Comparing fields: {field1.name} and {field2.name}")

    try:
        values_equal = field1.value == field2.value
        confirmation_equal = field1.confirmed == field2.confirmed

        logger.debug(f"Values equal: {values_equal}")
        logger.debug(f"Confirmation status equal: {confirmation_equal}")

        return values_equal and confirmation_equal
    except AttributeError as e:
        logger.error(f"Error comparing fields: {str(e)}")
        return False


def find_all_variables_matching_name(field_name: str, context: Any) -> List[str]:
    """Find all variables in the context that match a field name.

    Args:
        field_name: The field name to search for
        context: The context to search in

    Returns:
        List of matching variable names
    """
    logger.debug(f"Searching for variables matching field name: {field_name}")
    variables = []

    def find_matching_variables(obj: Any, field_name: str, key: str):
        """Recursively find matching variables in an object.

        Args:
            obj: The object to search in
            field_name: The field name to match
            key: The current key path
        """
        logger.debug(f"Searching in object: {key}")
        for field in get_genie_fields_from_ws(obj):
            if field.name == field_name:
                var_name = key + "." + field_name
                logger.debug(f"Found matching variable: {var_name}")
                variables.append(var_name)

    try:
        for key, value in context.context.items():
            if hasattr(value, "_ordered_attributes") and not inspect.isclass(value):
                find_matching_variables(value, field_name, key)
        logger.debug(f"Found {len(variables)} matching variables")
        return variables
    except Exception as e:
        logger.error(f"Error finding variables: {str(e)}")
        return []


def get_field_variable_name(obj: Any, context: Any) -> str:
    """Get the variable name of a field in a worksheet.

    Args:
        obj: The worksheet object
        context: The context to search in

    Returns:
        The variable name of the field
    """
    logger.debug("Getting field variable name")
    logger.debug(f"Field object: {obj}")

    try:
        for name, value in context.context.items():
            if not inspect.isclass(value) and hasattr(value, "_ordered_attributes"):
                logger.debug(f"Checking worksheet: {name}")
                for field in get_genie_fields_from_ws(value):
                    if field == obj:
                        var_name = name + "." + field.name
                        logger.debug(f"Found variable name: {var_name}")
                        return var_name

        logger.debug("No variable name found, returning original object")
        return obj
    except Exception as e:
        logger.error(f"Error getting field variable name: {str(e)}")
        return obj


def variable_resolver(
    var_name: str, global_context: Any, local_context: Any
) -> Optional[str]:
    """Resolve variable names in the context.

    This function resolves variable names since they are stored as <obj_name>.<field_name>
    in the context and the user only provides the field name. It also tracks the latest
    object of a worksheet for correct resolution.

    Args:
        var_name: The variable name to resolve
        global_context: The global context
        local_context: The local context

    Returns:
        The resolved variable name or None if not found
    """
    logger.debug(f"Resolving variable name: {var_name}")

    try:
        # Check local context first
        if var_name in local_context.context:
            logger.debug(f"Found variable in local context: {var_name}")
            return var_name
        elif var_name in global_context.context:
            logger.debug(f"Found variable in global context: {var_name}")
            return var_name
        else:
            # Search in local context first
            candidates = find_all_variables_matching_name(var_name, local_context)
            logger.debug(f"Found {len(candidates)} candidates in local context")

            if len(candidates) == 0:
                # If not found in local context, search in global context
                candidates = find_all_variables_matching_name(var_name, global_context)
                logger.debug(f"Found {len(candidates)} candidates in global context")

            if len(candidates) == 1:
                logger.debug(f"Found unique candidate: {candidates[0]}")
                return candidates[0]
            elif len(candidates) > 1:
                logger.warning(
                    f"Multiple candidates found for {var_name}: {candidates}"
                )
                logger.warning("Using first candidate as default")
                return candidates[0]

        logger.warning(f"No variable found for name: {var_name}")
        return None
    except Exception as e:
        logger.error(f"Error resolving variable name: {str(e)}")
        return None

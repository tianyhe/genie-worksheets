"""List processing utilities for the Genie system.

This module provides functions for processing lists in the Genie system,
including list variable resolution and formatting.
"""

from typing import Any, List

from loguru import logger

from worksheets.core.worksheet import GenieType
from worksheets.utils.variable import find_list_variable


def process_list_result(result_list: List[Any], context: Any) -> str:
    """Process a list result and format it as a string.

    This function handles list results, including GenieType values and
    list variable references.

    Args:
        result_list: List of values to process
        context: Context object containing variable information

    Returns:
        Formatted string representation of the list
    """
    logger.debug(f"Processing list result with {len(result_list)} items")

    parent_var_name = None
    indices = []
    result_strings = []

    for idx, val in enumerate(result_list):
        logger.debug(f"Processing item {idx}: {type(val)}")

        if isinstance(val, GenieType):
            logger.debug(f"Found GenieType value at index {idx}")
            var_name, var_idx = find_list_variable(val, context)

            if var_name is None and var_idx is None:
                logger.debug(f"No list variable found for value at index {idx}")
                result_strings.append(val)
            else:
                logger.debug(f"Found list variable: {var_name}[{var_idx}]")
                if parent_var_name is not None and parent_var_name != var_name:
                    error_msg = (
                        "Cannot handle multiple list variables in the same answer"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                parent_var_name = var_name
                indices.append(var_idx)
        else:
            logger.debug(f"Adding non-GenieType value at index {idx}")
            result_strings.append(val)

    if parent_var_name:
        logger.debug(f"Formatting list with parent variable {parent_var_name}")
        indices_str = [f"{parent_var_name}[{idx}]" for idx in indices]
        result = "[" + ", ".join(indices_str) + "]"
        logger.debug(f"Formatted result: {result}")
        return result

    result = str(result_strings)
    logger.debug(f"Formatted result: {result}")
    return result

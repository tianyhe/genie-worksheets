"""Utility functions for handling Genie worksheets.

This module provides utility functions for working with Genie worksheets,
including worksheet comparison, variable management, and context operations.
"""

from copy import deepcopy
from typing import Any, Dict

from loguru import logger

from worksheets.utils.field import get_genie_fields_from_ws, same_field


def same_worksheet(ws1: Any, ws2: Any) -> bool:
    """Check if two GenieWorksheet instances are the same.

    Args:
        ws1: The first worksheet to compare
        ws2: The second worksheet to compare

    Returns:
        True if the worksheets are the same, False otherwise
    """
    logger.debug(
        f"Comparing worksheets: {ws1.__class__.__name__} and {ws2.__class__.__name__}"
    )

    # Check random IDs if available
    if hasattr(ws1, "random_id") and hasattr(ws2, "random_id"):
        if ws1.random_id != ws2.random_id:
            logger.debug("Worksheets have different random IDs")
            return False

    # Check fields from WS1 to WS2
    for field1 in get_genie_fields_from_ws(ws1):
        field2_match = False
        logger.debug(f"Checking field {field1.name} from first worksheet")

        for field2 in get_genie_fields_from_ws(ws2):
            if field1.name == field2.name:
                field2_match = True
                logger.debug(f"Found matching field {field2.name} in second worksheet")

                if type(field1.value) is not type(field2.value):
                    logger.debug(
                        f"Field values have different types: {type(field1.value)} vs {type(field2.value)}"
                    )
                    return False

                if hasattr(field1.value, "_ordered_attributes") and hasattr(
                    field2.value, "_ordered_attributes"
                ):
                    logger.debug(
                        f"Recursively comparing nested worksheets for field {field1.name}"
                    )
                    if not same_worksheet(field1.value, field2.value):
                        return False
                else:
                    if not same_field(field1, field2):
                        logger.debug(f"Fields {field1.name} are not equal")
                        return False

        if not field2_match:
            logger.debug(
                f"No matching field found for {field1.name} in second worksheet"
            )
            return False

    # Check fields from WS2 to WS1 (for completeness)
    for field2 in get_genie_fields_from_ws(ws2):
        field1_match = False
        logger.debug(f"Checking field {field2.name} from second worksheet")

        for field1 in get_genie_fields_from_ws(ws1):
            if field2.name == field1.name:
                field1_match = True
                logger.debug(f"Found matching field {field1.name} in first worksheet")

                if hasattr(field2.value, "_ordered_attributes"):
                    logger.debug(
                        f"Recursively comparing nested worksheets for field {field2.name}"
                    )
                    if not same_worksheet(field2.value, field1.value):
                        return False
                else:
                    if not same_field(field2, field1):
                        logger.debug(f"Fields {field2.name} are not equal")
                        return False

        if not field1_match:
            logger.debug(
                f"No matching field found for {field2.name} in first worksheet"
            )
            return False

    logger.debug("Worksheets are equal")
    return True


def count_worksheet_variables(context: Dict[str, Any]) -> Dict[str, int]:
    """Count the number of variables of each worksheet type in the context.

    Args:
        context: The context dictionary to analyze

    Returns:
        Dictionary mapping variable names to their counts
    """
    logger.debug("Counting worksheet variables in context")
    var_counters = {}

    for key, value in context.items():
        if not hasattr(value, "_ordered_attributes"):
            continue
        if hasattr(value, "__class__") and value.__class__.__name__ == "Answer":
            continue

        from worksheets.utils.variable import generate_var_name

        var_name = generate_var_name(value.__class__.__name__)
        if var_name not in var_counters:
            var_counters[var_name] = -1
        var_counters[var_name] += 1
        logger.debug(f"Found variable {var_name}, count: {var_counters[var_name]}")

    return var_counters


def collect_all_parents(context: Any):
    """Collect all parent references for GenieField instances in the context.

    This ensures all fields have proper parent references set.

    Args:
        context: The context to process
    """
    logger.debug("Collecting parent references for all fields")

    for key, value in context.context.items():
        if hasattr(value, "_ordered_attributes"):
            logger.debug(f"Processing worksheet: {key}")
            for field in get_genie_fields_from_ws(value):
                if (
                    hasattr(field, "__class__")
                    and field.__class__.__name__ == "GenieField"
                ):
                    logger.debug(f"Setting parent for field {field.name}")
                    field.parent = value


def genie_deepcopy(context: Dict[str, Any]) -> Dict[str, Any]:
    """Special deepcopy function for Genie context.

    This function handles special cases for copying Genie objects.

    Args:
        context: The context dictionary to copy

    Returns:
        A deep copy of the context
    """
    logger.debug("Creating deep copy of context")
    new_context = {}

    for key, value in context.items():
        if key == "__builtins__":
            continue

        logger.debug(f"Copying context item: {key}")
        if (
            hasattr(value, "_ordered_attributes")
            or hasattr(value, "__class__")
            and value.__class__.__name__ == "GenieField"
        ):
            # logger.debug(f"Deep copying Genie object: {key}")
            new_context[key] = deepcopy(value)
        else:
            # logger.debug(f"Shallow copying regular object: {key}")
            new_context[key] = value

    return new_context


def any_open_empty_ws(turn_context: Any, global_context: Any) -> bool:
    from worksheets.core.worksheet import GenieWorksheet

    """Check if there are any available worksheet with any one field empty.

    TODO: should i also care about confirmation and check if the worksheet is complete or not?

    Args:
        turn_context: The current turn's context
        global_context: The global context

    Returns:
        True if there is an empty worksheet, False otherwise
    """
    logger.debug("Checking for empty worksheets")

    def check_context(context: Any) -> bool:
        for value in context.context.values():
            if not hasattr(value, "_ordered_attributes") or not isinstance(
                value, GenieWorksheet
            ):
                continue

            one_empty = False
            logger.debug(f"Checking worksheet: {value.__class__.__name__}")

            for field in get_genie_fields_from_ws(value):
                if field.value is None:
                    one_empty = True
                    break

            if one_empty:
                logger.debug(f"Found empty worksheet: {value.__class__.__name__}")
                return True

        return False

    turn_result = check_context(turn_context)
    global_result = check_context(global_context)

    if turn_result:
        logger.debug("Found empty worksheet in turn context")
    if global_result:
        logger.debug("Found empty worksheet in global context")

    return turn_result or global_result

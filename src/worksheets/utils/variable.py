"""Utility functions for handling variables in the Genie system.

This module provides utility functions for managing variables, including name generation,
variable resolution, and list operations.
"""

import inspect
import re
from typing import Any, List, Optional, Tuple

from worksheets.utils.field import get_genie_fields_from_ws
from worksheets.utils.worksheet import same_worksheet


def generate_var_name(class_name: str) -> str:
    """Generate a variable name from a class name.

    Converts CamelCase to snake_case.

    Args:
        class_name: The class name to convert

    Returns:
        The generated variable name
    """
    name = class_name[0].lower()
    for char in class_name[1:]:
        if char.isupper():
            name += "_" + char.lower()
        else:
            name += char
    return name


def get_variable_name(obj: Any, context: Any) -> str:
    """Get the variable name of a worksheet in the context.

    Args:
        obj: The worksheet object
        context: The context to search in

    Returns:
        The variable name of the worksheet
    """
    if not hasattr(obj, "_ordered_attributes"):
        return obj

    potential_objs = []
    for name, value in context.context.items():
        if not inspect.isclass(value) and hasattr(value, "_ordered_attributes"):
            if value.__class__.__name__ == obj.__class__.__name__:
                potential_objs.append((name, value))

    if len(potential_objs) == 1:
        return potential_objs[0][0]
    elif len(potential_objs) > 1:
        for name, value in potential_objs:
            fields_value = [(f.name, f.value) for f in get_genie_fields_from_ws(value)]
            obj_fields_value = [
                (f.name, f.value) for f in get_genie_fields_from_ws(obj)
            ]

            if deep_compare_lists(fields_value, obj_fields_value):
                return name

    return obj


def find_list_variable(val: Any, context: Any) -> Tuple[Optional[str], Optional[str]]:
    """Find the variable name which is a list and the index of the required value.

    Args:
        val: The value to find
        context: The context to search in

    Returns:
        Tuple of (variable name, index) or (None, None) if not found
    """
    for key, value in context.context.items():
        if isinstance(value, list):
            for idx, v in enumerate(value):
                if v == val:
                    return key, str(idx)
    return None, None


def select_variable_from_list(variables: List[Any], value: Any) -> Optional[str]:
    """Select a variable name from a list based on worksheet comparison.

    Args:
        variables: List of variables to search
        value: The value to match

    Returns:
        The selected variable name or None if not found
    """
    for var in variables:
        if same_worksheet(var, value):
            return generate_var_name(value.__class__.__name__)
    return None


def deep_compare_lists(list1: List[Any], list2: List[Any]) -> bool:
    """Compare two lists deeply, including nested structures.

    Args:
        list1: First list to compare
        list2: Second list to compare

    Returns:
        True if lists are equal, False otherwise
    """
    if len(list1) != len(list2):
        return False

    for item1, item2 in zip(list1, list2):
        if isinstance(item1, (list, tuple)) and isinstance(item2, (list, tuple)):
            if not deep_compare_lists(item1, item2):
                return False
        elif hasattr(item1, "_ordered_attributes") and hasattr(
            item2, "_ordered_attributes"
        ):
            if not same_worksheet(item1, item2):
                return False
        elif item1 != item2:
            return False

    return True


def camel_to_snake(name):
    name = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", name).lower()

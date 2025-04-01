"""Predicate evaluation utilities for the Genie system.

This module provides functions for evaluating predicates and conditions
in the Genie system, including code modification and sanitization.
"""

import ast
import re
import tokenize
from typing import Any, List, Optional, Union

from loguru import logger
from pygments.lexers.python import PythonLexer
from pygments.token import Token

from worksheets.utils.code_execution import modify_action_code, sanitize_dev_code
from worksheets.utils.logging_config import log_code_execution


def eval_predicates(
    predicates: Union[List[str], str, None], obj: Any, bot: Any, context: Any
) -> bool:
    """Evaluate a list of predicates or a single predicate.

    Args:
        predicates: The predicates to evaluate
        obj: The object context for evaluation
        bot: The bot instance
        context: The evaluation context

    Returns:
        True if all predicates evaluate to True, False otherwise
    """
    logger.debug("Starting predicate evaluation")
    logger.debug(f"Predicates to evaluate: {predicates}")

    if predicates is None:
        logger.debug("No predicates to evaluate")
        return True
    if isinstance(predicates, list) and len(predicates) == 0:
        logger.debug("Empty predicate list")
        return True

    try:
        if isinstance(predicates, list):
            logger.debug("Evaluating list of predicates")
            results = [
                parse_single_predicate(predicate, obj, bot, context)
                for predicate in predicates
            ]
            logger.debug(f"Predicate results: {results}")
            return all(results)
        else:
            logger.debug("Evaluating single predicate")
            result = parse_single_predicate(predicates, obj, bot, context)
            logger.debug(f"Predicate result: {result}")
            return result
    except Exception as e:
        logger.error(f"Error evaluating predicates: {str(e)}")
        return False


def parse_single_predicate(
    predicate: Union[str, bool], obj: Any, bot: Any, context: Any
) -> bool:
    """Parse and evaluate a single predicate.

    Args:
        predicate: The predicate to evaluate
        obj: The object context for evaluation
        bot: The bot instance
        context: The evaluation context

    Returns:
        The result of the predicate evaluation
    """
    logger.debug(f"Parsing single predicate: {predicate}")

    try:
        if isinstance(predicate, bool):
            logger.debug(f"Boolean predicate, returning: {predicate}")
            return predicate
        if predicate.upper() == "TRUE":
            logger.debug("TRUE predicate")
            return True
        elif predicate.upper() == "FALSE":
            logger.debug("FALSE predicate")
            return False
        elif predicate == "":
            logger.debug("Empty predicate")
            return True

        logger.debug("Modifying predicate code")
        code = modify_action_code(predicate, obj, bot, context)
        code = sanitize_dev_code(code, bot.get_all_variables()).strip()
        logger.debug(f"Modified and sanitized code: {code}")

        log_code_execution(code, context.context)
        res: bool = bot.eval(code, context)
        logger.debug(f"Predicate evaluation result: {res}")

        if "_obj" in context.context:
            logger.debug("Cleaning up _obj from context")
            del context.context["_obj"]

        return res
    except Exception as e:
        logger.error(f"Error parsing predicate: {str(e)}")
        return False

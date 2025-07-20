"""Utility functions for handling Genie worksheet annotations and context management.

This module provides utilities for managing and formatting Genie worksheet annotations,
handling different types of answers, and preparing context for semantic parsing and
dialogue interactions.
"""

from typing import Any, List, Optional

from loguru import logger

from worksheets.core.worksheet import Answer, GenieResult, GenieType, GenieWorksheet
from worksheets.utils.variable import find_list_variable


def _process_list_result(result_list: List[Any], context: Any) -> str:
    """Process a list result and format it as a string.

    Args:
        result_list: List of values to process
        context: Context object containing variable information

    Returns:
        Formatted string representation of the list
    """
    parent_var_name = None
    indices = []
    result_strings = []

    for val in result_list:
        if isinstance(val, GenieType):
            var_name, idx = find_list_variable(val, context)
            if var_name is None and idx is None:
                result_strings.append(val)
            else:
                if parent_var_name is not None and parent_var_name != var_name:
                    logger.error(
                        "Cannot handle multiple list variables in the same answer"
                    )
                parent_var_name = var_name
                indices.append(idx)
        else:
            result_strings.append(val)

    if parent_var_name:
        indices_str = [f"{parent_var_name}[{idx}]" for idx in indices]
        return "[" + ", ".join(indices_str) + "]"

    return str(result_strings)


def _format_answer_schema(
    key: str, answer: Answer, response_generator: bool, context: Any
) -> str:
    """Format the schema string for an Answer object.

    Args:
        key: The variable name
        answer: The Answer object
        response_generator: Whether to include response generation info
        context: Context object containing variable information

    Returns:
        Formatted schema string
    """
    schema = []

    # Format the answer definition
    if answer.query.value is not None and response_generator:
        schema.append(
            f"{key} = answer({repr(answer.nl_query)}, sql={repr(answer.query.value)})"
        )
    else:
        schema.append(f"{key} = answer({repr(answer.nl_query)})")

    # Format the result if it exists
    if not answer.result:
        schema.append(f"{key}.result = None")
        return "\n".join(schema) + "\n"

    result = answer.result.value if hasattr(answer.result, "value") else answer.result

    if isinstance(result, list):
        result_str = _process_list_result(result, context)
    else:
        result_str = (
            result.schema_without_type(context)
            if isinstance(result, GenieWorksheet)
            else str(result)
        )

    schema.append(f"{key}.result = {result_str}")
    return "\n".join(schema) + "\n"


def _format_worksheet_schema(
    key: str, worksheet: GenieWorksheet, context: Any
) -> Optional[str]:
    """Format the schema string for a GenieWorksheet object.

    Args:
        key: The variable name
        worksheet: The GenieWorksheet object
        context: Context object

    Returns:
        Formatted schema string or None if worksheet should be skipped
    """
    if worksheet.__class__.__name__ == "MoreFieldInfo":
        return None

    schema = []
    schema.append(f"{key} = {str(worksheet.schema_without_type(context))}")

    if hasattr(worksheet, "result") and worksheet.result:
        schema.append(f"{key}.result = {str(worksheet.result.value)}")

    return "\n".join(schema) + "\n"


def _format_result_schema(key: str, result: GenieResult, context: Any) -> str:
    """Format the schema string for a GenieResult object.

    Args:
        key: The variable name
        result: The GenieResult object
        context: Context object containing variable information

    Returns:
        Formatted schema string
    """
    schema = []
    schema.append(f"{key} = {str(result.value)}")
    return "\n".join(schema) + "\n"


def handle_genie_type(
    key: str, value: Any, context: Any, response_generator: bool
) -> Optional[str]:
    """Processes a Genie type value and generates its schema representation.

    Args:
        key: The key/name of the Genie type value
        value: The value to process
        context: The context object containing variable information
        response_generator: Flag indicating whether to include response generation info

    Returns:
        The schema representation of the Genie type value, or None if not applicable
    """
    if isinstance(value, GenieType) or key.startswith("__"):
        return None

    if isinstance(value, Answer):
        return _format_answer_schema(key, value, response_generator, context)

    if isinstance(value, GenieWorksheet):
        return _format_worksheet_schema(key, value, context)

    if isinstance(value, GenieResult):
        return _format_result_schema(key, value, context)

    return None


def get_context_schema(context, response_generator=False):
    """Generates a schema representation of the given context.

    Args:
        context: The context object containing variables and their values.
        response_generator (bool, optional): Flag to include response generation info. Defaults to False.

    Returns:
        str: A string representation of the context schema with escaped backslashes removed.
    """
    # Generating schema with separation of completed and active worksheets/APIs
    completed_parts = []
    active_parts = []

    for key, value in context.context.items():
        # Handle list of GenieType values first (same logic as before)
        if isinstance(value, list):
            bad_list = False
            for val in value:
                if not isinstance(val, GenieType):
                    bad_list = True
                    break

            if not bad_list:
                active_parts.append(f"{key} = {str(value)}\n")
            continue

        # Handle individual GenieWorksheet / Answer / GenieType, etc.
        new_schema = handle_genie_type(key, value, context, response_generator)
        if not new_schema:
            continue

        # Classify into completed vs active based on action_performed flag
        if isinstance(value, GenieWorksheet) and getattr(
            value, "action_performed", False
        ):
            completed_parts.append(new_schema)
        else:
            active_parts.append(new_schema)

    # Assemble final output
    if completed_parts:
        schema = (
            "### Completed APIs\n"
            + "".join(completed_parts)
            + "### Active APIs\n"
            + "".join(active_parts)
        )
    else:
        schema = "".join(active_parts)

    return schema.replace("\\", "")


def get_agent_action_schemas(agent_acts, *args, **kwargs):
    """Converts agent actions into their schema representations.

    Args:
        agent_acts: List of agent actions to convert.
        *args: Variable length argument list.
        **kwargs: Arbitrary keyword arguments.

    Returns:
        list: List of string representations of agent actions.
    """
    agent_acts_schema = []
    if agent_acts:
        for act in agent_acts:
            agent_acts_schema.append(str(act))

    return agent_acts_schema


def pretty_print_actions(actions, indent=2):
    """Pretty prints a list of actions.

    Args:
        actions: List of actions to print.
        indent: Number of spaces to indent the output.

    Returns:
        str: A string representation of the actions.
    """
    # Use the provided indent parameter to control indentation
    indent_str = " " * indent
    return "[\n" + "\n".join([f"{indent_str}{action}" for action in actions]) + "\n]"


def prepare_context_input(runtime, dlg_history, current_dlg_turn, starting_prompt: str):
    """Prepared context input for dialogue processing.
    currency
        Args:
            runtime: The runtime instance containing context and configuration.
            dlg_history: List of previous dialogue turns.
            current_dlg_turn: The current dialogue turn being processed.

        Returns:
            tuple: A tuple containing (state_schema, agent_acts, agent_utterance).
    """
    state_schema = get_context_schema(runtime.context)
    if len(dlg_history):
        agent_acts = pretty_print_actions(
            get_agent_action_schemas(dlg_history[-1].system_action, runtime.context),
            indent=2,
        )
        agent_utterance = dlg_history[-1].system_response
    else:
        agent_acts = "None"
        agent_utterance = starting_prompt

    state_schema = "None" if state_schema == "" else state_schema

    return state_schema, agent_acts, agent_utterance


def prepare_semantic_parser_input(
    runtime, dlg_history, current_dlg_turn, starting_prompt
):
    """Prepares input for semantic parsing by gathering necessary context and schemas.

    Args:
        runtime: The runtime instance containing worksheets and database models.
        dlg_history: List of previous dialogue turns.
        current_dlg_turn: The current dialogue turn being processed.

    Returns:
        tuple: A tuple containing (state_schema, agent_acts, agent_utterance,
               available_worksheets_text, available_dbs_text).
    """
    state_schema, agent_acts, agent_utterance = prepare_context_input(
        runtime, dlg_history, current_dlg_turn, starting_prompt
    )

    available_worksheets = [
        ws.get_semantic_parser_schema() for ws in runtime.genie_worksheets
    ]
    available_worksheets_text = "\n".join(available_worksheets)

    available_dbs = [
        db.get_semantic_parser_schema(db=True) for db in runtime.genie_db_models
    ]
    available_dbs_text = "\n".join(available_dbs)
    return (
        state_schema,
        agent_acts,
        agent_utterance,
        available_worksheets_text,
        available_dbs_text,
    )

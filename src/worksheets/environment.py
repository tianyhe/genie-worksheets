"""Core environment module for Genie worksheets and runtime management.

This module provides the foundational classes and utilities for managing Genie worksheets,
including type handling, context management, and runtime execution. It implements the core
functionality for worksheet validation, action execution, and state management.
"""

from __future__ import annotations

import ast
import inspect
import re
import tokenize
from copy import deepcopy
from enum import Enum
from functools import partial
from typing import Any

from bs4 import BeautifulSoup
from loguru import logger
from pygments.lexers.python import PythonLexer
from pygments.token import Token

from worksheets.llm import llm_generate
from worksheets.utils import (
    callable_name,
    camel_to_snake,
    deep_compare_lists,
    generate_var_name,
)


class GenieValue:
    """A class to represent a value in Genie.

    This class wraps primitive values (string, int, float, etc.) with additional
    functionality like confirmation status tracking.

    Attributes:
        value: The wrapped primitive value.
        confirmed (bool): Whether this value has been confirmed by the user.
    """

    def __init__(self, value):
        """Initialize a GenieValue.

        Args:
            value: The primitive value to wrap.
        """
        self.value = value
        self.confirmed = False

    def __repr__(self):
        return f"{self.value}"

    def __eq__(self, other):
        if isinstance(other, GenieValue):
            if self.value == other.value:
                return True

        return self.value == other

    def confirm(self, confirmed: bool = True):
        """Mark the value as confirmed.

        Args:
            confirmed (bool, optional): Whether to mark as confirmed. Defaults to True.

        Returns:
            GenieValue: The confirmed value instance.
        """
        self.confirmed = confirmed
        return self

    def __str__(self):
        return self.value

    def __hash__(self):
        return hash(self.value)


class GenieResult(GenieValue):
    """A class to represent results from executions.

    This class extends GenieValue to store results from Answer executions or
    other actions, maintaining references to parent objects.

    Attributes:
        value: The result value.
        parent: The parent object that produced this result.
        parent_var_name: The variable name of the parent in the context.
    """

    def __init__(self, value, parent, parent_var_name):
        """Initialize a GenieResult.

        Args:
            value: The result value.
            parent: The parent object that produced this result.
            parent_var_name: The variable name of the parent in the context.
        """
        super().__init__(value)
        self.parent = parent
        self.parent_var_name = parent_var_name

    def __getitem__(self, item):
        return self.value[item]


class GenieREPR(type):
    """A metaclass to customize string representation of Genie classes.

    This metaclass provides custom string representation for classes that use it,
    maintaining ordered attributes and generating schema representations.

    Attributes:
        _ordered_attributes: List of ordered attribute names for the class.
    """

    def __new__(cls, name, bases, dct):
        new_class = super().__new__(cls, name, bases, dct)
        # Store the ordered attributes, these are used for asking questions in the order they are defined
        new_class._ordered_attributes = [k for k in dct if not k.startswith("__")]
        return new_class

    def __repr__(cls):
        parameters = []
        for field in get_genie_fields_from_ws(cls):
            parameters.append(field.schema(value=False))

        return f"{cls.__name__}({', '.join([param for param in parameters])})"

    def get_semantic_parser_schema(cls):
        parameters = []
        if hasattr(cls, "predicate") and (cls.predicate == "" or cls.predicate is True):
            for field in get_genie_fields_from_ws(cls):
                if not field.internal:
                    parameters.append(field.schema(value=False))

        return f"{cls.__name__}({', '.join([repr(param) for param in parameters])})"


def validation_check(name, value, validation):
    """Validate a value against specified criteria using LLM.

    Args:
        name (str): The name of the field being validated.
        value (Any): The value to validate.
        validation (str): The validation criteria.

    Returns:
        tuple: A tuple containing:
            - bool: Whether the value is valid.
            - str or None: The reason for invalidity, if any.
    """
    prompt_path = "validation_check.prompt"
    if isinstance(value, GenieValue):
        val = str(value.value)
    else:
        val = str(value)
    response = llm_generate(
        prompt_path,
        {
            "value": val,
            "criteria": validation,
            "name": name,
        },
        model_name="gpt-4o-mini",
    )

    bs = BeautifulSoup(response, "html.parser")
    reason = bs.find("reason")
    valid = bs.find("valid")

    if valid:
        return valid.text.strip().lower() == "true", None
    return False, reason.text if reason else None


class GenieField:
    """A class representing a field in a Genie worksheet.

    This class handles field definitions, validation, and value management for
    worksheet fields. It supports various field types, validation rules, and
    action triggers.

    Attributes:
        slottype (str): The type of the field.
        name (str): The field name.
        question (str): Question to ask when field needs filling.
        description (str): Field description for LLM understanding.
        predicate (str): Condition for field relevance.
        ask (bool): Whether to ask user for this field.
        optional (bool): Whether field is optional.
        actions: Actions to perform when field is filled.
        requires_confirmation (bool): Whether field needs confirmation.
        internal (bool): Whether field is system-managed.
        primary_key (bool): Whether field is a primary key.
        validation (str): Validation criteria.
        parent: Parent worksheet.
        bot: Associated bot instance.
    """

    def __init__(
        self,
        # The type of the slot, e.g., str, int, etc.
        slottype: str,
        # The name of the field (variable name)
        name: str,
        # The question to ask the user if the field is not filled
        question: str = "",
        # A description of the field. This is provided to the LLM for better understanding.
        description: str = "",
        # A predicate to determine if the field should be filled
        predicate: str = "",
        # Whether to ask the user for this field
        ask: bool = True,
        # Whether this field is optional
        optional: bool = False,
        # Any actions to perform when this field is filled
        actions=None,
        # The initial value of the field
        value=None,
        # Whether this field requires confirmation
        requires_confirmation: bool = False,
        # Whether this field is internal (not shown to the user and filled by the system)
        internal: bool = False,
        # Whether this field is a primary key. Used for database Worksheets.
        primary_key: bool = False,
        # Whether this field has been confirmed by the user
        confirmed: bool = False,
        # Any validation criteria for this field
        validation: str | None = None,
        # The parent worksheet
        parent=None,
        # The bot instance (GenieRuntime)
        bot=None,
        # Whether an action has been performed for this field
        action_performed=False,
        **kwargs,
    ):
        self.predicate = predicate
        self.slottype = slottype
        self.name = name
        self.question = question
        self.ask = ask
        self.optional = optional
        if self.ask is False:
            self.optional = True
        self.actions = actions
        self.requires_confirmation = requires_confirmation
        self.internal = internal
        self.description = description
        self.primary_key = primary_key
        self.validation = validation
        self.parent = parent
        self.bot = bot

        self.action_performed = action_performed
        self._value = self.init_value(value)
        self._confirmed = confirmed

    def __deepcopy__(self, memo):
        return GenieField(
            slottype=deepcopy(self.slottype, memo),
            name=deepcopy(self.name, memo),
            question=deepcopy(self.question, memo),
            description=deepcopy(self.description, memo),
            predicate=deepcopy(self.predicate, memo),
            ask=deepcopy(self.ask, memo),
            optional=deepcopy(self.optional, memo),
            actions=deepcopy(self.actions, memo),
            value=deepcopy(self.value, memo),
            requires_confirmation=deepcopy(self.requires_confirmation, memo),
            internal=deepcopy(self.internal, memo),
            primary_key=deepcopy(self.primary_key, memo),
            confirmed=deepcopy(self.confirmed, memo),
            validation=deepcopy(self.validation, memo),
            action_performed=deepcopy(self.action_performed, memo),
            parent=self.parent,
            bot=self.bot,
        )

    def perform_action(self, bot: GenieRuntime, local_context: GenieContext):
        """Perform the action associated with this field if it hasn't been performed yet.

        Args:
            bot (GenieRuntime): The bot instance.
            local_context (GenieContext): The local context for the action.

        Returns:
            list: A list of actions performed.
        """
        if self.action_performed:
            return []
        logger.info(f"Peforming action for {self.name}: {self.actions.action}")
        acts = []

        # If there are no actions, return an empty list
        if self.actions is None or len(self.actions) == 0:
            return acts

        # Perform the action
        acts = self.actions.perform(self, bot, local_context)
        self.action_performed = True

        return acts

    def __repr__(self) -> str:
        return self.schema(value=True)

    def schema(self, value=True):
        """Generate a schema representation of the field.

        Args:
            value (bool, optional): Whether to include the value in the schema. Defaults to True.

        Returns:
            str: The schema representation.
        """
        # Getting the type of sources_type as a string
        if isinstance(self.slottype, str) and self.slottype == "confirm":
            slottype = "bool"
        elif self.slottype.__name__ in ["List", "Dict"]:
            slottype = self.slottype.__name__ + "["
            if isinstance(self.slottype.__args__[0], str):
                slottype += self.slottype.__args__[0]
            else:
                slottype += self.slottype.__args__[0].__name__
            slottype += "]"
        # Special case for enums
        elif inspect.isclass(self.slottype) and issubclass(self.slottype, Enum):
            options = ", ".join([repr(e.name) for e in self.slottype])
            slottype = "Enum[" + options + "]"
        else:
            slottype = self.slottype.__name__

        if value:
            if self.value is None:
                val = "None"
            elif self.value == "":
                val = '""'
            else:
                val = self.value
            return f"{self.name}: {slottype} = {repr(val)}"
        else:
            return f"{self.name}: {slottype}"

    def schema_without_type(self, no_none=False):
        """Generate a schema representation of the field without type information.

        Args:
            no_none (bool, optional): Whether to exclude None values. Defaults to False.

        Returns:
            str: The schema representation without type.
        """
        if self.value is None:
            val = None
        elif self.value == "":
            val = '""'
        else:
            if isinstance(self.value, str):
                val = f"{repr(self.value)}"
            else:
                val = self.value

        if no_none and val == "None":
            return

        return f"{self.name} = {repr(val)}"

    @property
    def confirmed(self):
        if hasattr(self, "_value") and isinstance(self._value, GenieValue):
            return self._value.confirmed
        return self._confirmed

    @confirmed.setter
    def confirmed(self, confirmed: bool):
        self._confirmed = confirmed

    @property
    def value(self):
        if isinstance(self._value, GenieValue):
            return self._value.value
        return self._value

    @value.setter
    def value(self, value):
        self.action_performed = False
        self._value = self.init_value(value)

    def init_value(self, value: Any):
        """Initialize a field value with proper validation and wrapping.

        Args:
            value (Any): The value to initialize.

        Returns:
            GenieValue: The initialized value, or None if validation fails.
        """

        def previous_action_contains_confirm():
            """Only allow confirmation if the previous action was a confirmation action."""
            if self.bot.dlg_history is not None and len(self.bot.dlg_history):
                if self.bot.dlg_history[-1].system_action is not None:
                    for act in self.bot.dlg_history[-1].system_action.actions:
                        if isinstance(act, AskAgentAct):
                            if act.field.slottype == "confirm":
                                return True
            return False

        # TODO: If the value is set by the user for internal field, then do not assign.
        # if done by the system, then assign.
        if value == "" or value is None:
            value = None
        else:
            if self.slottype == "confirm":
                prev_confirm = previous_action_contains_confirm()
                if not prev_confirm:
                    return

            valid = True
            if self.validation:
                # Use LLM to check if the value is valid based on the validation rule
                matches_criteria, reason = validation_check(
                    self.name, value, self.validation
                )
                if not matches_criteria:
                    # If the validation fails, use the original value, log the error and set valid to False
                    if isinstance(value, GenieValue):
                        value = value.value
                    self.parent.bot.context.agent_acts.add(
                        ReportAgentAct(
                            query=f"{self.name}={value}",
                            message=f"Invalid value for {self.name}: {value} - {reason}",
                        )
                    )
                    valid = False

            if valid:
                # If the value is valid, create a GenieValue instance
                if isinstance(value, GenieValue):
                    return value
                else:
                    return GenieValue(value)

    def __eq__(self, other):
        # For equality check, we compare the name and value of the fields
        if isinstance(other, GenieField):
            if self.name == other.name and self.value == other.value:
                return True
        return False


class GenieWorksheet(metaclass=GenieREPR):
    """Base class for Genie worksheets.

    This class provides the foundation for defining worksheets with fields,
    actions, and state management. It handles initialization, field management,
    and action execution.

    Attributes:
        action_performed (bool): Whether worksheet actions have been executed.
        result: The result of worksheet execution.
        random_id (int): Unique identifier for the worksheet instance.
    """

    def __init__(self, **kwargs):
        self.action_performed = False
        self.result = None
        self.random_id = 0

        # Since the user doesn't initialize the fields, we need to do it for them
        # first, we go over all the GenieFields in the class
        # then, we create a params dict with all the fields in the GenieField
        # finally, we check if the user has passed in a value for any GenieField
        # if they have, we set the value of the GenieField to the value passed in
        # and then we set the attribute of the class to the GenieField
        for attr_name, attr_value in self.__class__.__dict__.items():
            if isinstance(attr_value, GenieField):
                params = {
                    field: getattr(attr_value, field)
                    for field in dir(attr_value)
                    if not field.startswith("__")
                }
                # if the user has passed in a value for the GenieField, set it
                # eg. Book(booking_id=125)
                # then the user has passed in a value for booking_id
                # attr_name is all the GenieFields in the class
                # kwargs is all the values the user has passed in (like booking_id=125)
                if attr_name in kwargs:
                    params["value"] = kwargs[attr_name]
                    if params["value"] == "":
                        params["value"] = None

                if "optional" in params:
                    if not params["optional"] and params["value"] == "NA":
                        params["value"] = None

                setattr(self, attr_name, GenieField(**params))

    def perform_action(self, bot: GenieRuntime, local_context: GenieContext):
        """Perform the action associated with this worksheet if it hasn't been performed yet.

        Args:
            bot (GenieRuntime): The bot instance.
            local_context (GenieContext): The local context for the action.

        Returns:
            list: A list of actions performed.
        """

        if self.action_performed:
            return []
        acts = []

        if self.actions is None or len(self.actions) == 0:
            return acts

        acts = self.actions.perform(self, bot, local_context)
        self.action_performed = True

        return acts

    def is_complete(self, bot: GenieRuntime, context: GenieContext) -> bool:
        """Check if the worksheet is complete by evaluating all fields.

        Args:
            bot (GenieRuntime): The bot instance.
            context (GenieContext): The context for evaluation.

        Returns:
            bool: True if the worksheet is complete, False otherwise.
        """

        for field in get_genie_fields_from_ws(self):
            if eval_predicates(field.predicate, self, bot, context):
                if isinstance(field.value, GenieWorksheet):
                    if not field.value.is_complete(bot, context):
                        return False
                if (field.value is None or field.value == "") and not field.optional:
                    return False

                if field.requires_confirmation and not field.confirmed:
                    return False
        return True

    def __repr__(self):
        parameters = []
        for field in get_genie_fields_from_ws(self):
            if isinstance(field, GenieField):
                parameters.append(field)

        return f"{self.__class__.__name__}({', '.join([repr(param) for param in parameters])})"

    def schema_without_type(self, context: GenieContext) -> str:
        """Generate a schema representation of the worksheet without type information.

        Args:
            context (GenieContext): The context for the worksheet.

        Returns:
            str: The schema representation without type.
        """
        parameters = []
        for field in get_genie_fields_from_ws(self):
            if field.value is None:
                continue
            if isinstance(field.value, str):
                if field.value == "":
                    continue
                if field.confirmed:
                    parameters.append(f"{field.name} = confirmed({repr(field.value)})")
                else:
                    parameters.append(f"{field.name} = {repr(field.value)}")
            elif isinstance(field._value, GenieResult):
                if isinstance(field.value, list):
                    parent_var_name = None
                    indices = []

                    result_strings = []
                    for val in field.value:
                        if isinstance(val, GenieType):
                            var_name, idx = find_list_variable(val, context)
                            if var_name is None and idx is None:
                                result_strings.append(val)
                            else:
                                if (
                                    parent_var_name is not None
                                    and parent_var_name != var_name
                                ):
                                    logger.error(
                                        "Cannot handle multiple list variables in the same answer"
                                    )
                                parent_var_name = var_name  # Ignoring any potential multiple list variables

                                indices.append(idx)
                        else:
                            result_strings.append(val)

                    if parent_var_name:
                        indices_str = []
                        for idx in indices:
                            indices_str.append(f"{parent_var_name}[{idx}]")

                        result_strings = "[" + ", ".join(indices_str) + "]"
                if len(result_strings):
                    parameters.append(f"{field.name} = {str(result_strings)}")
                else:
                    # TODO: Instead of getting the var_name from paren, we should search and find the same type of answer from the context
                    parameters.append(f"{field.name} = {repr(field.value)}")
            elif isinstance(field.value, GenieType):
                # This should be straight forward, same as the one above
                var_name, idx = find_list_variable(field.value, context)
                if var_name is None and idx is None:
                    if field.confirmed:
                        parameters.append(
                            f"{field.name} = confirmed({repr(field.value)})"
                        )
                    else:
                        parameters.append(f"{field.name} = {repr(field.value)}")
                else:
                    if field.confirmed:
                        parameters.append(
                            f"{field.name} = confirmed({var_name}[{idx}])"
                        )
                    else:
                        parameters.append(f"{field.name} = {var_name}[{idx}]")
            else:
                var_name = get_variable_name(field.value, context)

                if isinstance(var_name, str):
                    if field.confirmed:
                        parameters.append(f"{field.name} = confirmed({repr(var_name)})")
                    else:
                        parameters.append(f"{field.name} = {var_name}")
                else:
                    val = field.schema_without_type(no_none=True)
                    if val:
                        parameters.append(val)

        return f"{self.__class__.__name__}({', '.join([str(param) for param in parameters])})"

    def execute(self, bot: GenieRuntime, local_context: GenieContext):
        """Execute the actions associated with this worksheet.

        Args:
            bot (GenieRuntime): The bot instance.
            local_context (GenieContext): The local context for execution.
        """
        parameters = []
        for f in get_genie_fields_from_ws(self):
            parameters.append(f.name + "= " + "self." + f.name)

        code = self.backend_api + "(" + ", ".join(parameters) + ")"
        var_name = get_variable_name(self, local_context)
        self.result = GenieResult(
            execute_query(code, self, bot, local_context), self, var_name
        )
        self.bot.context.agent_acts.add(
            ReportAgentAct(code, self.result, None, var_name + ".result")
        )
        self.action_performed = True
        # local_context.context[
        #     f"{generate_var_name(self.__class__.__name__)}_result"
        # ] = self.result

    # This might give me some troubles since we are already using .value at certain places.
    # def __getattr__(self, name):
    #     for field in get_genie_fields_from_ws(self):
    #         if field.name == name:
    #             return field.value

    @classmethod
    def new(cls, initialize_from_dict: dict):
        return cls(**initialize_from_dict)

    def __setattr__(self, name, value):
        if hasattr(self, name):
            attr = getattr(self, name)
            if isinstance(attr, GenieField):
                self.action_performed = False

                # if the worksheet has a confirm type field which is set to true
                # upon update, we need to set it to false
                for field in get_genie_fields_from_ws(self):
                    if field.slottype == "confirm" and field.value is True:
                        field.value = False

                if isinstance(value, GenieField) and value.name == name:
                    value.parent = self
                    super().__setattr__(name, value)
                    return

                if isinstance(value, GenieValue):
                    attr.value = value
                else:
                    attr.value = GenieValue(value)
                return
        super().__setattr__(name, value)

    def ask(self):
        """This is a hack for when the user asks the system to ask a question from a different worksheet.

        We increment the random_id to make sure that the ws is updated and the system with ask the question naturally
        """
        logger.info(f"Ask: {self}")
        self.random_id += 1


class GenieType(GenieWorksheet):
    """Base class for Genie type definitions.

    This class extends GenieWorksheet to provide type-specific functionality
    and validation. It's used to define custom types in the Genie system.

    Attributes:
        _parent: Parent object reference.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._parent = None

    def is_complete(self, *args, **kwargs):
        for field in get_genie_fields_from_ws(self):
            if field.primary_key and field.value is not None:
                return True

        return False


class GenieDB(GenieWorksheet):
    """Base class for Genie database models.

    This class extends GenieWorksheet to provide database-specific functionality
    and schema management.
    """


class Answer(GenieWorksheet):
    """Class representing an answer in the Genie system.

    This class handles query execution, result management, and parameter tracking
    for answers to user queries.

    Attributes:
        query (GenieField): The query to execute.
        actions: Associated actions.
        result: Query execution result.
        tables: Related database tables.
        potential_outputs: Possible output types.
        nl_query: Natural language query.
        param_names: Required parameter names.
    """

    def __init__(self, query, required_params, tables, nl_query):
        self.query = GenieField("str", "query", value=query)
        self.actions = Action(">suql_runner(self.query.value, self.required_columns)")
        self.result = None
        self.tables = tables
        self.potential_outputs = []
        self.nl_query = nl_query
        self.param_names = []
        self.action_performed = False

        for table in self.tables:
            self.potential_outputs.extend(self.bot.context.context[table].outputs)

        self.required_columns = [
            field.name
            for table in self.tables
            for field in get_genie_fields_from_ws(self.bot.context.context[table])
        ]

        # Create required params and add them to ordered attributes
        _ordered_attributes = ["query"]
        if required_params is not None:
            for db_name, params in required_params.items():
                for param in params:
                    setattr(
                        self,
                        f"{db_name}_{param}",
                        GenieField("str", f"{db_name}.{param}", value=None),
                    )
                    self.param_names.append(f"{db_name}_{param}")
                    _ordered_attributes.append(f"{db_name}_{param}")

        self._ordered_attributes = _ordered_attributes

    def execute(self, bot: GenieRuntime, local_context: GenieContext):
        """Execute the actions associated with this answer.

        Args:
            bot (GenieRuntime): The bot instance.
            local_context (GenieContext): The local context for the execution.
        """
        if self.action_performed:
            return
        results = execute_query(self.actions.action, self, bot, local_context)
        self.action_performed = True
        if results is None:
            results = []

        # Get more information about the fields
        ws, field_name, more_field_info_result = self.more_field_info_query(bot)
        logger.info(f"More Field Info: {more_field_info_result}")
        logger.info(f"Results: {results}")

        # Earlier we had a mechanism to check if the user is asking to execute a query or asking for more information
        # about the field. Hence we have output_idx.
        # For now we are going to assume that the user is asking for the output of the query
        output_idx = [1]

        if len(output_idx):
            output_idx = int(output_idx[0])
            if output_idx == 1:
                # Check if the output type is in the results
                output = self.output_in_result(results)
                var_name = get_variable_name(self, local_context)
                self.result = GenieResult(output, self, var_name)

                # Report the agent act
                self.bot.context.agent_acts.add(
                    ReportAgentAct(
                        self.query, self.result, var_name, var_name + ".result"
                    )
                )
                for i, _output in enumerate(output):
                    if isinstance(_output, GenieWorksheet):
                        # add the output to the local context
                        local_context.set(
                            f"{camel_to_snake(_output.__class__.__name__)}", _output
                        )
            elif output_idx == 2:
                # We don't use this for now but we can use it to ask for more information
                var_name = get_variable_name(self, local_context)
                self.result = GenieResult(more_field_info_result, self, var_name)
                self.bot.context.agent_acts.add(
                    ReportAgentAct(
                        f"AskClarificationQuestion({ws.__class__.__name__}, {field_name.name})",
                        self.result,
                        message_var_name=var_name + ".result",
                    )
                )

        # for i, _output in enumerate(output):
        #     local_context.context[f"__{var_name}_result_{i}"] = _output

    def more_field_info_query(self, bot: GenieRuntime):
        if bot.dlg_history is None or len(bot.dlg_history) == 0:
            return None, None, None
        if bot.dlg_history[-1].system_action is None:
            return None, None, None
        acts = bot.dlg_history[-1].system_action.actions
        for act in acts:
            if isinstance(act, AskAgentAct):
                more_field_info = generate_clarification(act.ws, act.field.name)
                if more_field_info:
                    return act.ws, act.field, more_field_info

        return None, None, None

    def output_in_result(self, results: list):
        """Check if the output type is in the results."""
        if len(self.potential_outputs):
            output_results = []
            for result in results:
                for output_type in self.potential_outputs:
                    found_primary_key = False
                    for field in get_genie_fields_from_ws(output_type):
                        if field.primary_key and field.name in result:
                            output_results.append(output_type(**result))
                            found_primary_key = True
                            break
                    if not found_primary_key:
                        output_results.append(result)

            return output_results
        return results

    def update(self, query, unfilled_params, tables, query_str):
        """Update the answer with new parameters and tables.

        We are not using this method anymore, but we can keep it for reference."""
        logger.error(f"Updating Answer: {query}, This has been deprecated")
        self.query.value = query
        for param in self.param_names:
            del self.__dict__[param]
            self._ordered_attributes.remove(param)
        self.param_names = []
        self.required_columns = [
            field.name
            for table in tables
            for field in get_genie_fields_from_ws(self.bot.context.context[table])
        ]
        self.tables = tables
        self.potential_outputs = []
        for table in self.tables:
            self.potential_outputs.extend(self.bot.context.context[table].outputs)

        if unfilled_params is not None:
            for db_name, params in unfilled_params.items():
                for param in params:
                    setattr(
                        self,
                        f"{db_name}_{param}",
                        GenieField("str", f"{db_name}.{param}", value=None),
                    )
                    self.param_names.append(f"{db_name}_{param}")
                    self._ordered_attributes.append(f"{db_name}_{param}")

        self.nl_query = query_str


class MoreFieldInfo(GenieWorksheet):
    """Class for managing additional field information requests.

    This class handles requests for clarification or additional information
    about specific fields.

    Attributes:
        api_name (GenieField): Name of the API.
        parameter_name (GenieField): Name of the parameter.
        actions: Associated actions.
    """

    def __init__(self, api_name, parameter_name):
        self.api_name = GenieField("str", "api_name", value=api_name)
        self.parameter_name = GenieField("str", "parameter_name", value=parameter_name)
        self.actions = Action(
            ">answer_clarification_question(self.api_name, self.parameter_name)"
        )
        self.action_performed = False


class Action:
    """Class for managing worksheet actions.

    This class handles action definition, execution, and result management
    for worksheet operations.

    Attributes:
        action: The action to perform.
    """

    def __init__(self, action):
        self.action = action

    def __len__(self):
        return len(self.action)

    def perform(
        self, obj: GenieWorksheet, bot: GenieRuntime, local_context: GenieContext
    ) -> list:
        """Perform the action with the given context.

        Args:
            obj (GenieWorksheet): The worksheet object.
            bot (GenieRuntime): The bot instance.
            local_context (GenieContext): The local context.

        Returns:
            list: List of actions performed.
        """
        code = modify_action_code(self.action, obj, bot, local_context)
        code = sanitize_dev_code(code, bot.get_all_variables())

        # this is right now a hack. We are just going to assign all the statments to a variable
        # and then return the variable
        acts = []
        # here what i need to do is:
        # 1. rewrite the code such that and inbuilt function appends its result to __return
        # 2. then return __return

        # We append the results to the __return variable. This is done by the rewriter
        transformed_code = rewrite_action_code(
            code,
            ["say", "propose", "answer_clarification_question"],  # predefined actions
        )
        code_ = f"__return = []\n{transformed_code}"

        local_context.context["__return"] = None

        # Execute the action code
        bot.execute(code_, local_context)

        # Context management
        if local_context.context["__return"] is not None:
            acts.extend(local_context.context["__return"])
        del local_context.context["__return"]

        if "_obj" in local_context.context:
            del local_context.context["_obj"]

        return acts


class GenieRuntime:
    """Main runtime environment for Genie system.

    This class manages the execution environment, including worksheet registration,
    context management, and action execution.

    Attributes:
        name (str): Runtime instance name.
        prompt_dir (str): Directory for prompts.
        args: Additional arguments.
        genie_worksheets (list): Registered worksheets.
        genie_db_models (list): Registered database models.
        starting_prompt (str): Initial system prompt.
        description (str): Runtime description.
        suql_runner: SQL query runner.
        suql_parser: SQL query parser.
        context (GenieContext): Global context.
        dlg_history (list): Dialogue history.
    """

    def __init__(
        self,
        # The name of the bot
        name,
        # The directory where the prompts are stored
        prompt_dir,
        # The starting prompt of the bot
        starting_prompt=None,
        # A description of the bot
        description=None,
        # Any additional arguments
        args=None,
        # Define the API to be used
        api=None,
        # The SUQL runner (SUQLKnowledgeBase)
        suql_runner=None,
        # The SUQL parser (SUQLParser)
        suql_parser=None,
    ):
        self.prompt_dir = prompt_dir
        self.args = args
        self.name = name
        self.genie_worksheets = []
        self.genie_db_models = []
        if starting_prompt is None:
            self.starting_prompt = f"Hello! I'm the {name}. What would you like to do?"
        self.starting_prompt = starting_prompt
        self.description = description
        self.suql_runner = suql_runner
        self.suql_parser = suql_parser

        self._interpreter = GenieInterpreter()
        self.context = GenieContext()
        self.local_context_init = GenieContext()

        # add the api to the context
        if api:
            if isinstance(api, list):
                apis = api
            else:
                api_funcs = inspect.getmembers(api, inspect.isfunction)
                apis = [func for name, func in api_funcs if not name.startswith("_")]
        else:
            apis = []
        self.dlg_history = []

        self.order_of_actions = []

        apis.extend([self.suql_runner])

        Answer.bot = self

        # Add the predefined apis and functions
        apis.extend(
            [
                propose,
                confirm,
                GenieValue,
                partial(answer_clarification_question, context=self.context),
                Answer,
                MoreFieldInfo,
                say,
            ]
        )
        for api in apis:
            self.add_api(api)

    def reset(self):
        """Reset the bot's context and state."""
        self.context.reset_agent_acts()
        to_delete = []
        for key, value in self.context.context.items():
            if isinstance(value, GenieWorksheet):
                to_delete.append(key)

        for key in to_delete:
            del self.context.context[key]
        self.dlg_history = None
        self.order_of_actions = []

    def add_worksheet(self, ws: type):
        """Add a worksheet to the bot's context.

        Args:
            ws (type): The worksheet class to add.
        """
        ws.bot = self
        for field in get_genie_fields_from_ws(ws):
            field.parent = ws
            field.bot = self
        self.genie_worksheets.append(ws)
        self.context.set(ws.__name__, ws)
        # self.context.update(self._grab_all_variables(ws))
        # self.local_context_init.update(self._grab_all_variables(ws))

    def add_db_model(self, db_model: type):
        """Add a database model to the bot's context.

        Args:
            db_model (type): The database model class to add.
        """
        db_model.bot = self
        for field in get_genie_fields_from_ws(db_model):
            field.parent = db_model
            field.bot = self
        self.genie_db_models.append(db_model)
        self.context.set(db_model.__name__, db_model)
        # self.context.update(self._grab_all_variables(db_model))
        # self.local_context_init.update(self._grab_all_variables(db_model))

    def add_api(self, api: Any):
        """Add an API function to the context.

        Args:
            api (Any): The API function or object to add.
        """
        self.context.set(callable_name(api), api)

    def geniews(
        self,
        predicates=None,
        outputs: GenieWorksheet | dict | None = None,
        backend_api=None,
        actions="",
    ):
        """Decorator to define a Genie worksheet."""

        def decorator(cls):
            cls.predicate = predicates
            cls.outputs = outputs
            cls.backend_api = backend_api
            cls.actions = actions
            self.add_worksheet(cls)
            return cls

        return decorator

    def genie_sql(
        self,
        outputs: GenieWorksheet | dict | None = None,
        actions="",
    ):
        """Decorator to define a Genie database model."""

        def decorator(cls):
            if outputs is None:
                outputs = {}
            cls.outputs = outputs
            cls.actions = actions
            self.add_db_model(cls)
            return cls

        return decorator

    def execute(
        self, code: str, local_context: GenieContext | None = None, sp: bool = False
    ):
        """Execute the given code in the context of the bot.

        Args:
            code (str): The code to execute.
            local_context (GenieContext | None, optional): Local context to use. Defaults to None.
            sp (bool, optional): Whether this is a semantic parser execution. Defaults to False.
        """
        if local_context:
            local_context.update(
                {k: v for k, v in self.local_context_init.context.items()}
            )
        else:
            local_context = GenieContext(
                {k: v for k, v in self.local_context_init.context.items()}
            )
        self._interpreter.execute(
            code,
            self.context,
            local_context,
            sp=sp,
        )

        # Add the parents for all the objects in the local context
        collect_all_parents(local_context)

    def eval(self, code: str, local_context: GenieContext | None = None) -> Any:
        """Evaluate the given code in the context of the bot.

        Args:
            code (str): The code to evaluate.
            local_context (GenieContext | None, optional): Local context to use. Defaults to None.

        Returns:
            Any: The result of the evaluation.
        """
        if local_context:
            local_context.update(
                {k: v for k, v in self.local_context_init.context.items()}
            )
        else:
            local_context = GenieContext(
                {k: v for k, v in self.local_context_init.context.items()}
            )
        return self._interpreter.eval(
            code,
            self.context,
            local_context,
        )

    def update_from_context(self, context):
        """add new variables to the context"""
        self.context.update(context.context)

    def get_available_worksheets(self, context):
        """Get all available worksheets based on their predicates."""
        for ws in self.genie_worksheets:
            if ws.predicate:
                if eval_predicates(ws.predicate, None, self, context):
                    yield ws
            else:
                yield ws

    def get_available_dbs(self, context):
        """Get all available database models based on their predicates."""
        for db in self.genie_db_models:
            if db.predicate:
                if eval_predicates(db.predicate, None, self, context):
                    yield db
            else:
                yield db

    def get_all_variables(self):
        """Get all fields (variables) from all worksheets."""
        all_variables = []
        for ws in self.genie_worksheets:
            for field in get_genie_fields_from_ws(ws):
                all_variables.append(field.name)

        return all_variables


class GenieInterpreter:
    """Interpreter for executing Genie code.

    This class provides code execution capabilities within the Genie environment,
    handling variable resolution and context management.
    """

    def execute(self, code, global_context, local_context, sp=False):
        # There are some issues here. since there are no numbers now,
        # when we do courses_to_take = CoursesToTake(courses_0_details=course)
        # since courses_to_take is a field in main worksheet, the code gets modified to:
        # main.courses_to_take.value = CoursesToTake(courses_0_details=course)
        # One easy fix could be if you are setting a GenieWorksheet to a field, then
        # do not modify the code.

        # Another way is to have an, argument which mentions if the execution is from semantic parser
        # if it is, then do not modify the code.

        if not sp:
            # If the execution is for action then we replace the undefined variables
            code = replace_undefined_variables(code, local_context, global_context)
        try:
            try:
                exec(code, global_context.context, local_context.context)
            except NameError as e:
                local_context.set(e.name, None)
                # regex to catch the variable name. If the variable name is "user_task" then we want to find "user_task.value" as well until we hit a space.
                # This is just a hack ideally we should traverse the ast or at least use the tokenize module to find the variable name
                var_name = re.findall(rf"{e.name}\.\w+", code)
                if var_name:
                    code = code.replace(var_name[0], f"{e.name}")
                exec(code, global_context.context, local_context.context)
                local_context.delete(e.name)
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.error(f"Code: {code}")

    def eval(self, code, global_context, local_context):
        # perform rewrite to update any variables that is not in the local context
        # by using the variable resolver
        code = replace_undefined_variables(code, local_context, global_context).strip()
        try:
            return eval(code, global_context.context, local_context.context)
        except (NameError, AttributeError):
            return False


class GenieContext:
    """Context manager for Genie runtime.

    This class manages variable context and agent actions during runtime.

    Attributes:
        context (dict): The context dictionary.
        agent_acts: Current agent actions.
    """

    def __init__(self, context: dict = None):
        if context is None:
            context = {}
        self.context = context
        self.agent_acts = None
        self.reset_agent_acts()

    def reset_agent_acts(self):
        self.agent_acts = AgentActs({})

    def update(self, content: dict):
        """Update the context with new content.

        Args:
            content (dict): Dictionary of content to update with.
        """
        for key, value in content.items():
            if key != "answer" and key in self.context:
                if not isinstance(self.context[key], list):
                    if self.context[key] != value:
                        self.context[key] = [
                            self.context[key]
                        ]  # TODO: make the line below this else: if
                else:
                    if isinstance(value, list):
                        for v in value:
                            if v not in self.context[key]:
                                self.context[key].append(v)
                    else:
                        self.context[key].append(value)
            else:
                self.context[key] = value

    def get(self, key: str) -> Any:
        """Get a value from the context.

        Args:
            key (str): The key to get.

        Returns:
            Any: The value associated with the key.
        """
        return self.context[key]

    def set(self, key: str, value: Any):
        """Set a value in the context.

        Args:
            key (str): The key to set.
            value (Any): The value to set.
        """
        if key != "answer" and key in self.context:
            if not isinstance(self.context[key], list):
                self.context[key] = [self.context[key]]
            self.context[key].append(value)
        else:
            self.context[key] = value

    def delete(self, key: str):
        """Delete a key from the context.

        Args:
            key (str): The key to delete.
        """
        del self.context[key]


class TurnContext:
    """Context manager for dialogue turns.

    This class manages context for individual dialogue turns.

    Attributes:
        context (list[GenieContext]): List of contexts for each turn.
    """

    def __init__(self):
        self.context: list[GenieContext] = []

    def add_turn_context(self, context: GenieContext):
        """Add a new turn context.

        Args:
            context (GenieContext): The context to add for this turn.
        """
        self.context.append(deepcopy(context))


def get_genie_fields_from_ws(obj: GenieWorksheet) -> list[GenieField]:
    """Get all GenieField instances from a GenieWorksheet.

    Args:
        obj (GenieWorksheet): The worksheet to get fields from.

    Returns:
        list[GenieField]: List of GenieField instances.
    """
    fields = []
    for attr in obj._ordered_attributes:
        if not attr.startswith("_"):
            field = getattr(obj, attr)
            if isinstance(field, GenieField):
                fields.append(field)
    return fields


def execute_query(
    code: str, obj: GenieWorksheet, bot: GenieRuntime, local_context: GenieContext
) -> Any:
    """Execute a query in the given context.

    Args:
        code (str): The code to execute.
        obj (GenieWorksheet): The worksheet object.
        bot (GenieRuntime): The bot instance.
        local_context (GenieContext): The local context.

    Returns:
        Any: The result of the query execution.
    """
    # refactoring the developer written code
    code = modify_action_code(code, obj, bot, local_context)
    code_ = f"__return = {code}"
    local_context.context["__return"] = None

    bot.execute(code_, local_context)

    if "_obj" in local_context.context:
        del local_context.context["_obj"]

    result = local_context.context["__return"]

    del local_context.context["__return"]
    return result


def modify_action_code(code, obj, bot, local_context):
    # Pattern to match decorators and their arguments
    api_pattern = r"@(\w+)\((.*?)\)"
    api_matches = re.findall(api_pattern, code)

    inbuilt_pattern = r">(\w+)\((.*?)\)"
    inbuilt_matches = re.findall(inbuilt_pattern, code)

    def replace_sign(sign, matches, code):
        for func_name, args in matches:
            if (
                func_name not in bot.context.context
                and func_name not in local_context.context
            ):
                continue

            # Replace the decorator with the direct function call in the code
            code = re.sub(f"{sign}{func_name}", func_name, code)
        return code

    def replace_self(code):
        # Replace 'self.' with 'custom_obj.' to reference the custom object
        if isinstance(obj, GenieWorksheet):
            local_context.context["_obj"] = obj
        elif isinstance(obj, GenieField):
            local_context.context["_obj"] = obj.parent
        modified_args = code.replace("self.", "_obj" + ".")
        modified_args = re.sub(r"self$", "_obj", modified_args)
        modified_args = re.sub(r"self}", "_obj" + "}", modified_args)

        return modified_args

    code = replace_self(code)

    code = replace_sign("@", api_matches, code)
    code = replace_sign(">", inbuilt_matches, code)
    return code


def eval_predicates(
    predicates: list | str,
    obj: GenieField | GenieWorksheet,
    bot: GenieRuntime,
    local_context: GenieContext,
) -> bool:
    if predicates is None:
        return True
    if len(predicates) == 0:
        return True
    if isinstance(predicates, list):
        for predicate in predicates:
            if not parse_single_predicate(predicate, obj, bot, local_context):
                return False
    else:
        if not parse_single_predicate(predicates, obj, bot, local_context):
            return False
    return True


def parse_single_predicate(predicate: str, obj, bot, context) -> bool:
    if isinstance(predicate, bool):
        return predicate
    if predicate.upper() == "TRUE":
        return True
    elif predicate.upper() == "FALSE":
        return False
    elif predicate == "":
        return True

    code = modify_action_code(predicate, obj, bot, context)
    code = sanitize_dev_code(code, bot.get_all_variables()).strip()

    res: bool = bot.eval(code, context)

    if "_obj" in context.context:
        del context.context["_obj"]
    return res


def rewrite_action_code(code, builtin_funcs):
    class CallTransformer(ast.NodeTransformer):
        def __init__(self, builtin_funcs) -> None:
            super().__init__()
            self.builtins = builtin_funcs

        def visit_Call(self, node):
            # Process the node further before possibly wrapping it
            self.generic_visit(node)

            # Wrap the function call in a result.append if it's not a built-in function
            # Note: you'll need to determine if a function is built-in based on your criteria
            if isinstance(node.func, ast.Name) and node.func.id in self.builtins:
                append_call = ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="__return", ctx=ast.Load()),
                            attr="append",
                            ctx=ast.Load(),
                        ),
                        args=[node],
                        keywords=[],
                    )
                )
                return append_call
            return node

    # Parse the code into an AST
    tree = ast.parse(code)

    # Initialize the transformer and apply it
    transformer = CallTransformer(builtin_funcs=builtin_funcs)
    transformer.result_added = False
    transformed_tree = transformer.visit(tree)

    # Fix missing locations in the AST
    # Convert the AST back to code
    new_code = ast.unparse(ast.fix_missing_locations(transformed_tree))
    return new_code


def same_field(field1: GenieField, field2: GenieField):
    """Check if the values and confirmed status are the same for any two GenieField instances.

    Args:
        field1 (GenieField): The first field to compare.
        field2 (GenieField): The second field to compare.

    Returns:
        bool: True if the fields are the same, False otherwise.
    """

    return field1.value == field2.value and field1.confirmed == field2.confirmed


def same_worksheet(ws1: GenieWorksheet, ws2: GenieWorksheet):
    """Check if two GenieWorksheet instances are the same.

    Args:
        ws1 (GenieWorksheet): The first worksheet to compare.
        ws2 (GenieWorksheet): The second worksheet to compare.

    Returns:
        bool: True if the worksheets are the same, False otherwise.
    """
    # If the randomly generated id is different, then the worksheets are different
    if hasattr(ws1, "random_id") and hasattr(ws2, "random_id"):
        if ws1.random_id != ws2.random_id:
            return False

    # Check if the fields in both worksheets are the same starting from WS1
    for field in get_genie_fields_from_ws(ws1):
        for field2 in get_genie_fields_from_ws(ws2):
            if field.name == field2.name:
                if type(field.value) is not type(field2.value):
                    return False
                if isinstance(field.value, GenieWorksheet) and isinstance(
                    field2.value, GenieWorksheet
                ):
                    # Recursively check if the worksheets are the same
                    # if the value of the current field is a worksheet
                    if not same_worksheet(field.value, field2.value):
                        return False
                else:
                    if not same_field(field, field2):
                        return False

    # Check if the fields in both worksheets are the same starting from WS2
    for field in get_genie_fields_from_ws(ws2):
        for field2 in get_genie_fields_from_ws(ws1):
            if field.name == field2.name:
                if isinstance(field.value, GenieWorksheet):
                    if not same_worksheet(field.value, field2.value):
                        return False
                else:
                    if not same_field(field, field2):
                        return False

    return True


def count_number_of_vars(context: dict):
    """Count the number of variables of the same type in the context.

    Args:
        context (dict): The context to count variables in.

    Returns:
        dict: A dictionary with variable names as keys and their counts as values."""
    var_counters = {}
    for key, value in context.items():
        if isinstance(value, Answer):
            continue
        if isinstance(value, GenieWorksheet):
            var_name = generate_var_name(value.__class__.__name__)
            if var_name not in var_counters:
                var_counters[var_name] = -1
            var_counters[var_name] += 1

    return var_counters


def genie_deepcopy(context):
    """Special deepcopy function for Genie context."""
    new_context = {}
    for key, value in context.items():
        if key == "__builtins__":
            continue
        if isinstance(value, GenieWorksheet):
            new_context[key] = deepcopy(value)
        elif isinstance(value, GenieField):
            new_context[key] = deepcopy(value)
        else:
            new_context[key] = value
    return new_context


def get_field_variable_name(obj: GenieWorksheet, context: GenieContext):
    """Get the variable name of a field in a worksheet.

    Args:
        obj (GenieWorksheet): The worksheet object.
        context (GenieContext): The context to search in.

    Returns:
        str: The variable name of the field.
    """
    for name, value in context.context.items():
        if not inspect.isclass(value) and isinstance(value, GenieWorksheet):
            for field in get_genie_fields_from_ws(value):
                if field == obj:
                    return name + "." + field.name

    return obj


def collect_all_parents(context: GenieContext):
    """Collect all parent references for GenieField instances in the context.

    Args:
        context (GenieContext): The context to collect parents from.
    """
    for key, value in context.context.items():
        if isinstance(value, GenieWorksheet):
            for field in get_genie_fields_from_ws(value):
                if isinstance(field, GenieField):
                    field.parent = value


def find_all_variables_matching_name(field_name: str, context: GenieContext):
    """Go through all the variables in the context recursively and return the variables that match the field_name"""
    variables = []

    def find_matching_variables(obj, field_name, key):
        for field in get_genie_fields_from_ws(obj):
            if field.name == field_name:
                variables.append(key + "." + field_name)
            # if isinstance(field.value, GenieWorksheet):
            # find_matching_variables(field.value, field_name, key + "." + field.name)

    for key, value in context.context.items():
        if isinstance(value, GenieWorksheet):
            find_matching_variables(value, field_name, key)

    return variables


def replace_undefined_variables(
    code: str, local_context: GenieContext, global_context: GenieContext
):
    """Replace undefined variables in the code with their corresponding values from the context."""

    class ReplaceVariables(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in local_context.context:
                if isinstance(local_context.context[node.id], GenieField):
                    if node.id.endswith(".value"):
                        name = node.id
                    else:
                        name = node.id + ".value"
                    return ast.copy_location(
                        ast.Name(
                            id=name,
                            ctx=node.ctx,
                        ),
                        node,
                    )
            elif node.id in global_context.context:
                if isinstance(global_context.context[node.id], GenieField):
                    if node.id.endswith(".value"):
                        name = node.id
                    else:
                        name = node.id + ".value"
                    return ast.copy_location(
                        ast.Name(
                            id=name,
                            ctx=node.ctx,
                        ),
                        node,
                    )
            else:
                replacement_var = variable_resolver(
                    node.id, global_context, local_context
                )
                if replacement_var:
                    if replacement_var.endswith(".value"):
                        name = replacement_var
                    else:
                        name = replacement_var + ".value"
                    return ast.copy_location(
                        ast.Name(
                            id=name,
                            ctx=node.ctx,
                        ),
                        node,
                    )
            return node

    # Parse the code into an AST
    tree = ast.parse(code)

    # Modify the AST
    tree = ReplaceVariables().visit(tree)

    # Convert back to source code
    code = ast.unparse(tree)
    code = code.replace(".value.value", ".value")
    return code


def variable_resolver(var_name, global_context, local_context):
    """We need to resolve the variable name since they are stored as <obj_name>.<field_name> in the context
    and the user only provides the field name. We also need to keep track of the latest object of a worksheet
    so that we can resolve the variable name correctly.
    """
    if var_name in local_context.context:
        return var_name
    elif var_name in global_context.context:
        return var_name
    else:
        candidates = find_all_variables_matching_name(var_name, local_context)

        if len(candidates) == 0:
            candidates = find_all_variables_matching_name(var_name, global_context)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            logger.info(f"Could not resolve the variable name {var_name}.")
            logger.info(f"Found multiple candidates: {candidates}")
            return candidates[0]


def select_variable_from_list(variables, value):
    for var in variables:
        if same_worksheet(var, value):
            return generate_var_name(value.__class__.__name__)

    return None


def get_variable_name(obj: GenieWorksheet, context: GenieContext):
    """Get the variable name of a worksheet in the context.

    Args:
        obj (GenieWorksheet): The worksheet object.
        context (GenieContext): The context to search in.

    Returns:
        str: The variable name of the worksheet.
    """
    potential_objs = []
    if isinstance(obj, GenieWorksheet):
        for name, value in context.context.items():
            if not inspect.isclass(value) and isinstance(value, GenieWorksheet):
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


### INBUILT FUNCTIONS ###


def propose(worksheet: GenieWorksheet, params: dict) -> ProposeAgentAct:
    """Create a proposal action.

    Args:
        worksheet (GenieWorksheet): The worksheet to propose values for.
        params (dict): The parameters to propose.

    Returns:
        ProposeAgentAct: The created proposal action.
    """
    return ProposeAgentAct(worksheet(**params), params)


def say(message: str) -> ReportAgentAct:
    """Create a message report action.

    Args:
        message (str): The message to report.

    Returns:
        ReportAgentAct: The created report action.
    """
    return ReportAgentAct(None, message)


def generate_clarification(worksheet: GenieWorksheet, field: str) -> str:
    """Generate clarification text for a field.

    Args:
        worksheet (GenieWorksheet): The worksheet containing the field.
        field (str): The name of the field.

    Returns:
        str: The generated clarification text.
    """
    for f in get_genie_fields_from_ws(worksheet):
        if f.name == field:
            if inspect.isclass(f.slottype) and issubclass(f.slottype, Enum):
                options = [x.name for x in list(f.slottype.__members__.values())]
                options = ", ".join(options)
                option_desc = f.description + f" Options are: {options}"
                return option_desc
            return f.description

    return ""


def answer_clarification_question(
    worksheet: GenieField, field: GenieField, context: GenieContext
) -> ReportAgentAct:
    """Create a clarification answer action.

    Args:
        worksheet (GenieField): The worksheet field.
        field (GenieField): The field to clarify.
        context (GenieContext): The context.

    Returns:
        ReportAgentAct: The created clarification report action.
    """
    ws = context.context[worksheet.value]
    return ReportAgentAct(
        f"AskClarification({worksheet.value}, {field.value})",
        generate_clarification(ws, field.value),
    )


def confirm(value: Any) -> GenieValue:
    """Create a confirmed value.

    Args:
        value (Any): The value to confirm.

    Returns:
        GenieValue: The confirmed value instance.
    """
    if isinstance(value, GenieValue):
        return value.confirm()
    return GenieValue(value).confirm()


### AGENT ACTS ###


class AgentAct:
    """Base class for agent actions.

    This class serves as the foundation for different types of agent actions
    in the system.
    """


class ReportAgentAct(AgentAct):
    """Action for reporting query results or messages.

    This class handles reporting of query results and system messages.

    Attributes:
        query (GenieField): The query being reported.
        message: The message or result to report.
        query_var_name: Variable name for the query.
        message_var_name: Variable name for the message.
    """

    def __init__(
        self,
        query: GenieField,
        message: Any,
        query_var_name=None,
        message_var_name=None,
    ):
        self.query = query
        self.message = message
        self.query_var_name = query_var_name
        self.message_var_name = message_var_name

    def __repr__(self):
        if self.query_var_name:
            query_var_name = self.query_var_name
        else:
            query_var_name = self.query

        if self.message_var_name:
            message_var_name = self.message_var_name
        else:
            message_var_name = self.message
        return f"Report({query_var_name}, {message_var_name})"

    def __eq__(self, other):
        if isinstance(other, ReportAgentAct):
            if self.query == other.query and self.message == other.message:
                return True
        return False


class AskAgentAct(AgentAct):
    """Action for requesting information from users.

    This class handles user information requests.

    Attributes:
        ws (GenieWorksheet): The worksheet context.
        field (GenieField): The field to ask about.
        ws_name: Worksheet name override.
    """

    def __init__(self, ws: GenieWorksheet, field: GenieField, ws_name=None):
        self.ws = ws
        self.field = field
        self.ws_name = ws_name

    def __repr__(self):
        description = None
        if inspect.isclass(self.field.slottype):
            if issubclass(self.field.slottype, Enum):
                options = [
                    x.name for x in list(self.field.slottype.__members__.values())
                ]
                options = ", ".join(options)
                description = self.field.description + f" Options are: {options}"

        if description is None and self.field.description is not None:
            description = self.field.description

        if self.ws_name:
            return f"AskField({self.ws_name}, {self.field.name}, {description})"
        return (
            f"AskField({self.ws.__class__.__name__}, {self.field.name}, {description})"
        )


class ProposeAgentAct(AgentAct):
    """Action for proposing worksheet values.

    This class handles proposals for worksheet field values.

    Attributes:
        ws (GenieWorksheet): The worksheet context.
        params (dict): Proposed parameters.
        ws_name: Worksheet name override.
    """

    def __init__(self, ws: GenieWorksheet, params: dict, ws_name=None):
        self.ws = ws
        self.params = params
        self.ws_name = ws_name

    def __repr__(self):
        if self.ws_name:
            return f"ProposeAgentAct({self.ws_name}, {self.params})"
        return f"ProposeAgentAct({self.ws.__class__.__name__}, {self.params})"


class AskForConfirmationAgentAct(AgentAct):
    """Action for requesting user confirmation.

    This class handles confirmation requests for field values.

    Attributes:
        ws (GenieWorksheet): The worksheet context.
        field (GenieField): The field to confirm.
        ws_name: Worksheet name override.
        field_name: Field name override.
        value: Value to confirm.
    """

    def __init__(
        self, ws: "GenieWorksheet", field: "GenieField", ws_name=None, field_name=None
    ):
        self.ws = ws
        self.field = field
        self.ws_name = ws_name
        self.field_name = field_name
        self.value = None

    def __repr__(self):
        if self.ws_name:
            ws_name = self.ws_name
        else:
            ws_name = self.ws.__class__.__name__

        if self.field_name:
            field_name = self.field_name
        else:
            field_name = self.field.name

        return f"AskForFieldConfirmation({ws_name}, {field_name})"


class AgentActs:
    """Container for managing multiple agent actions.

    This class manages collections of agent actions, handling action ordering
    and compatibility.

    Attributes:
        args: Arguments for action management.
        actions (list): List of agent actions.
    """

    def __init__(self, args):
        self.args = args
        self.actions = []

    def add(self, action):
        self._add(action)

    def _add(self, action):
        if self.should_add(action):
            self.actions.append(action)

    def should_add(self, incoming_action):
        """There can be multiple ReportActs, and (multiple propose acts or one ask acts or one confirmation act) but only one of each type of act"""
        acts_to_action = {}
        for action in self.actions:
            if action.__class__.__name__ in acts_to_action:
                acts_to_action[action.__class__.__name__].append(action)
            else:
                acts_to_action[action.__class__.__name__] = [action]

        # Check if the incoming action is a ReportAct, if it is then check if there is already a ReportAct with the same query
        if incoming_action.__class__.__name__ == "ReportAgentAct":
            for action in acts_to_action.get("ReportAgentAct", []):
                if (
                    action.query == incoming_action.query
                    and action.message == incoming_action.message
                ):
                    return False
            return True
        # Check if the incoming action is a ProposeAct, if it is then check if there is already a ProposeAct with the same query
        # or AskAgentAct or AskForConfirmationAct are present
        elif incoming_action.__class__.__name__ == "ProposeAgentAct":
            if (
                "AskAgentAct" in acts_to_action
                or "AskForConfirmationAgentAct" in acts_to_action
            ):
                return False
            for action in acts_to_action.get("ProposeAgentAct", []):
                if action.params == incoming_action.params and same_worksheet(
                    action.ws, incoming_action.ws
                ):
                    return False
            return True
        # Check if the incoming action is a AskAgentAct, if other AskAgentAct or ProposeAgentAct or AskForConfirmationAgentAct are present
        elif incoming_action.__class__.__name__ == "AskAgentAct":
            if (
                "ProposeAgentAct" in acts_to_action
                or "AskAgentAct" in acts_to_action
                or "AskForConfirmationAgentAct" in acts_to_action
            ):
                return False
            return True
        # Check if the incoming action is a AskForConfirmationAct, if other AskAgentAct or ProposeAgentAct or AskForConfirmationAgentAct are present
        elif incoming_action.__class__.__name__ == "AskForConfirmationAgentAct":
            if (
                "ProposeAgentAct" in acts_to_action
                or "AskAgentAct" in acts_to_action
                or "AskForConfirmationAgentAct" in acts_to_action
            ):
                return False
            return True

        # for action in self.actions:
        #     if isinstance(action, ReportAgentAct) or isinstance(action, ReportAgentAct):
        #         if action == incoming_action:
        #             return True
        #     else:
        #         return True

        # return False

    def extend(self, actions):
        for action in actions:
            self._add(action)

    def __iter__(self):
        return iter(self.actions)

    def __next__(self):
        return next(self.actions)

    def can_have_other_acts(self):
        acts_to_action = {}
        for action in self.actions:
            if action.__class__.__name__ in acts_to_action:
                acts_to_action[action.__class__.__name__].append(action)
            else:
                acts_to_action[action.__class__.__name__] = [action]

        if (
            "ProposeAgentAct" in acts_to_action
            or "AskAgentAct" in acts_to_action
            or "AskForConfirmationAgentAct" in acts_to_action
        ):
            return False
        return True


def sanitize_dev_code(code: str, all_variables: list[str]):
    """Sanitize the developer's code to ensure it doesn't contain any undefined variables."""
    lexer = PythonLexer()
    tokens = lexer.get_tokens(code)
    new_tokens_list = []
    for token in tokens:
        if token[0] == Token.Name and token[1] in all_variables:
            new_tokens_list.append((Token.Name, token[1] + ".value"))
        else:
            new_tokens_list.append(token)

    new_code = tokenize.untokenize(new_tokens_list)
    return new_code


def any_open_empty_ws(turn_context: GenieContext, global_context: GenieContext):
    """Checks all the worksheets in the context. If there is any worksheet that is available but all the fields are None, then return True
    else return False
    """
    for key, value in turn_context.context.items():
        if isinstance(value, GenieWorksheet):
            all_none = True
            for field in get_genie_fields_from_ws(value):
                if field.value is not None:
                    all_none = False
                    break

            if all_none:
                return True

    for key, value in global_context.context.items():
        if isinstance(value, GenieWorksheet):
            all_none = True
            for field in get_genie_fields_from_ws(value):
                if field.value is not None:
                    all_none = False
                    break

            if all_none:
                return True

    return False


def find_list_variable(val, context):
    """Find the variable name which is a list and the index of the required value in the context."""
    for key, value in context.context.items():
        if isinstance(value, list):
            for idx, v in enumerate(value):
                if v == val:
                    return key, str(idx)
    return None, None

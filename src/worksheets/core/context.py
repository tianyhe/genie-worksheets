from copy import deepcopy
from typing import Any

from worksheets.core.agent_acts import AgentActs


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
            if (
                hasattr(value, "action_performed")
                and value.is_complete(self.bot, self)
                and value.action_performed
                and hasattr(value, "backend_api")
            ):
                self.context[key] = value.result  # set the result to the context
                self.context[f"___{key}"] = value  # set the complete api to the context
            elif not isinstance(self.context[key], list):
                self.context[key] = [self.context[key]]
            else:
                self.context[key] = value
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

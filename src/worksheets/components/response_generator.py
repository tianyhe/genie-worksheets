import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from loguru import logger

from worksheets.core.dialogue import CurrentDialogueTurn
from worksheets.llm.basic import llm_generate
from worksheets.utils.annotation import get_agent_action_schemas, get_context_schema


class ResponsePromptManager:
    """Manages the preparation and handling of prompts for response generation.

    This class is responsible for gathering and organizing all necessary information
    for generating appropriate responses in the dialogue system.

    Attributes:
        runtime (GenieRuntime): The runtime runtime instance containing configuration and models.
    """

    def __init__(self, runtime, agent):
        """Initialize the ResponsePromptManager.

        Args:
            runtime (GenieRuntime): The runtime runtime instance.
            agent (Agent): The agent instance.
        """
        self.runtime = runtime
        self.agent = agent

    def prepare_prompt_inputs(
        self,
        current_dlg_turn: CurrentDialogueTurn,
        dlg_history: List[CurrentDialogueTurn],
        state_schema: str,
        agent_acts: List[Dict],
        agent_utterance: str,
    ) -> Dict[str, Any]:
        """Prepare all necessary inputs for the response generation prompt.

        Args:
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
            state_schema (str): The current state schema.
            agent_acts (List[Dict]): The agent actions.
            agent_utterance (str): The previous agent utterance.

        Returns:
            Dict[str, Any]: The prepared prompt inputs.
        """
        current_date = datetime.datetime.now()

        return {
            "prior_agent_utterance": agent_utterance,
            "user_utterance": current_dlg_turn.user_utterance,
            "dlg_history": dlg_history,
            "date": current_date.strftime("%Y-%m-%d"),
            "day": current_date.strftime("%A"),
            "state": state_schema,
            "agent_acts": agent_acts,
            "description": self.agent.description,
            "parsing": current_dlg_turn.user_target,
        }

    def get_model_args(self) -> Dict[str, Any]:
        """Get the model configuration arguments.

        Returns:
            Dict[str, Any]: The model configuration arguments.
        """
        return self.agent.config.response_generator.model_dump()


class ResponseSupervisor:
    """Supervises and validates generated responses.

    This class is responsible for checking the quality and appropriateness
    of generated responses, providing feedback and validation.
    """

    @staticmethod
    async def validate_response(
        agent_response: str,
        prompt_inputs: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Validate a generated response and provide feedback.

        Args:
            agent_response (str): The generated response to validate.
            prompt_inputs (Dict[str, Any]): The inputs used to generate the response.

        Returns:
            Tuple[bool, Optional[str]]: A tuple containing (is_valid, feedback).
        """
        prompt_inputs["agent_response"] = agent_response

        validation_output = await llm_generate(
            "supervisor_response_generator.prompt",
            prompt_inputs=prompt_inputs,
            model_name="gpt-4o",
        )

        return ResponseSupervisor._parse_validation_output(validation_output)

    @staticmethod
    def _parse_validation_output(validation_output: str) -> Tuple[bool, Optional[str]]:
        """Parse the validation output from the supervisor.

        Args:
            validation_output (str): The raw validation output.

        Returns:
            Tuple[bool, Optional[str]]: A tuple containing (is_valid, feedback).
        """
        bs = BeautifulSoup(validation_output, "html.parser")
        answer = bs.find("answer")
        feedback = bs.find("reasoning")

        is_valid = False
        feedback_text = None

        if answer is not None:
            answer_text = answer.text.lower().strip()
            is_valid = answer_text == "true"

        if feedback is not None:
            feedback_text = feedback.text.lower().strip()

        return is_valid, feedback_text


class ResponseGenerator:
    """Main class for generating dialogue system responses.

    This class orchestrates the process of generating appropriate responses
    based on the current dialogue state, history, and system actions.

    Attributes:
        runtime (GenieRuntime): The runtime instance.
        prompt_manager (ResponsePromptManager): Manager for prompt preparation.
        supervisor (ResponseSupervisor): Supervisor for response validation.
    """

    def __init__(self, runtime, agent):
        """Initialize the ResponseGenerator.

        Args:
            runtime (GenieRuntime): The runtime runtime instance.
            validate_response (bool): Whether to validate the response.
        """
        self.runtime = runtime
        self.agent = agent
        self.prompt_manager = ResponsePromptManager(runtime, agent)
        self.supervisor = ResponseSupervisor()
        self.validate_response = agent.config.validate_response

    async def generate_response(
        self,
        current_dlg_turn: CurrentDialogueTurn,
        dlg_history: List[CurrentDialogueTurn],
    ) -> None:
        """Generate a response for the current dialogue turn.

        Args:
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
        """
        # Gather context and state information
        state_schema = self._get_state_schema()
        agent_acts = self._get_agent_acts(current_dlg_turn)
        agent_utterance = self._get_previous_utterance(dlg_history)

        # Prepare prompt inputs
        prompt_inputs = self.prompt_manager.prepare_prompt_inputs(
            current_dlg_turn,
            dlg_history,
            state_schema,
            agent_acts,
            agent_utterance,
        )

        # Get model configuration
        model_args = self.prompt_manager.get_model_args()

        # Generate response
        response = await self._generate_response_with_model(prompt_inputs, model_args)

        # Update dialogue turn
        current_dlg_turn.system_response = response

        # Optionally validate response
        if self.validate_response:
            await self._validate_response(response, prompt_inputs)

    def _get_state_schema(self) -> str:
        """Get the current state schema.

        Returns:
            str: The current state schema.
        """
        return get_context_schema(self.runtime.context, response_generator=True)

    def _get_agent_acts(self, current_dlg_turn: CurrentDialogueTurn) -> List[Dict]:
        """Get the agent actions for the current turn.

        Args:
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.

        Returns:
            List[Dict]: The agent actions.
        """
        if current_dlg_turn.system_action is None:
            return []
        return get_agent_action_schemas(
            current_dlg_turn.system_action, self.runtime.context
        )

    def _get_previous_utterance(self, dlg_history: List[CurrentDialogueTurn]) -> str:
        """Get the previous agent utterance.

        Args:
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.

        Returns:
            str: The previous agent utterance.
        """
        return (
            dlg_history[-1].system_response
            if dlg_history
            else self.agent.starting_prompt
        )

    async def _generate_response_with_model(
        self,
        prompt_inputs: Dict[str, Any],
        model_args: Dict[str, Any],
    ) -> str:
        """Generate a response using the language model.

        Args:
            prompt_inputs (Dict[str, Any]): The prepared prompt inputs.
            model_args (Dict[str, Any]): The model configuration arguments.

        Returns:
            str: The generated response.
        """
        return await llm_generate(
            "response_generator.prompt",
            prompt_inputs=prompt_inputs,
            prompt_dir=self.agent.prompt_dir,
            **model_args,
        )

    async def _validate_response(
        self,
        response: str,
        prompt_inputs: Dict[str, Any],
    ) -> None:
        """Validate the generated response.

        Args:
            response (str): The generated response.
            prompt_inputs (Dict[str, Any]): The prompt inputs used for generation.
        """
        is_valid, feedback = await self.supervisor.validate_response(
            response, prompt_inputs
        )

        if not is_valid:
            logger.warning(f"Response validation failed: {feedback}")
            # TODO: Implement response regeneration or fallback strategy

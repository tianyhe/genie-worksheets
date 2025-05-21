from typing import Optional, Type

from worksheets.agent.config import Config
from worksheets.components.agent_policy import AgentPolicyManager
from worksheets.components.response_generator import ResponseGenerator
from worksheets.components.semantic_parser import GenieParser
from worksheets.core import GenieContext, GenieRuntime
from worksheets.core.dialogue import CurrentDialogueTurn
from worksheets.knowledge.base import BaseKnowledgeBase
from worksheets.knowledge.parser import BaseParser
from worksheets.specification.from_spreadsheet import gsheet_to_genie


class Agent:
    """Agent setting for GenieWorksheets"""

    def __init__(
        self,
        # name of the agent
        botname: str,
        # description of the agent. This is used for generating response
        description: str,
        # directory where the prompts are stored
        prompt_dir: str,
        # starting prompt for the agent to ask the user
        starting_prompt: str,
        # arguments to pass to the agent for configuration
        config: Config,
        # list of functions that are available to the agent for execution
        api: list,
        # knowledge configuration for the agent to run queries and respond to the user
        knowledge_base: BaseKnowledgeBase,
        # semantic parser for knowledge queries
        knowledge_parser: BaseParser,
        # contextual semantic parser
        genie_parser_class: Optional[Type[GenieParser]] = GenieParser,
        # agent policy manager
        genie_agent_policy_class: Optional[
            Type[AgentPolicyManager]
        ] = AgentPolicyManager,
        # response generator
        genie_response_generator_class: Optional[
            Type[ResponseGenerator]
        ] = ResponseGenerator,
    ):
        self.botname = botname
        self.description = description
        self.prompt_dir = prompt_dir
        self.starting_prompt = starting_prompt
        self.config = config
        self.api = api
        self.knowledge_base = knowledge_base
        self.knowledge_parser = knowledge_parser

        self.runtime = None
        self.dlg_history = []
        self.genie_parser_class = genie_parser_class
        self.genie_agent_policy_class = genie_agent_policy_class
        self.genie_response_generator_class = genie_response_generator_class

    def load_runtime_from_gsheet(self, gsheet_id: str):
        """Load the agent configuration from the google sheet.

        Args:
            gsheet_id (str): The ID of the Google Sheet.

        Returns:
            GenieRuntime: An instance of GenieRuntime configured with the loaded data.
        """

        # Load Genie worksheets, databases, and types from the Google Sheet
        genie_worsheets, genie_dbs, genie_types = gsheet_to_genie(gsheet_id)

        # Create a SUQL runner if knowledge_base is provided. Suql runner is used by the
        # GenieRuntime to run queries against the knowledge base.
        if self.knowledge_base:

            def suql_runner(query, *args, **kwargs):
                return self.knowledge_base.run(query, *args, **kwargs)

        else:
            suql_runner = None

        # Create an instance of GenieRuntime with the loaded configuration
        runtime = GenieRuntime(
            config=self.config,
            api=self.api,
            suql_runner=suql_runner,
            agent=self,
        )

        # Add worksheets, databases, and types to the GenieRuntime instance
        for worksheet in genie_worsheets:
            runtime.add_worksheet(worksheet)

        for db in genie_dbs:
            runtime.add_db_model(db)

        for genie_type in genie_types:
            runtime.add_worksheet(genie_type)

        self.runtime = runtime

        self._initialize_modules()

    def _initialize_modules(self):
        self.genie_parser = self.genie_parser_class(
            self.runtime, self.knowledge_parser, self
        )
        self.genie_agent_policy_manager = self.genie_agent_policy_class(self.runtime)
        self.genie_response_generator = self.genie_response_generator_class(
            self.runtime, self
        )

    async def generate_next_turn(self, user_utterance: str):
        """Generate the next turn in the dialogue based on the user's utterance.

        Args:
            user_utterance (str): The user's input.
            bot (Agent): The bot instance handling the dialogue.
        """
        # instantiate a new dialogue turn
        current_dlg_turn = CurrentDialogueTurn()
        current_dlg_turn.user_utterance = user_utterance

        # initialize contexts
        current_dlg_turn.context = GenieContext()
        current_dlg_turn.global_context = GenieContext()

        # reset the agent acts
        self.runtime.context.reset_agent_acts()

        # process the dialogue turn to GenieWorksheets
        await self.genie_parser.parse(current_dlg_turn, self.dlg_history)

        # run the agent policy if user_target is not None
        if current_dlg_turn.user_target is not None:
            self.genie_agent_policy_manager.run_policy(current_dlg_turn)

        # generate a response based on the agent policy
        await self.genie_response_generator.generate_response(
            current_dlg_turn, self.dlg_history
        )
        self.dlg_history.append(current_dlg_turn)

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional

from chainlite import write_prompt_logs_to_file
from loguru import logger
from suql.agent import DialogueTurn as SUQLDialogueTurn

from worksheets.agent.config import AzureModelConfig, OpenAIModelConfig
from worksheets.core.dialogue import CurrentDialogueTurn
from worksheets.core.runtime import GenieRuntime
from worksheets.core.worksheet import Answer
from worksheets.knowledge.base import SUQLKnowledgeBase
from worksheets.kraken.agent import KrakenParser
from worksheets.kraken.utils import DialogueTurn
from worksheets.llm import llm_generate
from worksheets.utils.llm import extract_code_block_from_output

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


class BaseParser(ABC):
    """Base class for parsers"""

    @abstractmethod
    def parse(
        self,
        query: str,
        dlg_history: List[CurrentDialogueTurn],
        *args,
        **kwargs,
    ):
        """Parse the query and return the output."""
        pass


class BaseSUQLParser(BaseParser):
    """Base class for SUQL parsers"""

    def __init__(self, model_config: AzureModelConfig | OpenAIModelConfig, **kwargs):
        super().__init__(**kwargs)

        # Name of the LLM model to use for the queries
        self.model_config = model_config

    async def parse(
        self,
        query: str,
        dlg_history: List[CurrentDialogueTurn],
        *args,
        **kwargs,
    ):
        raise NotImplementedError

    def convert_dlg_turn_to_suql_dlg_turn(self, dlg_history, db_results):
        # Convert the dialog history to the expected format for SUQL
        suql_dlg_history = []
        for i, turn in enumerate(dlg_history):
            user_target = turn.user_target_suql
            agent_utterance = turn.system_response
            user_utterance = turn.user_utterance

            if db_results is None:
                db_result = [
                    obj.result
                    for obj in turn.context.context.values()
                    if isinstance(obj, Answer)
                    and obj.query.value == turn.user_target_suql
                ]
            else:
                db_result = db_results[i]

            suql_dlg_history.append(
                SUQLDialogueTurn(
                    user_utterance=user_utterance,
                    db_results=db_result,
                    user_target=user_target,
                    agent_utterance=agent_utterance,
                )
            )

        db_result = None
        return suql_dlg_history, db_result, False


class SUQLParser(BaseSUQLParser):
    """Parser for SUQL queries"""

    def __init__(self, model_config: AzureModelConfig | OpenAIModelConfig, **kwargs):
        super().__init__(model_config=model_config, **kwargs)

        # Selector for the prompt to use for the queries
        self.prompt_selector = kwargs.get("prompt_selector", None)

    async def parse(
        self,
        query: str,
        dlg_history: List[CurrentDialogueTurn],
        bot: GenieRuntime,
        db_results: List[str] | None = None,
    ):
        """
        A SUQL conversational semantic parser, with a pre-set prompt file.
        The function convets the List[CurrentDialogueTurn] to the expected format
        in SUQL (suql.agent.DialogueTurn) and calls the prompt file.

        # Parameters:

        `dlg_history` (List[CurrentDialogueTurn]): a list of past dialog turns.

        `query` (str): the current query to be parsed.

        # Returns:

        `parsed_output` (str): a parsed SUQL output
        """

        suql_dlg_history = self.convert_dlg_turn_to_suql_dlg_turn(
            dlg_history, db_results
        )

        # Use the prompt selector if available
        if self.prompt_selector:
            prompt_file = await self.prompt_selector(bot, dlg_history, query)
        else:
            prompt_file = "suql_parser.prompt"

        # Generate the SUQL output
        parsed_output = await llm_generate(
            prompt_file,
            prompt_inputs={
                "dlg": suql_dlg_history,
                "query": query,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "day": datetime.now().strftime("%A"),
                "day_tmr": (datetime.now() + timedelta(days=1)).strftime("%A"),
            },
            prompt_dir=bot.prompt_dir,
            model_name=self.model_config.model_name,
            api_key=self.model_config.api_key,
            api_version=self.model_config.api_version,
            api_base=self.model_config.api_base,
            temperature=0.0,
        )

        db_result = None
        return (
            extract_code_block_from_output(parsed_output, lang="sql"),
            db_result,
            False,
        )


class SUQLReActParser(BaseSUQLParser):
    """ReAct Parser for SUQL queries"""

    def __init__(
        self,
        model_config: AzureModelConfig | OpenAIModelConfig,
        example_path: str,
        instruction_path: str,
        table_schema_path: str,
        knowledge: SUQLKnowledgeBase,
        examples: Optional[List[str]] = None,
        instructions: Optional[List[str]] = None,
        table_schema: Optional[str] = None,
        conversation_history: Optional[List[DialogueTurn]] = None,
        **kwargs,
    ):
        super().__init__(model_config=model_config, **kwargs)

        self.example_path = example_path
        self.instruction_path = instruction_path
        self.table_schema_path = table_schema_path
        self.knowledge = knowledge
        self.examples = examples
        self.instructions = instructions
        self.table_schema = table_schema
        self.conversation_history = conversation_history

        if self.examples is None:
            self.examples = []
            with open(self.example_path, "r") as f:
                text = f.read()

            for example in text.split("--"):
                if example.strip():
                    self.examples.append(example.strip())

        if self.instructions is None:
            with open(self.instruction_path, "r") as f:
                self.instructions = f.readlines()

        if self.table_schema is None:
            with open(self.table_schema_path, "r") as f:
                self.table_schema = f.read()

    async def parse(
        self,
        query: str,
        dlg_history: List[CurrentDialogueTurn],
        runtime: GenieRuntime,
        db_results: List[str] | None = None,
    ):
        suql_dlg_history = self.convert_dlg_turn_to_suql_dlg_turn(
            dlg_history, db_results
        )

        self.conversation_history = suql_dlg_history

        output = await self.anext_turn(
            query,
            update_conversation_history=False,
            table_w_ids=self.knowledge.tables_with_primary_keys,
            database_name=self.knowledge.database_name,
            embedding_server_address=self.knowledge.embedding_server_address,
            source_file_mapping=self.knowledge.source_file_mapping,
        )

        # TODO: KeyError: 'final_sql'
        # happens when the action_counter limit is met without a final SQL being generated
        logger.info(f"SUQL output: {output}")
        try:
            final_output = output["final_sql"].sql
            final_result = output["final_sql"].execution_result
        except Exception as e:
            logger.error(f"Error in parsing output: {e}")
            final_output = None
            final_result = None
        return final_output, final_result, True

    async def anext_turn(
        self,
        user_input: str,
        update_conversation_history: bool = False,
        table_w_ids: dict = None,
        database_name: str = None,
        embedding_server_address: str = None,
        source_file_mapping: dict = None,
    ):
        try:
            parser = KrakenParser()
            parser.initialize(
                engine=self.model_config.model_name,
                table_w_ids=table_w_ids,
                database_name=database_name,
                suql_model_name=self.knowledge.model_config.model_name,
                suql_api_base=self.knowledge.model_config.azure_endpoint,
                suql_api_version=self.knowledge.model_config.api_version,
                embedding_server_address=embedding_server_address,
                source_file_mapping=source_file_mapping,
                domain_instructions=self.instructions,
                examples=self.examples,
                table_schema=self.table_schema,
            )

            output = await parser.arun(
                {
                    "question": user_input,
                    "conversation_history": self.conversation_history,
                }
            )
        finally:
            write_prompt_logs_to_file(append=True, include_timestamp=True)

        if update_conversation_history:
            self.update_turn(self.conversation_history, output, response=None)

        return output

    def update_turn(self, conversation_history, output, response):
        turn = DialogueTurn(
            user_utterance=output["question"],
            agent_utterance=response,
            user_target=output["final_sql"].sql,
            db_results=output["final_sql"].execution_result,
        )

        conversation_history.append(turn)

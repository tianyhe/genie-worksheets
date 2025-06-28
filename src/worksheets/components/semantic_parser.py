import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sql_metadata import Parser
from suql.sql_free_text_support.execute_free_text_sql import _check_required_params

from worksheets.components.rewriter import rewrite_code_to_extract_funcs
from worksheets.core.dialogue import CurrentDialogueTurn
from worksheets.core.runtime import GenieRuntime
from worksheets.llm.basic import llm_generate
from worksheets.utils.annotation import prepare_semantic_parser_input
from worksheets.utils.field import get_genie_fields_from_ws
from worksheets.utils.llm import extract_code_block_from_output
from worksheets.utils.worksheet import count_worksheet_variables


class ContextualSemanticParser:
    """A class responsible for generating formal code representations from natural language using LLM.

    This class handles the contextual parsing of user utterances into executable code,
    taking into account dialogue history, available APIs, and system state.

    Attributes:
        runtime (GenieRuntime): The runtime instance for configuration and model access.
        agent (Agent): The agent instance for configuration and model access.
    """

    def __init__(self, runtime: GenieRuntime, agent):
        """Initialize the ContextualSemanticParser.

        Args:
            runtime (GenieRuntime): The runtime instance.
        """
        self.runtime = runtime
        self.agent = agent

    async def generate_formal_representation(
        self,
        dlg_history: List[CurrentDialogueTurn],
        current_dlg_turn: CurrentDialogueTurn,
        state_schema: Optional[str],
        agent_acts: Optional[str],
        agent_utterance: Optional[str],
        available_worksheets_text: str,
        available_dbs_text: str,
    ) -> str:
        """Generate formal code representation from natural language input.

        Args:
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.
            state_schema (Optional[str]): The state schema.
            agent_acts (Optional[str]): The agent actions.
            agent_utterance (Optional[str]): The agent utterance.
            available_worksheets_text (str): Available worksheets text.
            available_dbs_text (str): Available databases text.

        Returns:
            str: The generated formal code representation.
        """
        prompt_inputs = self._prepare_prompt_inputs(
            dlg_history,
            current_dlg_turn,
            state_schema,
            agent_acts,
            agent_utterance,
            available_worksheets_text,
            available_dbs_text,
        )

        model_args = self._get_model_args()

        parsed_output = await llm_generate(
            "semantic_parser.prompt",
            prompt_inputs=prompt_inputs,
            prompt_dir=self.agent.prompt_dir,
            **model_args,
        )

        return extract_code_block_from_output(parsed_output, lang="python")

    def _prepare_prompt_inputs(
        self,
        dlg_history: List[CurrentDialogueTurn],
        current_dlg_turn: CurrentDialogueTurn,
        state_schema: Optional[str],
        agent_acts: Optional[str],
        agent_utterance: Optional[str],
        available_worksheets_text: str,
        available_dbs_text: str,
    ) -> Dict[str, Any]:
        """Prepare inputs for the LLM prompt.

        Args:
            Same as generate_formal_representation.

        Returns:
            Dict[str, Any]: The prepared prompt inputs.
        """
        current_date = datetime.datetime.now()
        return {
            "user_utterance": current_dlg_turn.user_utterance,
            "dlg_history": dlg_history,
            "apis": available_worksheets_text,
            "dbs": available_dbs_text,
            "date": current_date.strftime("%Y-%m-%d"),
            "day": current_date.strftime("%A"),
            "date_tmr": (current_date + datetime.timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
            "yesterday_date": (current_date - datetime.timedelta(days=1)).strftime(
                "%Y-%m-%d"
            ),
            "state": state_schema,
            "agent_actions": agent_acts if agent_acts else "None",
            "agent_utterance": agent_utterance,
            "description": self.agent.description,
        }

    def _get_model_args(self) -> Dict[str, Any]:
        """Get model arguments for LLM generation.

        Returns:
            Dict[str, Any]: The model arguments.
        """
        return self.agent.config.semantic_parser.model_dump()


class KnowledgeBaseParser:
    """A class responsible for processing and transforming answer queries into SUQL queries.

    This class handles the extraction and processing of answer queries, managing database table
    information, and generating SUQL queries with proper parameter handling.

    Attributes:
        runtime (GenieRuntime): The bot runtime instance for database access.
    """

    def __init__(self, runtime: GenieRuntime, parser):
        """Initialize the KnowledgeBaseParser.

        Args:
            runtime (GenieRuntime): The runtime instance.
            parser (BaseParser): The parser instance.
        """
        self.runtime = runtime
        self.parser = parser

    async def process_answer_queries(
        self,
        answer_queries: List[str],
        dlg_history: List[CurrentDialogueTurn],
        user_target: str,
        pattern_type: str,
    ) -> Tuple[List[str], str]:
        """Process answer queries and generate SUQL queries.

        Args:
            answer_queries (List[str]): List of answer queries to process.
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
            user_target (str): The user target code.
            pattern_type (str): The pattern type ("func" or "attr").

        Returns:
            Tuple[List[str], str]: Processed SUQL queries and updated user target.
        """
        suql_queries = []
        updated_target = user_target

        for answer_query in answer_queries:
            logger.info(f"Answer query: {answer_query}")
            parsing_sql_response = await self._parse_to_suql(dlg_history, answer_query)

            if parsing_sql_response:
                suql_query, db_result, db_result_exec = parsing_sql_response
            else:
                suql_query = None
                db_result = None
                db_result_exec = False

            if suql_query:
                tables, unfilled_params = self._process_suql_query(suql_query)
                suql_queries.append(suql_query)

            updated_target = self._update_user_target(
                updated_target,
                answer_query,
                suql_query,
                tables,
                unfilled_params,
                pattern_type,
                db_result,
                db_result_exec,
            )

        return suql_queries, updated_target

    async def _parse_to_suql(
        self,
        dlg_history: List[CurrentDialogueTurn],
        answer_query: str,
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """Parse an answer query to SUQL format.

        Args:
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
            answer_query (str): The answer query to parse.

        Returns:
            Tuple[Optional[str], Optional[str], bool]: The parsed SUQL query, database result, and database result
            execution is True if the query is executed.
        """
        suql_query, db_result, db_result_exec = await self.parser.parse(
            answer_query[1:-1], dlg_history, self.runtime
        )

        if suql_query is None:
            logger.error(f"SUQL parsing failed for {answer_query}")
            return ""

        return suql_query.replace("\*", "*"), db_result, db_result_exec

    def _process_suql_query(self, suql_query: str) -> Tuple[List[str], Dict[str, Any]]:
        """Process a SUQL query to extract tables and unfilled parameters.

        Args:
            suql_query (str): The SUQL query to process.

        Returns:
            Tuple[List[str], Dict[str, Any]]: Tables and unfilled parameters.
        """
        if "SELECT" not in suql_query:
            return [], {}

        tables = Parser(suql_query).tables
        table_req_params = {
            table: self._get_required_params_in_table(table)[0] for table in tables
        }

        _, unfilled_params = _check_required_params(suql_query, table_req_params)

        # Check if primary key is filled when there are unfilled params
        if unfilled_params:
            id_filled, _ = _check_required_params(
                suql_query, self._get_table_primary_keys()
            )
            if id_filled:
                unfilled_params = {}

        return tables, unfilled_params

    def _get_table_primary_keys(self) -> Dict[str, List[str]]:
        """Get the primary keys for all tables in the bot's database models.

        Returns:
            Dict[str, List[str]]: A dictionary mapping table names to their primary keys.
        """
        mapping = {}
        for db in self.runtime.genie_db_models:
            for field in get_genie_fields_from_ws(db):
                if field.primary_key:
                    mapping[db.__name__] = [field.name]
        return mapping

    def _get_required_params_in_table(self, table: str) -> Tuple[List[str], Any]:
        """Get the required parameters for a given table.

        Args:
            table (str): The name of the table.

        Returns:
            Tuple[List[str], Any]: A tuple containing required parameters and table class.
        """
        required_params = []
        table_class = None
        for db in self.runtime.genie_db_models:
            if db.__name__ == table:
                table_class = db
                for field in get_genie_fields_from_ws(db):
                    if not field.optional:
                        required_params.append(field.name)
        return required_params, table_class

    @staticmethod
    def _update_user_target(
        user_target: str,
        answer_query: str,
        suql_query: str,
        tables: List[str],
        unfilled_params: Dict[str, Any],
        pattern_type: str,
        db_result: Optional[str],
        db_result_exec: bool,
    ) -> str:
        """Update the user target with processed query information.

        Args:
            user_target (str): The current user target.
            answer_query (str): The original answer query.
            suql_query (str): The processed SUQL query.
            tables (List[str]): The tables used in the query.
            unfilled_params (Dict[str, Any]): The unfilled parameters.
            pattern_type (str): The pattern type ("func" or "attr").

        Returns:
            str: The updated user target.
        """
        # TODO: Something is fucked up here.
        # we should be able to pass the db_result and db_result_exec to the answer worksheet
        # and use it to update the result
        # I don't want to execute it directly right now, that doesn't seem a good idea -- there can be random formatting
        # issues and other complications.
        if pattern_type == "func":
            answer_str = f"Answer({repr(suql_query)}, {unfilled_params}, {tables}, {repr(answer_query[1:-1])})"
            return user_target.replace(f"answer({answer_query})", answer_str)
        else:
            answer_var = re.search(r"answer_(\d+)", user_target).group(0)
            answer_str = (
                f"{answer_var}.result = []\n"
                f"{answer_var}.update(query={repr(suql_query)}, "
                f"unfilled_params={unfilled_params}, tables={tables}, "
                f"query_str={repr(answer_query[1:-1])})"
            )
            return user_target.replace(
                f"{answer_var}.query = {answer_query}", answer_str
            )


class GenieParser:
    """A class that handles semantic parsing for the Genie conversational AI system.

    This class is responsible for converting natural language utterances into executable code,
    handling SQL queries, and managing the dialogue state.

    Attributes:
        bot (GenieRuntime): The bot runtime instance containing configuration and models.
        contextual_parser (ContextualSemanticParser): Parser for generating formal code.
        knowledge_parser (KnowledgeBaseParser): Parser for handling database queries.
    """

    def __init__(
        self,
        runtime: GenieRuntime,
        parser: "BaseParser",
        agent: "Agent",
    ):
        """Initialize the GenieParser.

        Args:
            runtime (GenieRuntime): The bot runtime instance.
        """
        self.runtime = runtime
        self.contextual_parser = ContextualSemanticParser(runtime, agent)
        self.knowledge_parser = KnowledgeBaseParser(runtime, parser)
        self.current_dir = os.path.dirname(__file__)
        self.agent = agent

    async def parse(
        self,
        current_dlg_turn: CurrentDialogueTurn,
        dlg_history: List[CurrentDialogueTurn],
    ) -> None:
        """Convert user utterance to worksheet representation and process it.

        Args:
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.
        """
        # Convert the user utterance to worksheet representation
        user_formal, suql_target = await self._natural_language_to_formal(
            current_dlg_turn, dlg_history
        )

        current_dlg_turn.user_target_sp = user_formal
        current_dlg_turn.user_target_suql = "\n".join(suql_target)

        # Rewrite the code to extract function calls to variables
        genie_user_target = self._symbolic_code_rewrite(user_formal)

        current_dlg_turn.user_target = genie_user_target

    def _symbolic_code_rewrite(self, user_target: str) -> Optional[str]:
        """Extract function calls to variables using AST.

        Args:
            user_target (str): The user target code to rewrite.

        Returns:
            Optional[str]: The rewritten code with extracted function calls, or None if parsing fails.
        """
        valid_worksheets = [func.__name__ for func in self.runtime.genie_worksheets]
        valid_dbs = [func.__name__ for func in self.runtime.genie_db_models]

        valid_worksheets.extend(["Answer", "MoreFieldInfo"])
        var_counter = count_worksheet_variables(self.runtime.context.context)

        try:
            return rewrite_code_to_extract_funcs(
                user_target,
                valid_worksheets,
                valid_dbs,
                var_counter,
            )
        except SyntaxError as e:
            logger.info(f"SyntaxError: {e}")
            return None

    async def _natural_language_to_formal(
        self,
        current_dlg_turn: CurrentDialogueTurn,
        dlg_history: List[CurrentDialogueTurn],
    ) -> Tuple[str, List[str]]:
        """Convert natural language to executable code.

        Args:
            current_dlg_turn (CurrentDialogueTurn): The current dialogue turn.
            dlg_history (List[CurrentDialogueTurn]): The dialogue history.

        Returns:
            Tuple[str, List[str]]: A tuple containing the user target code and SUQL queries.
        """
        input_data = prepare_semantic_parser_input(
            self.runtime, dlg_history, current_dlg_turn, self.agent.starting_prompt
        )
        (
            state_schema,
            agent_acts,
            agent_utterance,
            available_worksheets_text,
            available_dbs_text,
        ) = input_data

        user_target = await self.contextual_parser.generate_formal_representation(
            dlg_history,
            current_dlg_turn,
            state_schema,
            agent_acts,
            agent_utterance,
            available_worksheets_text,
            available_dbs_text,
        )

        answer_queries, pattern_type = self._extract_answer_queries(user_target)
        suql_queries, user_target = await self.knowledge_parser.process_answer_queries(
            answer_queries, dlg_history, user_target, pattern_type
        )

        return user_target.strip(), suql_queries

    @staticmethod
    def _extract_answer_queries(text: str) -> Tuple[List[str], str]:
        """Extract answer queries from the provided text.

        Args:
            text (str): The input text containing answer queries.

        Returns:
            Tuple[List[str], str]: A tuple containing extracted queries and pattern type.
        """
        pattern_type = "func"
        # Match answer() with string argument
        pattern = r'answer\((?:("[^"]*")|(\'[^\']*\'))\)'
        matches = re.findall(pattern, text)

        # Match answer(query='...') format
        if not matches:
            pattern = r'answer\(query=(?:("[^"]*")|(\'[^\']*\'))\)'
            matches = re.findall(pattern, text)

        queries = [match[0] or match[1] for match in matches]

        if not queries:
            pattern = r'answer_\d+\.query = (?:("[^"]*")|(\'[^\']*\'))'
            matches = re.findall(pattern, text)
            queries = [match[0] or match[1] for match in matches]
            pattern_type = "attr"

        return queries, pattern_type

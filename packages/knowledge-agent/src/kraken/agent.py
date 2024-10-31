import json
import os

from chainlite import chain, llm_generation_chain, load_config_from_file
from kraken.state import Action, PartToWholeParserState, SqlQuery
from kraken.utils import (
    BaseParser,
    execute_sql_object,
    format_table_schema,
    get_relevant_examples,
    get_relevant_table_schema,
    parse_string_to_json,
    sql_string_to_sql_object,
)
from langgraph.graph import END, StateGraph
from loguru import logger

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
load_config_from_file(os.path.join(CURRENT_DIR, "..", "..", "llm_config.yaml"))


@chain
async def json_to_string(j: dict) -> str:
    return json.dumps(j, indent=2, ensure_ascii=False)


@chain
async def json_to_action(action_dict: dict) -> Action:
    thought = action_dict["thought"]
    action_name = action_dict["action_name"]
    action_argument = action_dict["action_argument"]

    if action_name == "execute_sql":
        assert action_argument, action_dict

    return Action(
        thought=thought,
        action_name=action_name,
        action_argument=action_argument,
    )


class PartToWholeParser(BaseParser):
    @classmethod
    def initialize(
        cls,
        engine: str,
        table_w_ids: dict,
        database_name: str,
        suql_model_name: str,
        embedding_server_address: str = "http://127.0.0.1:8509",
        source_file_mapping: dict = {},
        domain_instructions: str | None = None,
        examples: list | None = None,
        table_schema: list | None = None,
        available_actions=[
            "get_tables_schema",  # retrieve relevant tables based on a query
        ],
        suql_api_base: str = None,
        suql_api_version: str = None,
    ):
        @chain
        async def initialize_state(_input):
            return PartToWholeParserState(
                question=_input["question"],
                conversation_history=_input["conversation_history"],
                engine=engine,
                action_counter=0,
                actions=[],
                examples=examples or [],
                table_schemas=table_schema or [],
                domain_instructions=domain_instructions,
                api_base=suql_api_base,
                api_version=suql_api_version,
            )

        # build the graph
        graph = StateGraph(PartToWholeParserState)
        graph.add_node("start", lambda x: {})
        graph.add_node("controller", PartToWholeParser.controller)
        graph.add_node("execute_sql", PartToWholeParser.execute_sql)
        graph.add_node("get_tables_schema", PartToWholeParser.get_tables_schema)
        # graph.add_node("get_examples", PartToWholeParser.get_examples)

        graph.add_node("stop", PartToWholeParser.stop)

        graph.set_entry_point("start")

        graph.add_edge("start", "controller")
        graph.add_conditional_edges(
            "controller",
            PartToWholeParser.router,  # the function that will determine which node is called next.
        )
        for n in [
            "execute_sql",
            "get_tables_schema",
            # "get_examples",
        ]:
            graph.add_edge(n, "controller")

        graph.add_edge("stop", END)

        cls.controller_chain = (
            {
                "input": llm_generation_chain(
                    template_file="controller.prompt",
                    engine=engine,
                    max_tokens=700,
                    temperature=1.0,
                    top_p=0.9,
                    # stop_tokens=["Observation:"],
                    keep_indentation=True,
                )
            }
            | llm_generation_chain(
                template_file="format_actions.prompt",
                engine=engine,
                max_tokens=700,
                keep_indentation=True,
                output_json=True,
            )
            | parse_string_to_json
            | json_to_action
        )

        cls.sql_chain = sql_string_to_sql_object | execute_sql_object.bind(
            table_w_ids=table_w_ids,
            database_name=database_name,
            suql_model_name=suql_model_name,
            embedding_server_address=embedding_server_address,
            source_file_mapping=source_file_mapping,
            api_base=suql_api_base,
            api_version=suql_api_version,
        )

        compiled_graph = graph.compile()
        cls.runnable = initialize_state | compiled_graph
        logger.info("Finished initializing the graph.")
        # compiled_graph.get_graph().print_ascii()  # requies grandalf
        # sys.stdout.flush()

    @staticmethod
    def get_current_action(state):
        return state["actions"][-1]

    @staticmethod
    async def router(state):
        move_back_on_duplicate_action = 2
        current_action = PartToWholeParser.get_current_action(state)
        if current_action in state["actions"][-5:-1]:
            logger.warning(
                "Took duplicate action %s, going back %d steps.",
                current_action.action_name,
                move_back_on_duplicate_action,
            )
            # current_action.observation = "I have already taken this action. I should not repeat the same action twice."
            # Remove generated_sparqls as well
            if len(state["actions"]) - 2 >= 0:
                for i in range(len(state["actions"]) - 2, -1, -1):
                    if state["actions"][i].action_name == "execute_sql":
                        state["generated_sqls"] = state["generated_sqls"][:-1]
            state["actions"] = state["actions"][:-move_back_on_duplicate_action]
            state["action_counter"] -= move_back_on_duplicate_action
            return "controller"

        if state["action_counter"] >= 15:
            if (
                len(state["generated_sqls"]) == 0
                or not state["generated_sqls"][-1].has_results()
            ):
                logger.warning(
                    "Reached action_counter limit without a good Sql. Starting over."
                )
                state["generated_sqls"] = []
                state["actions"] = []
                state["action_counter"] = 0

            return END

        return state["actions"][-1].action_name

    @staticmethod
    @chain
    async def controller(state):
        # if state["actions"]:
        #     print("last action = ", state["actions"][-1])
        #     sys.stdout.flush()

        # make the history shorter
        actions = state["actions"][-10:]
        action_history = []
        for i, a in enumerate(actions):
            include_observation = True
            if i < len(actions) - 2 and a.action_name in [
                "get_tables_schema",
                "get_examples",
                "get_feedback_on_result",
            ]:
                include_observation = False
            action_history.append(a.to_jinja_string(include_observation))

        action = await PartToWholeParser.controller_chain.ainvoke(
            {
                "question": state["question"],
                "action_history": action_history,
                "conversation_history": state["conversation_history"],
                "instructions": state["domain_instructions"],
            }
        )
        logger.debug(f"Generated action: {action}")
        return {"actions": action, "action_counter": 1}

    @staticmethod
    @chain
    async def execute_sql(state):
        current_action = PartToWholeParser.get_current_action(state)
        assert current_action.action_name == "execute_sql"
        logger.debug(f"executing {current_action.action_argument}")
        sql = await PartToWholeParser.sql_chain.ainvoke(current_action.action_argument)
        current_action.action_argument = (
            sql.sql
        )  # update it with the cleaned and optimized SQL
        # print(sql.has_results())
        # print(sql.execution_result)
        if sql.has_results():
            # current_action.observation = sql.results_in_table_format()
            current_action.observation = sql.execution_result
            # print("SUQL execution result:", current_action.observation)
        else:
            current_action.observation = sql.execution_status

        return {"generated_sqls": sql}

    @staticmethod
    @chain
    async def get_tables_schema(state):
        current_action = PartToWholeParser.get_current_action(state)
        assert current_action.action_name == "get_tables_schema"
        action_results = get_relevant_table_schema(
            current_action.action_argument, state["table_schemas"]
        )
        current_action.observation = format_table_schema(action_results)

    @staticmethod
    @chain
    async def get_examples(state):
        current_action = PartToWholeParser.get_current_action(state)
        assert current_action.action_name == "get_examples"
        action_result = await get_relevant_examples(
            current_action.action_argument, state["examples"]
        )
        current_action.observation = "\n".join(action_result)

    @staticmethod
    @chain
    async def stop(state):
        current_action = PartToWholeParser.get_current_action(state)
        assert current_action.action_name == "stop"
        # print("generated_sqls = ", state["generated_sqls"])
        for s in state["generated_sqls"]:
            assert isinstance(s, SqlQuery)
        if (
            len(state["generated_sqls"]) == 0
            or not state["generated_sqls"][-1].has_results()
        ):
            logger.warning("Stop() was called without a good Sql. Starting over.")
            state["generated_sqls"] = []
            state["actions"] = []
            state["action_counter"] = 0
            return

        logger.info("Finished run for question %s", state["question"])
        final_sql = state["generated_sqls"][-1]
        if final_sql.sql.strip().endswith("LIMIT 10"):
            logger.info("Removing LIMIT 10 from the final Sql")
            s = final_sql.sql.strip()[: -len("LIMIT 10")]
            final_sql = SqlQuery(sql=s)
            final_sql.execute()

        return {"final_sql": final_sql}

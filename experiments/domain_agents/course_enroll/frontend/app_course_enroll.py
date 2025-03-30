import json
import os
import random
import sys
from typing import Any, Dict, List

import chainlit as cl
from loguru import logger
from suql.agent import postprocess_suql

from worksheets import (
    AgentBuilder,
    AzureModelConfig,
    Config,
    SUQLKnowledgeBase,
    SUQLReActParser,
)
from worksheets.agent.chainlit import ChainlitAgent
from worksheets.core.dialogue import CurrentDialogueTurn
from worksheets.utils.annotation import get_agent_action_schemas, get_context_schema

sys.path.append(
    "/home/harshit/genie-worksheets/experiments/domain_agents/course_enroll/"
)


# Define your APIs
course_is_full = {}


def course_detail_to_individual_params(course_detail):
    if course_detail.value is None:
        return {}
    course_detail = course_detail.value
    course_detail = {}
    for field in get_genie_fields_from_ws(course_detail):
        course_detail[field.name] = field.value

    return course_detail


def courses_to_take_oval(**kwargs):
    return {"success": True, "transaction_id": uuid4()}


def is_course_full(course_id, **kwargs):
    # randomly return True or False
    if course_id not in course_is_full:
        is_full = random.choice([True, False])
        course_is_full[course_id] = is_full

    return course_is_full[course_id]


# Constants
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(CURRENT_DIR, "data", "user_conversation")
LOGS_DIR = os.path.join(CURRENT_DIR, "..", "user_logs_courseenroll")
LOGS_FILE = os.path.join(LOGS_DIR, "user_logs_230325.log")
EXAMPLES_PATH = os.path.join(CURRENT_DIR, "..", "examples.txt")
INSTRUCTIONS_PATH = os.path.join(CURRENT_DIR, "..", "instructions.txt")
TABLE_SCHEMA_PATH = os.path.join(CURRENT_DIR, "..", "table_schema.txt")
PROMPT_DIR = os.path.join(CURRENT_DIR, "..", "prompts")
GSHEET_ID = "1ejyFlZUrUZiBmFP3dLcVNcKqzAAfw292-LmyHXSFsTE"
GENERAL_INFO_PATH = os.path.join(CURRENT_DIR, "course_assistant_general_info.txt")
DB_CONFIG = {
    "database_name": "course_assistant",
    "embedding_server_address": "http://127.0.0.1:8509",
    "db_username": "select_user",
    "db_password": "select_user",
}
TABLE_PRIMARY_KEYS = {
    "courses": "course_id",
    "ratings": "rating_id",
    "offerings": "course_id",
    "programs": "program_id",
}

# Extend python path to include parent directories
sys.path.append(os.path.join(CURRENT_DIR, "..", ".."))

# Configure logger
logger.remove()
logger.add(LOGS_FILE, rotation="1 day")

# Azure OpenAI configuration
config = Config(
    semantic_parser=AzureModelConfig(
        model_name="azure/gpt-4o",
        api_key=os.getenv("AZURE_OPENAI_WS_KEY"),
        api_version=os.getenv("AZURE_WS_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_WS_ENDPOINT"),
    ),
    response_generator=AzureModelConfig(
        model_name="azure/gpt-4o",
        api_key=os.getenv("AZURE_OPENAI_WS_KEY"),
        api_version=os.getenv("AZURE_WS_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_WS_ENDPOINT"),
    ),
    knowledge_parser=AzureModelConfig(
        model_name="gpt-4o",
        api_key=os.getenv("AZURE_OPENAI_WS_KEY"),
        api_version=os.getenv("AZURE_WS_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_WS_ENDPOINT"),
    ),
    knowledge_base=AzureModelConfig(
        model_name="azure/gpt-4o",
        api_key=os.getenv("AZURE_OPENAI_WS_KEY"),
        api_version=os.getenv("AZURE_WS_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_WS_ENDPOINT"),
    ),
    prompt_dir=PROMPT_DIR,
)


def convert_to_json(dialogue: List[CurrentDialogueTurn]) -> List[Dict[str, Any]]:
    """
    Convert dialogue history to JSON format for storage.

    Args:
        dialogue: List of dialogue turns

    Returns:
        List of dialogue turns in JSON format
    """
    json_dialogue = []
    for turn in dialogue:
        json_turn = {
            "user": turn.user_utterance,
            "bot": turn.system_response,
            "turn_context": get_context_schema(turn.context),
            "global_context": get_context_schema(turn.global_context),
            "system_action": get_agent_action_schemas(turn.system_action),
            "user_target_sp": turn.user_target_sp,
            "user_target": turn.user_target,
            "user_target_suql": turn.user_target_suql,
        }
        json_dialogue.append(json_turn)
    return json_dialogue


def get_user_conversation_dir(user_id: str) -> str:
    """
    Get the user conversation directory path.

    Args:
        user_id: User ID

    Returns:
        Path to user conversation directory
    """
    return os.path.join(DATA_DIR, user_id)


def ensure_user_dir_exists(user_id: str) -> None:
    """
    Ensure that the user conversation directory exists.

    Args:
        user_id: User ID
    """
    user_dir = get_user_conversation_dir(user_id)
    os.makedirs(user_dir, exist_ok=True)


def save_conversation(
    user_id: str, dialogue: List[CurrentDialogueTurn], filename: str
) -> str:
    """
    Save conversation to a file.

    Args:
        user_id: User ID
        dialogue: Dialogue history
        filename: Filename to save to

    Returns:
        Path to saved file
    """
    user_dir = get_user_conversation_dir(user_id)
    file_path = os.path.join(user_dir, filename)

    with open(file_path, "w") as f:
        json.dump(convert_to_json(dialogue), f, indent=4)

    return file_path


def create_agent() -> ChainlitAgent:
    """
    Create and configure the course enrollment agent.

    Returns:
        Configured ChainlitAgent
    """
    return (
        AgentBuilder(
            name="Course Enrollment Assistant",
            description="You are a course enrollment assistant. You can help students with course selection and enrollment.",
            starting_prompt="""Hello! I'm the Course Enrollment Assistant. I can help you with:
- Selecting a course: just say find me programming courses
- Enrolling into a course. 
- Asking me any question related to courses and their requirement criteria.

How can I help you today? 
    """,
            agent_class=ChainlitAgent,
        )
        .with_knowledge_base(
            SUQLKnowledgeBase,
            tables_with_primary_keys=TABLE_PRIMARY_KEYS,
            database_name=DB_CONFIG["database_name"],
            embedding_server_address=DB_CONFIG["embedding_server_address"],
            source_file_mapping={
                "course_assistant_general_info.txt": GENERAL_INFO_PATH
            },
            postprocessing_fn=postprocess_suql,
            result_postprocessing_fn=None,
            db_username=DB_CONFIG["db_username"],
            db_password=DB_CONFIG["db_password"],
        )
        .with_parser(
            SUQLReActParser,
            example_path=EXAMPLES_PATH,
            instruction_path=INSTRUCTIONS_PATH,
            table_schema_path=TABLE_SCHEMA_PATH,
        )
        .add_apis(
            (course_detail_to_individual_params, "Get course details"),
            (courses_to_take_oval, "Final API to enroll into a course"),
            (is_course_full, "Check if a course is full"),
        )
        .with_gsheet_specification(GSHEET_ID)
        .build(config)
    )


@cl.on_chat_start
async def initialize():
    """Initialize the chat session when a user starts a conversation."""
    agent = create_agent()
    cl.user_session.set("bot", agent)

    user_id = cl.user_session.get("id")
    logger.info(f"Chat started for user {user_id}")

    ensure_user_dir_exists(user_id)

    welcome_message = (
        f"Here is your user id: **{user_id}**\n"
        f"{agent.starting_prompt}\n\n"
        # "Please be a user who asks several questions.\n\n"
        # "It is mandatory for users (you) to enroll in at least two courses.\n"
        "**Note:** The database only contains Computer Science courses and contains course data till the academic 2023."
    )

    await cl.Message(welcome_message).send()


@cl.on_message
async def get_user_message(message):
    """Handle user messages and generate responses."""
    agent = cl.user_session.get("bot")
    await agent.generate_next_turn_cl(message.content)

    cl.user_session.set("bot", agent)
    user_id = cl.user_session.get("id")
    response = agent.dlg_history[-1].system_response

    ensure_user_dir_exists(user_id)

    # Save intermediate conversation
    file_path = save_conversation(
        user_id, agent.dlg_history, "intermediate_conversation.json"
    )

    # Send response with conversation log attachment
    await cl.Message(
        response,
        elements=[cl.File(name="conv_log.json", path=file_path)],
    ).send()


@cl.on_chat_end
def on_chat_end():
    """Handle the end of a chat session."""
    user_id = cl.user_session.get("id")
    agent = cl.user_session.get("bot")

    ensure_user_dir_exists(user_id)

    if agent.dlg_history:
        user_dir = get_user_conversation_dir(user_id)
        file_name = "conversation.json"
        file_path = os.path.join(user_dir, file_name)

        # If file already exists, create a new one with random suffix
        if os.path.exists(file_path):
            file_name = f"conversation_{random.randint(0, 1000)}.json"
            file_path = os.path.join(user_dir, file_name)

        save_conversation(user_id, agent.dlg_history, file_name)
    else:
        # If no dialogue history, remove the user directory
        try:
            user_dir = get_user_conversation_dir(user_id)
            os.rmdir(user_dir)
        except OSError:
            # Directory might not be empty or might not exist
            logger.warning(f"Could not remove directory for user {user_id}")

    logger.info(f"Chat ended for user {user_id}")

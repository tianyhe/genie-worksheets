import json
import os
import random

import chainlit as cl
from langchain.memory import ChatMessageHistory
from langchain_core.messages import SystemMessage
from loguru import logger

from experiments.baselines.gpt_servicenow import generate_next_turn_async
from worksheets.agents.servicebot import spreadsheet
from worksheets.components import CurrentDialogueTurn
from worksheets.specification.from_spreadsheet import gsheet_to_genie

current_dir = os.path.dirname(os.path.realpath(__file__))
logger.remove()

logger.add(
    os.path.join(current_dir, "..", "user_logs_servicenow", "user_logs.log"),
    rotation="1 day",
)

user_dialogues = {}

# yelp bot
unhappy_paths = [
    "**- Once you have given some information, change it (e.g, the course name, the issue you were having)**",
    "**- Ask question about how to enroll in a course**",
]

goals = [
    "- You want to applied for leave of absense but cannot check your form status.",
    "- You are having trouble with joining waitlist for a course.",
    "- You cannot find your AP credits in your transcript.",
]

goals = "\n" + "\n".join(goals) + "\n"

unhappy_paths = "\n" + "\n".join(unhappy_paths)


def convert_to_json(dialogue: list[CurrentDialogueTurn]):
    json_dialogue = []
    for turn in dialogue:
        json_turn = {
            "user": turn.user_utterance,
            "bot": turn.system_response,
            "context": None,
            "system_action": None,
            "user_target_sp": turn.user_target_sp,
            "user_target": turn.user_target,
            "user_target_suql": turn.user_target_suql,
        }
        json_dialogue.append(json_turn)
    return json_dialogue


@cl.on_chat_start
async def initialize():
    user_id = cl.user_session.get("id")

    user_dialogues[user_id] = {
        "dlg_history": [],
        "db_results": [],
        "chat_history": None,
    }
    user_dialogues[user_id]["chat_history"] = ChatMessageHistory()

    user_dialogues[user_id]["chat_history"].add_message(
        SystemMessage(
            content="""You an assistant for Stanford student services. You can help the student with their questions and generate a help ticket if needed.
            
    Follow these instructions:
    - Always confirm the information with the student before submitting the ticket.
    - After you have all the information, submit the ticket using the 'submit_ticket' tool.

    For External Test Credits:
    You should ask for:
        - test issues if the specific issue is 'Missing or Incorrect Test Score'.
        - test type if specific issue is 'Missing or Incorrect Test Score' and test issue is Credit Not Posted.
        - time of test score submission if specific issue is 'Missing or Incorrect Test Score' and test issue is Credit Not Posted.
        - type of international test if specifc issue is Submit International Test for Unit Award.
        - subjects for unit award if specifc issue is Submit International Test for Unit Award.
    """
        )
    )

    cl.user_session.set(
        "bot",
        gsheet_to_genie(
            bot_name=spreadsheet.botname,
            description=spreadsheet.description,
            prompt_dir=spreadsheet.prompt_dir,
            starting_prompt=spreadsheet.starting_prompt,
            args={},
            api=spreadsheet.api,
            gsheet_id=spreadsheet.gsheet_id_default,
            suql_runner=spreadsheet.suql_runner,
            suql_prompt_selector=None,
        ),
    )

    logger.info(f"Chat started for user {user_id}")
    if not os.path.exists(
        os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "servicenow",
            "user_conversation_gpt",
            user_id,
        )
    ):
        os.mkdir(
            os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "servicenow",
                "user_conversation_gpt",
                user_id,
            )
        )
    await cl.Message(
        f"Here is your user id: **{user_id}**\n"
        + cl.user_session.get("bot").starting_prompt
        + f"\n\nTry to talk for at least 10 turns. Assume that you have one of the following goals or make up one along the similar lines: {goals}"
    ).send()


@cl.on_message
async def get_user_message(message):
    user_id = cl.user_session.get("id")
    response = await generate_next_turn_async(
        message.content,
        user_dialogues[user_id]["dlg_history"],
        user_dialogues[user_id]["chat_history"],
        user_dialogues[user_id]["db_results"],
    )

    await cl.Message(response).send()


@cl.on_chat_end
def on_chat_end():
    user_id = cl.user_session.get("id")
    if not os.path.exists(
        os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "servicenow",
            "user_conversation_gpt",
            user_id,
        )
    ):
        os.mkdir(
            os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "servicenow",
                "user_conversation_gpt",
                user_id,
            )
        )

    if len(user_dialogues[user_id]["dlg_history"]):
        file_name = os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "servicenow",
            "user_conversation_gpt",
            user_id,
            "conversation.json",
        )
        if os.path.exists(file_name):
            file_name = os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "servicenow",
                "user_conversation_gpt",
                user_id,
                f"conversation_{random.randint(0, 1000)}.json",
            )
        else:
            with open(
                file_name,
                "w",
            ) as f:
                json.dump(
                    {
                        "dialogue": convert_to_json(
                            user_dialogues[user_id]["dlg_history"]
                        ),
                        "db_results": user_dialogues[user_id]["db_results"],
                        "chat_history": [
                            turn.content
                            for turn in user_dialogues[user_id]["chat_history"].messages
                        ],
                    },
                    f,
                )
    else:
        os.rmdir(
            os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "servicenow",
                "user_conversation_gpt",
                user_id,
            )
        )

    logger.info(f"Chat ended for user {user_id}")

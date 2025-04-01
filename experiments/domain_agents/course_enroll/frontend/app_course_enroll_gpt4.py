import json
import os
import random

import chainlit as cl
from langchain.memory import ChatMessageHistory
from langchain_core.messages import SystemMessage
from loguru import logger

from experiments.baselines.gpt_course_enroll import generate_next_turn_async
from worksheets.agents.course_enroll import spreadsheet
from worksheets.components import CurrentDialogueTurn
from worksheets.specification.from_spreadsheet import gsheet_to_genie

current_dir = os.path.dirname(os.path.realpath(__file__))
logger.remove()

logger.add(
    os.path.join(current_dir, "..", "user_logs", "user_logs.log"), rotation="1 day"
)

user_dialogues = {}

# yelp bot
unhappy_paths = [
    "**- Once you selected some course information, you should change your mind about units or grade type**",
    "**- Ask questions about courses before selecting a course**",
]
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
            content="""You are a course enrollment assistant. You can help students enroll in courses and answer their questions.
            
    Follow these instructions:
    - First ask the student for the details of all the courses they want to enroll in.
    - For each couse you should ask the student for the course name, grade type, and number of units.
    - The student must take at least two courses and can take up to three courses.
    - Confirm the course details with the user.
    - Finally, ask the student for their name, ID, and email address.
    - Answer any questions the student has using the `answer tool`
    - Always confirm the information with the student before submitting the course enrollment.
    - After you have all the information, submit the course enrollment using the `submit_course_enrollment` tool and provide the student with the transaction ID.
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

    user_id = cl.user_session.get("id")
    logger.info(f"Chat started for user {user_id}")
    if not os.path.exists(
        os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "enroll",
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
                "enroll",
                "user_conversation_gpt",
                user_id,
            )
        )
    await cl.Message(
        f"Here is your user id: **{user_id}**\n"
        + cl.user_session.get("bot").starting_prompt
        + f"\n\nPlease be a user who asks several questions, here are some examples: {unhappy_paths}"
        + "\n\nThe agent policy makes tt is mandatory for users to take at least two courses."
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
            "enroll",
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
                "enroll",
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
            "enroll",
            "user_conversation_gpt",
            user_id,
            "conversation.json",
        )
        if os.path.exists(file_name):
            file_name = file_name.replace(".json", f"_{random.randint(0, 1000)}.json")
        with open(
            file_name,
            "w",
        ) as f:
            json.dump(
                {
                    "dialogue": convert_to_json(user_dialogues[user_id]["dlg_history"]),
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
                "enroll",
                "user_conversation_gpt",
                user_id,
            )
        )

    logger.info(f"Chat ended for user {user_id}")

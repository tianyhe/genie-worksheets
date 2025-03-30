import json
import os
import random

import chainlit as cl
from langchain.memory import ChatMessageHistory
from langchain_core.messages import SystemMessage
from loguru import logger

from experiments.baselines.gpt_yelpbot import generate_next_turn_async
from worksheets.agents.yelpbot import spreadsheet
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
    "Once you have selected a restaurant, ask for a different restaurant",
    "Before confirming the booking, create a special request for your booking (e.g., this is for anniversary)",
    "Change your mind about the restaurant criteria (e.g. change the cuisine you want to eat)",
    "Change the restaurant booking details in the middle of the booking (eg. change the number of people, or change the time)",
    "Randomly, in between the conversation ask question about the cancellation policy",
]


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
            content="""You are the restaurant booking assistant!
            
    Follow these instructions:
    - Use the answer function to answer to user's questions.
    - Use the book_restaurant function to book a restaurant.
    - If the user asks for a restuarant and they are do not want to book, then propose to book the restaurant.
    - Confirm the booking details before booking the restaurant.
    - If the user doesn't confirm then propose them deals or other restaurants.
    - Give the user the transaction id after booking the restaurant.
    - If the user asks for restaurants then ask for location first.
    - Always ask for the arguments one by one.
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

    cl.user_session.set("unhappy_choice", random.choice(unhappy_paths))

    user_id = cl.user_session.get("id")
    logger.info(f"Chat started for user {user_id}")
    if not os.path.exists(
        os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "user_conversation_gpt_final",
            user_id,
        )
    ):
        os.mkdir(
            os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "user_conversation_gpt_final",
                user_id,
            )
        )
    await cl.Message(
        f"Here is your user id: **{user_id}**\n"
        + cl.user_session.get("bot").starting_prompt
        + f"\n\nPlease follow the unhappy path: **{cl.user_session.get('unhappy_choice')}**"
    ).send()


@cl.on_message
async def get_user_message(message):
    user_id = cl.user_session.get("id")

    msg = cl.Message("")

    await msg.send()

    response = await generate_next_turn_async(
        message.content,
        user_dialogues[user_id]["dlg_history"],
        user_dialogues[user_id]["chat_history"],
        user_dialogues[user_id]["db_results"],
    )

    msg.content = response

    await msg.update()


@cl.on_chat_end
def on_chat_end():
    user_id = cl.user_session.get("id")
    if not os.path.exists(
        os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "user_conversation_gpt_final",
            user_id,
        )
    ):
        os.mkdir(
            os.path.join(
                current_dir,
                "..",
                "benchmarks",
                "data",
                "user_conversation_gpt_final",
                user_id,
            )
        )

    if len(user_dialogues[user_id]["dlg_history"]):
        file_name = os.path.join(
            current_dir,
            "..",
            "benchmarks",
            "data",
            "user_conversation_gpt_final",
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
                    "unhappy_path": cl.user_session.get("unhappy_choice"),
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
                "user_conversation_gpt_final",
                user_id,
            )
        )

    logger.info(f"Chat ended for user {user_id}")

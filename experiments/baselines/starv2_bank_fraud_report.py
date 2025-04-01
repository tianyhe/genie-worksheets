import argparse
import json
import os
import random
from glob import glob
from queue import PriorityQueue

import openai
from loguru import logger
from tqdm import tqdm

from worksheets.agents.bankbot import spreadsheet
from worksheets.annotation_utils import get_agent_action_schemas, get_context_schema
from worksheets.components import CurrentDialogueTurn, generate_next_turn
from worksheets.environment import (
    GenieContext,
    GenieWorksheet,
    get_genie_fields_from_ws,
)
from worksheets.specification.from_spreadsheet import gsheet_to_genie

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))

logger.remove()
logger.add(
    os.path.join(CURRENT_DIR, "bank_fraud_report.log"),
    format="{time} {level} {message}",
    level="INFO",
)


def create_parser():
    parser = argparse.ArgumentParser(description="Convert STARv2 data to JSON")
    parser.add_argument(
        "--input",
        type=str,
        help="Path to the STARv2 data directory",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to the output JSON file",
    )
    return parser


def convert_to_json(dialogue: list[CurrentDialogueTurn]):
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


def load_state(slots: dict):
    bot = gsheet_to_genie(
        bot_name=spreadsheet.botname,
        description=spreadsheet.description,
        prompt_dir=spreadsheet.prompt_dir,
        starting_prompt=spreadsheet.starting_prompt,
        api=spreadsheet.api,
        args={},
        gsheet_id=spreadsheet.gsheet_id_default,
        suql_prompt_selector=spreadsheet.suql_prompt_selector,
        suql_runner=spreadsheet.suql_runner,
    )

    for key, value in slots.items():
        if slots[key] == "forgot":
            slots[key] = "NA"
    first_auth = False
    second_auth = False
    if slots.get("AccountNumber") or slots.get("PIN"):
        first_auth = True

    if (
        slots.get("DateOfBirth")
        or slots.get("SecurityAnswer1")
        or slots.get("SecurityAnswer2")
    ):
        second_auth = True

    main = f"""main = Main(
    full_name={repr(slots.get("FullName"))},
    fraud_report={repr(slots.get("FraudReport"))},
    first_authentication_details={"first_authentication" if first_auth else repr(None)},
    second_authentication_details={"second_authentication" if second_auth else repr(None)},
)
"""

    first_authentication = f"""first_authentication = FirstAuthentication(
    account_number={repr(slots.get("AccountNumber"))},
    pin={repr(slots.get("PIN"))},
    )
"""
    second_authentication = f"""second_authentication = SecondAuthentication(
    date_of_birth={repr(slots.get("DateOfBirth"))},
    security_answer_1={repr(slots.get("SecurityAnswer1"))},
    security_answer_2={repr(slots.get("SecurityAnswer2"))}
)
"""

    slot_to_worksheet = {
        "FullName": main,
        "AccountNumber": first_authentication,
        "PIN": first_authentication,
        "FraudReport": main,
        "DateOfBirth": second_authentication,
        "SecurityAnswer1": second_authentication,
        "SecurityAnswer2": second_authentication,
    }

    code_to_execute = []
    for slot in slots:
        if slot_to_worksheet[slot] not in code_to_execute:
            code_to_execute.append(slot_to_worksheet[slot])

    priority_order = [
        first_authentication,
        second_authentication,
        main,
    ]
    q = PriorityQueue()
    for code in code_to_execute:
        q.put((priority_order.index(code), code))

    code_to_execute = []
    while not q.empty():
        code_to_execute.append(q.get()[1])

    code_to_execute = "\n".join(code_to_execute)
    local_context = GenieContext({})
    bot.execute(code_to_execute, local_context=local_context, sp=True)

    for key, value in local_context.context.items():
        if isinstance(value, GenieWorksheet):
            for field in get_genie_fields_from_ws(value):
                if (
                    field.value is not None
                    and field.value != "NA"
                    and not isinstance(field.value, GenieWorksheet)
                ):
                    # field.perform_action(bot, local_context)
                    field.action_performed = True
            if value.is_complete(bot, local_context):
                value.perform_action(bot, local_context)
                value.action_performed = True

    bot.context.update(local_context.context)

    return bot


def run_one_file(file, output_path):
    output_path = os.path.join(
        output_path, f"bank_fraud_report_{os.path.basename(file)}"
    )
    if os.path.exists(output_path):
        return
    with open(file, "r") as f:
        data = json.load(f)

    dlg_history = []

    turn_num = 0
    start_turn = 0
    prev_agent_utterance = None
    current_state = {}
    for event in data["Events"]:
        if event["Action"] == "utter":
            bot = load_state(current_state)

            if turn_num != 0:
                bot.dlg_history.append(
                    CurrentDialogueTurn(system_response=prev_agent_utterance)
                )

            if turn_num >= start_turn:
                generate_next_turn(event["Text"], bot)

            dlg_history.append(
                {
                    "state": bot.dlg_history[-1] if len(bot.dlg_history) else [],
                    "event": event,
                }
            )
            if "PredictedBeliefState" in event:
                current_state = event["PredictedBeliefState"]
            turn_num += 1
        if event["Agent"] == "Wizard" and "Text" in event:
            prev_agent_utterance = event["Text"]
            if event["Action"] == "pick_suggestion":
                dlg_history[-1]["sys_act"] = event["ActionLabel"]

    dlg_history_jsonified = []
    for turn in dlg_history:
        if "state" in turn:
            state = turn["state"]
            if state:
                state = convert_to_json([state])
            dlg_history_jsonified.append(
                {
                    "state": state,
                    "event": turn["event"],
                    "sys_act": turn.get("sys_act", None),
                }
            )

    with open(output_path, "w") as f:
        json.dump(dlg_history_jsonified, f)


def main(input_path, output_path):
    files = glob(os.path.join(input_path, "*.json"))

    count = 0
    bank_files = []
    for file in files:
        with open(file, "r") as f:
            data = json.load(f)

        if "bank" in data["Scenario"]["Domains"]:
            if len(data["Scenario"]["WizardCapabilities"]) == 1:
                capabilities = data["Scenario"]["WizardCapabilities"][0]
                if (
                    capabilities["Domain"] == "bank"
                    and capabilities["Task"] == "bank_fraud_report"
                ):
                    count += 1
                    bank_files.append(file)

    # files = random.sample(bank_files, 30)
    files = bank_files

    for file in tqdm(files):
        try:
            run_one_file(file, output_path)
        except openai.BadRequestError:
            continue


if __name__ == "__main__":
    try:
        args = create_parser().parse_args()
        main(args.input, args.output)

    except Exception as e:
        import pdb
        import sys
        import traceback

        extype, value, tb = sys.exc_info()
        traceback.print_exc()
        pdb.post_mortem(tb)

import argparse
import json
import os
import random
from glob import glob
from queue import PriorityQueue

import openai
from loguru import logger
from tqdm import tqdm

from worksheets.agents.tripbot import spreadsheet
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
    os.path.join(CURRENT_DIR, "trip.log"),
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


def load_state(
    slots: dict, next_step: bool | None = None, current_step: int | None = None
):
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

    travel_information = f"""travel_information = TravelInformation(travel_mode={repr(slots.get("TravelMode"))}, departure_location={repr(slots.get("DepartureLocation"))}, arrival_location={repr(slots.get("ArrivalLocation"))}, departure_time={repr(slots.get("DepartureTime"))})"""

    if next_step is not None:
        continue_details = f"""continue_details = ContinueDetails(show_next_step={repr(next_step)}, current_step={repr(current_step)})"""
    else:
        continue_details = ""

    slot_to_worksheet = {
        "TravelMode": travel_information,
        "DepartureLocation": travel_information,
        "ArrivalLocation": travel_information,
        "DepartureTime": travel_information,
    }

    code_to_execute = []
    for slot in slots:
        if slot_to_worksheet[slot] not in code_to_execute:
            code_to_execute.append(slot_to_worksheet[slot])

    if next_step is not None:
        code_to_execute.append(continue_details)

    priority_order = [travel_information, continue_details]
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

    if "continue_details" in local_context.context and current_step is not None:
        local_context.context["continue_details"].show_next_step = None

    bot.context.update(local_context.context)

    return bot


def run_one_file(file, output_path):
    output_path = os.path.join(output_path, f"trip_{os.path.basename(file)}")
    if os.path.exists(output_path):
        return
    with open(file, "r") as f:
        data = json.load(f)

    dlg_history = []

    next_step = None
    current_step = None
    turn_num = 0
    start_turn = 0
    prev_agent_utterance = None
    current_state = {}
    for event in data["Events"]:
        if event["Action"] == "utter":
            bot = load_state(
                current_state, next_step=next_step, current_step=current_step
            )

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

            if "ActionLabel" in event:
                if "user_trip_directions_continue" in event["ActionLabel"]:
                    next_step = True
                    if current_step is None:
                        current_step = 1
                    current_step += 1
                elif "user_trip_directions_no_continue" in event["ActionLabel"]:
                    next_step = False
                    if current_step is None:
                        current_step = 1

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
        json.dump(dlg_history_jsonified, f, indent=4)


def main(input_path, output_path):
    files = glob(os.path.join(input_path, "*.json"))

    count = 0
    bank_files = []
    for file in files:
        with open(file, "r") as f:
            data = json.load(f)

        if "trip" in data["Scenario"]["Domains"]:
            if len(data["Scenario"]["WizardCapabilities"]) == 1:
                count += 1
                bank_files.append(file)

    files = random.sample(bank_files, 50)
    # files = bank_files
    # files = ["benchmarks/data/starv2/STARv2/dialogues/165.json"]

    for file in tqdm(files):
        try:
            run_one_file(file, output_path)
        except openai.BadRequestError:
            continue


if __name__ == "__main__":
    try:
        args = create_parser().parse_args()

        if args.input is None:
            args.input = "benchmarks/data/starv2/STARv2/dialogues/"
        if args.output is None:
            args.output = "benchmarks/trip/"
        main(args.input, args.output)

    except Exception as e:
        import pdb
        import sys
        import traceback

        extype, value, tb = sys.exc_info()
        traceback.print_exc()
        pdb.post_mortem(tb)

import asyncio
import os
import random
from uuid import uuid4

import yaml
from suql.agent import postprocess_suql

from worksheets.agent import Agent
from worksheets.environment import get_genie_fields_from_ws
from worksheets.interface_utils import conversation_loop
from worksheets.knowledge import SUQLKnowledgeBase, SUQLReActParser

with open("model_config.yaml", "r") as f:
    model_config = yaml.safe_load(f)

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


# Define path to the prompts

current_dir = os.path.dirname(os.path.realpath(__file__))
prompt_dir = os.path.join(current_dir, "prompts")

# Define Knowledge Base
suql_knowledge = SUQLKnowledgeBase(
    llm_model_name="azure/gpt-4o",
    tables_with_primary_keys={
        "courses": "course_id",
        "ratings": "rating_id",
        "offerings": "course_id",
        "programs": "program_id",
    },
    database_name="course_assistant",
    embedding_server_address="http://127.0.0.1:8509",
    source_file_mapping={
        "course_assistant_general_info.txt": os.path.join(
            current_dir, "course_assistant_general_info.txt"
        )
    },
    postprocessing_fn=postprocess_suql,
    result_postprocessing_fn=None,
    api_base="https://ovaloairesourceworksheet.openai.azure.com/",
    api_version="2024-08-01-preview",
)

# Define the SUQL React Parser
suql_react_parser = SUQLReActParser(
    llm_model_name="gpt-4o",
    example_path=os.path.join(current_dir, "examples.txt"),
    instruction_path=os.path.join(current_dir, "instructions.txt"),
    table_schema_path=os.path.join(current_dir, "table_schema.txt"),
    knowledge=suql_knowledge,
)

# Define the agent
course_assistant_bot = Agent(
    botname="Course Enrollment Assistant",
    description="You are a course enrollment assistant. You can help students with course selection and enrollment.",
    prompt_dir=prompt_dir,
    starting_prompt="""Hello! I'm the Course Enrollment Assistant. I can help you with :
- Selecting a course: just say find me programming courses
- Enrolling into a course. 
- Asking me any question related to courses and their requirement criteria.

How can I help you today? 
""",
    args=model_config,
    api=[course_detail_to_individual_params, courses_to_take_oval, is_course_full],
    knowledge_base=suql_knowledge,
    knowledge_parser=suql_react_parser,
    model_config=model_config,
).load_from_gsheet(
    gsheet_id="1ejyFlZUrUZiBmFP3dLcVNcKqzAAfw292-LmyHXSFsTE",
)

if __name__ == "__main__":
    # Run the conversation loop
    asyncio.run(conversation_loop(course_assistant_bot, "course_assistant_bot.json"))

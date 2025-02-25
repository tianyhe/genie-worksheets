import asyncio
import os
import random
from uuid import uuid4

from suql.agent import postprocess_suql

from worksheets import (
    AgentBuilder,
    AzureModelConfig,
    Config,
    SUQLKnowledgeBase,
    SUQLReActParser,
    conversation_loop,
)
from worksheets.core.worksheet import get_genie_fields_from_ws

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
    prompt_dir=prompt_dir,
)

agent = (
    AgentBuilder(
        name="Course Enrollment Assistant",
        description="You are a course enrollment assistant. You can help students with course selection and enrollment.",
        starting_prompt="""Hello! I'm the Course Enrollment Assistant. I can help you with :
- Selecting a course: just say find me programming courses
- Enrolling into a course. 
- Asking me any question related to courses and their requirement criteria.

How can I help you today? 
""",
    )
    .with_knowledge_base(
        SUQLKnowledgeBase,
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
    )
    .with_parser(
        SUQLReActParser,
        example_path=os.path.join(current_dir, "examples.txt"),
        instruction_path=os.path.join(current_dir, "instructions.txt"),
        table_schema_path=os.path.join(current_dir, "table_schema.txt"),
    )
    .add_apis(
        (course_detail_to_individual_params, "Get course details"),
        (courses_to_take_oval, "Final API to enroll into a course"),
        (is_course_full, "Check if a course is full"),
    )
    .with_gsheet_specification("1ejyFlZUrUZiBmFP3dLcVNcKqzAAfw292-LmyHXSFsTE")
    .build(config)
)


if __name__ == "__main__":
    # Run the conversation loop in the terminal
    asyncio.run(conversation_loop(agent, "course_assistant_bot.json"))

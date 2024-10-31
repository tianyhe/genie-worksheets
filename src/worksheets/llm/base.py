import json
from typing import Callable, Dict, List, Tuple

from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import StrOutputParser
from langchain_community.callbacks.manager import get_openai_callback
from langchain_openai import AzureChatOpenAI, OpenAI
from loguru import logger

from worksheets.llm.utils import load_prompt


class BaseLLM:
    def __init__(self, api_key: str, **params):
        """Base class for using language models.

        Args:
            api_key (str): API key for the model.
            params (dict): Default additional parameters for the model. These
            are useful if you want to create a model with a specific
            configuration. For example, DeterministicGPT with temperature=0.0.
        """
        self.api_key = api_key
        self.params = params

    async def generate(
        self,
        prompt: Tuple[str, str] | None,
        prompt_path: str | None,
        examples: List[str] | None,
        examples_path: str | None,
        prompt_input: Dict[str, str],
        model: str,
        post_processing_func: Callable,
        **llm_params,
    ):
        """Generate text from the language model.

        Args:
            prompt (Tuple[str, str] | None): Tuple of the system prompt and the user prompt.
            prompt_path (str | None): Path to the prompt file.
            examples (List[str] | None): List of examples to use for the model.
            examples_path (str | None): Path to the examples file in jsonl format with keys: user, ai.
            prompt_input (Dict[str, str]): Dictionary of the prompt input.
            model (str): Name of the model to use.
            post_processing_func (Callable): Function to post-process the output.
            llm_params (dict): Additional parameters for the language model.
        """

        if prompt is None and prompt_path is None:
            raise ValueError("Prompt or prompt_path must be provided.")

        # Create parameters
        for key, value in self.params.items():
            if key not in llm_params:
                llm_params[key] = value

        # Select Model
        if model.startswith("azure/"):
            if "azure_endpoint" not in llm_params:
                raise ValueError("azure_endpoint must be provided.")

            if "api_version" not in llm_params:
                raise ValueError("api_version must be provided.")

            model = AzureChatOpenAI(
                azure_deployment=model.replace("azure/", ""),
                api_key=self.api_key,
                azure_endpoint=llm_params["azure_endpoint"],
                api_version=llm_params["api_version"],
                **llm_params,
            )
        elif model.startswith("openai/"):
            model = OpenAI(
                model=model.replace("openai/"), api_key=self.api_key, **llm_params
            )
        else:
            raise ValueError(f"Model: {model} not supported.")

        # Gather prompt
        system_prompt = None
        user_prompt = None
        if prompt is not None:
            system_prompt, user_prompt = prompt
        else:
            system_prompt, user_prompt = load_prompt(prompt_path)

        messages = [
            SystemMessagePromptTemplate.from_template(
                system_prompt, template_format="jinja2"
            )
        ]

        # Gather examples
        examples_txt = None
        if examples:
            examples_txt = "\n".join(examples)

        if examples is None and examples_path is not None:
            # read jsonl file
            with open(examples_path, "r") as f:
                examples = [json.loads(line) for line in f]

            if len(examples):
                examples_txt = "\n".join(
                    [f"{ex['user']}\n{ex['ai']}" for ex in examples]
                )

        if examples_txt:
            user_prompt = f"Examples:\n{examples_txt}\n\n{user_prompt}"

        # Putting it all together
        messages.append(
            HumanMessagePromptTemplate.from_template(
                user_prompt, template_format="jinja2"
            )
        )

        prompt_template = ChatPromptTemplate(messages=messages)

        # For logging purposes
        filled_prompt = await prompt_template.ainvoke(prompt_input)
        filled_prompt_str = ""

        for message in filled_prompt.messages:
            filled_prompt_str += message.content + "\n----------------\n"

        logger.info(f"Prompt===========:\n{filled_prompt_str}")

        # invoking the model
        chain = prompt_template | model | StrOutputParser

        with get_openai_callback() as cb:
            parsed_output = await chain.ainvoke(prompt_input)
            logger.info(
                f"total token usage: prompt tokens: {cb.prompt_tokens}, completion tokens: {cb.completion_tokens}"
            )
            logger.info(f"total cost: {cb.total_cost:.6f}")

        logger.info(f"Output: ==================\n {parsed_output}")

        return post_processing_func(parsed_output)

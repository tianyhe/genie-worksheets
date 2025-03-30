from functools import wraps

import yaml
from pydantic import BaseModel, Field


class OpenAIModelConfig(BaseModel):
    model_name: str = Field(default="azure/gpt-4o")
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=512)
    top_p: float = Field(default=1.0)
    frequency_penalty: float = Field(default=0.0)
    presence_penalty: float = Field(default=0.0)
    api_key: str = Field(default=None)
    api_base: str = Field(default=None)
    api_version: str = Field(default=None)
    config_name: str = Field(default="openai", frozen=True)


class AzureModelConfig(BaseModel):
    model_name: str = Field(default="azure/gpt-4o")
    api_key: str = Field(default=None)
    azure_endpoint: str = Field(default=None)
    api_version: str = Field(default=None)
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=512)
    top_p: float = Field(default=1.0)
    frequency_penalty: float = Field(default=0.0)
    presence_penalty: float = Field(default=0.0)
    config_name: str = Field(default="azure", frozen=True)


class Config(BaseModel):
    semantic_parser: OpenAIModelConfig | AzureModelConfig
    response_generator: OpenAIModelConfig | AzureModelConfig
    knowledge_parser: OpenAIModelConfig | AzureModelConfig
    knowledge_base: OpenAIModelConfig | AzureModelConfig

    prompt_dir: str
    validate_response: bool = Field(default=False)

    @classmethod
    def load_from_yaml(cls, path: str):
        with open(path, "r") as f:
            return cls(**yaml.safe_load(f))


def agent_api(name: str = None, description: str = None):
    """Decorator to mark functions as agent APIs

    @agent_api("get_course", "Gets course details")
    def get_course_details(course_id: str):
        ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._is_agent_api = True
        wrapper._api_name = name or func.__name__
        wrapper._api_description = description or func.__doc__
        return wrapper

    return decorator

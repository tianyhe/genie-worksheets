from __future__ import annotations
import importlib
import inspect
from pathlib import Path
from typing import Callable, Dict, Optional, Type, TYPE_CHECKING


from jinja2 import Template

from worksheets.agent.agent import Agent
from worksheets.agent.config import _AGENT_API_REGISTRY, Config
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worksheets.knowledge.base import BaseKnowledgeBase
    from worksheets.knowledge.parser import BaseKnowledgeParser


class AgentBuilder:
    def __init__(
        self,
        name: str,
        description: str,
        starting_prompt: str,
    ):
        self.name = name
        self.description = description
        self.starting_prompt = starting_prompt
        self.apis = {}
        self.knowledge_base = None
        self.parser = None
        self._kb_class: Optional[Type[BaseKnowledgeBase]] = None
        self._parser_class: Optional[Type[BaseKnowledgeParser]] = None
        self._kb_args: dict = {}
        self._parser_args: dict = {}
        self.auto_discover_apis = True  # New flag to control auto-discovery
        self._initial_context: dict = {}  # Store initial context variables

    def add_api(self, func: callable, description: str = None):
        """Register an API with name and optional description"""
        self.apis[func.__name__] = {"func": func, "description": description}
        return self

    def add_apis(self, *apis: tuple[callable, str]):
        """Register multiple APIs with names and descriptions"""
        for func, description in apis:
            self.add_api(func, description)
        return self

    def disable_auto_discovery(self):
        """Disable automatic API discovery"""
        self.auto_discover_apis = False
        return self

    def add_apis_from_module(self, module_path: str):
        """Load all APIs from a Python module"""
        module = importlib.import_module(module_path)
        for name, obj in inspect.getmembers(module):
            if hasattr(obj, "_is_agent_api"):
                self.apis[obj._api_name] = {
                    "func": obj,
                    "description": obj._api_description,
                }
        return self

    def add_apis_from_directory(self, directory: str, recursive: bool = True):
        """Auto-discover and load APIs from all Python files in a directory"""
        api_dir = Path(directory)
        pattern = "**/*.py" if recursive else "*.py"

        for python_file in api_dir.glob(pattern):
            if python_file.name.startswith("_"):
                continue

            module_path = str(python_file.relative_to(Path.cwd()).with_suffix(""))
            module_path = module_path.replace("/", ".")
            self.add_apis_from_module(module_path)

        return self

    def add_apis_from_dict(self, apis: Dict[str, Callable]):
        """Bulk add APIs from a dictionary"""
        for name, func in apis.items():
            self.apis[name] = {
                "func": func,
                "description": getattr(func, "__doc__", None),
            }
        return self

    def with_knowledge_base(self, kb_class: Type[BaseKnowledgeBase], **kwargs):
        """Configure knowledge base with tables and optional source files"""
        self._kb_class = kb_class
        self._kb_args = kwargs
        return self

    def with_parser(self, parser_class: Type[BaseKnowledgeParser], **kwargs):
        """Configure parser with tables and optional source files"""
        self._parser_class = parser_class
        self._parser_args = kwargs
        return self

    def with_gsheet_specification(self, gsheet_id: str):
        """Use a Google Sheet to specify the agent dialogue state"""
        self.gsheet_id = gsheet_id
        return self

    def with_csv_specification(self, csv_path: str):
        """Use a CSV file to specify the agent dialogue state"""
        self.csv_path = csv_path
        return self

    def with_json_specification(self, json_path: str):
        """Use a JSON file to specify the agent dialogue state"""
        self.json_path = json_path
        return self

    def with_initial_context(self, **context):
        """Set initial context variables that will be available to the agent at runtime."""
        self._initial_context = context
        return self

    def _discover_registered_apis(self):
        """Auto-discover all APIs registered with @agent_api"""
        for api in _AGENT_API_REGISTRY:
            if api._api_name not in self.apis:
                self.apis[api._api_name] = {
                    "func": api,
                    "description": api._api_description,
                }

    def build(
        self,
        config: Config,
        agent_class: Type[Agent] = Agent,
    ) -> Agent:
        """Build and return the configured agent"""

        # Auto-discover APIs if enabled
        if self.auto_discover_apis:
            self._discover_registered_apis()

        if self._kb_class:
            self.knowledge_base = self._kb_class(config.knowledge_base, **self._kb_args)

        if self._parser_class:
            self.parser = self._parser_class(
                config.knowledge_parser,
                knowledge=self.knowledge_base,
                **self._parser_args,
            )

        agent = agent_class(
            botname=self.name,
            description=self.description,
            config=config,
            api=[api["func"] for api in self.apis.values()],
            knowledge_base=self.knowledge_base,
            knowledge_parser=self.parser,
            starting_prompt=self.starting_prompt,
        )

        if hasattr(self, "gsheet_id"):
            agent.load_runtime_from_specification(gsheet_id=self.gsheet_id)
        elif hasattr(self, "csv_path"):
            agent.load_runtime_from_specification(csv_path=self.csv_path)
        elif hasattr(self, "json_path"):
            agent.load_runtime_from_specification(json_path=self.json_path)
        else:
            raise ValueError(
                "Either gsheet_id, csv_path, or json_path must be provided"
            )

        # Inject the initial context into the runtime if provided
        if self._initial_context:
            agent.runtime.context.update(self._initial_context)
            agent.runtime.local_context_init.update(self._initial_context)

        return agent


class TemplateLoader:
    def __init__(self, template: str, format: str = "jinja2"):
        self.template = template
        self.format = format

    @classmethod
    def load(cls, template: str, format: str = "jinja2"):
        with open(template, "r") as f:
            return cls(f.read(), format)

    def render(self, **kwargs):
        if self.format == "jinja2":
            template = Template(self.template)
            return template.render(**kwargs)
        else:
            raise ValueError(f"Unsupported format: {self.format}")

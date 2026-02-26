from typing import Tuple, Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
import config
import platform
from skills.loader import load_skill_index, find_relevant_skills, prompt_for_discovery, prompt_for_activation

import json

class Deps(BaseModel):
    os_name: str
    shell_name: str
    discovery: str = ""
    matched_skills: List[Dict] = []
    activation: str = ""

def create_agent(model) -> Agent[Deps]:
    agent = Agent(model)
    @agent.instructions
    def instructions(ctx: RunContext[Deps]) -> str:
        base = (
            "You are a helpful assistant that outputs STRICT JSON for shell command execution.\n"
            f"The user is running on {ctx.deps.os_name} using {ctx.deps.shell_name}.\n"
            "Respond with one of the following JSON shapes:\n"
            "{\"status\":\"execute\",\"command\":\"<single command>\"}\n"
            "{\"status\":\"choose\",\"options\":[{\"cmd\":\"<command>\",\"reason\":\"<short>\"},...]}\n"
            "{\"status\":\"clarify\",\"questions\":[\"<question1>\",\"<question2>\"]}\n"
            "{\"status\":\"tool\",\"tool\":\"<name>\",\"args\":{}}\n"
            "Do not include markdown or code fences. Return JSON only."
        )
        extra = "\n".join([p for p in [ctx.deps.matched_skills, ctx.deps.activation] if p])
        return base if not extra else f"{base}\n{extra}"
    return agent

class CommandGenerator:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Please set it in .env file.")
        self.model = OpenAIChatModel(
            config.OPENAI_MODEL,
            provider=LiteLLMProvider(
                api_key=config.OPENAI_API_KEY,
                api_base=config.OPENAI_BASE_URL or None,
            ),
        )
        self.os_name = platform.system()
        self.shell_name = config.DEFAULT_SHELL
        self.system_prompt = None
        self.messages = []
        self.agent = create_agent(self.model)

    # Legacy non-JSON command generation removed

    async def run_structured(self, text: str) -> Tuple[dict, Optional[str]]:
        index = load_skill_index()
        discovery = prompt_for_discovery(index)
        matched = find_relevant_skills(text, index)
        activation = prompt_for_activation(matched)
        base = (
            "You are a helpful assistant that outputs STRICT JSON for shell command execution.\n"
            f"The user is running on {self.os_name} using {self.shell_name}.\n"
            "Respond with one of the following JSON shapes:\n"
            "{\"status\":\"execute\",\"command\":\"<single command>\"}\n"
            "{\"status\":\"choose\",\"options\":[{\"cmd\":\"<command>\",\"reason\":\"<short>\"},...]}\n"
            "{\"status\":\"clarify\",\"questions\":[\"<question1>\",\"<question2>\"]}\n"
            "{\"status\":\"tool\",\"tool\":\"<name>\",\"args\":{}}\n"
            "Do not include markdown or code fences. Return JSON only."
        )
        extra = "\n".join([p for p in [discovery, activation] if p])
        sys_prompt = base if not extra else f"{base}\n{extra}"
        self.system_prompt = sys_prompt
        self.messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}]
        try:
            deps = Deps(os_name=self.os_name, shell_name=self.shell_name, discovery=discovery, matched_skills=matched, activation=activation)
            result = await self.agent.run(text, output_type=ResponsePayload, deps=deps)
            self.messages.append({"role": "assistant", "content": getattr(result, "output", None)})
            convo = self._format_conversation() if config.SHOW_REASONING else None
            return result, convo
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}, None

    def _build_system_prompt(self) -> str:
        return ""


    def _format_conversation(self) -> str:
        lines = []
        for m in self.messages:
            role = m["role"].capitalize()
            lines.append(f"{role}: {m['content']}")
        return "\n".join(lines)

class ChooseOption(BaseModel):
    cmd: str
    reason: Optional[str] = None

class ExecutePayload(BaseModel):
    status: Literal["execute"]
    command: str

class ChoosePayload(BaseModel):
    status: Literal["choose"]
    options: List[ChooseOption]

class ClarifyPayload(BaseModel):
    status: Literal["clarify"]
    questions: List[str]

class ToolPayload(BaseModel):
    status: Literal["tool"]
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

class ErrorPayload(BaseModel):
    status: Literal["error"]
    message: str

ResponsePayload = Union[ExecutePayload, ChoosePayload, ClarifyPayload, ToolPayload, ErrorPayload]

from typing import Tuple, Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
import config
import platform
from skills.loader import load_skill_index, find_relevant_skills, prompt_for_discovery, prompt_for_activation

import json

class CommandGenerator:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Please set it in .env file.")
        self.model = OpenAIChatModel(
            config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL or None,
        )
        self.os_name = platform.system()
        self.shell_name = config.DEFAULT_SHELL
        self.system_prompt = None
        self.messages = []

    # Legacy non-JSON command generation removed

    def generate_structured(self, query: str) -> Tuple[dict, Optional[str]]:
        base = self._build_system_prompt()
        index = load_skill_index()
        discovery = prompt_for_discovery(index)
        matched = find_relevant_skills(query, index)
        activation = prompt_for_activation(matched)
        extra = "\n".join([p for p in [discovery, activation] if p])
        self.system_prompt = base if not extra else f"{base}\n{extra}"
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        try:
            agent = Agent(self.model, system_prompt=self.system_prompt)
            result = agent.run(query, result_type=ResponsePayload)
            payload = result.data if hasattr(result, "data") else result
            self.messages.append({"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)})
            convo = self._format_conversation() if config.SHOW_REASONING else None
            return payload, convo
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}, None

    def continue_structured(self, user_reply: str) -> Tuple[dict, Optional[str]]:
        self.messages.append({"role": "user", "content": user_reply})
        try:
            agent = Agent(self.model, system_prompt=self.system_prompt or self._build_system_prompt())
            result = agent.run(user_reply, result_type=ResponsePayload)
            payload = result.data if hasattr(result, "data") else result
            self.messages.append({"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)})
            convo = self._format_conversation() if config.SHOW_REASONING else None
            return payload, convo
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}, None

    # Legacy text command extraction removed

    # Legacy command cleanup removed

    # Legacy command heuristics removed

    def _build_system_prompt(self) -> str:
        return (
            "You are a helpful assistant that outputs STRICT JSON for shell command execution.\n"
            f"The user is running on {self.os_name} using {self.shell_name}.\n"
            "Respond with one of the following JSON shapes:\n"
            "{\"status\":\"execute\",\"command\":\"<single command>\"}\n"
            "{\"status\":\"choose\",\"options\":[{\"cmd\":\"<command>\",\"reason\":\"<short>\"},...]}\n"
            "{\"status\":\"clarify\",\"questions\":[\"<question1>\",\"<question2>\"]}\n"
            "Do not include markdown or code fences. Return JSON only."
        )


    def _format_conversation(self) -> str:
        lines = []
        for m in self.messages:
            role = m["role"].capitalize()
            lines.append(f"{role}: {m['content']}")
        return "\n".join(lines)

    # Legacy non-JSON conversation removed

    def _parse_json(self, content: str) -> dict:
        s = content.strip()
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]
        try:
            obj = json.loads(s)
            return obj
        except Exception:
            return {"status": "error", "message": "Invalid JSON returned"}

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

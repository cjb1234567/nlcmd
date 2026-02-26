from openai import OpenAI
import config
import platform

from typing import Tuple, Optional
import json

class CommandGenerator:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Please set it in .env file.")
        client_args = {"api_key": config.OPENAI_API_KEY}
        if config.OPENAI_BASE_URL:
            client_args["base_url"] = config.OPENAI_BASE_URL
        self.client = OpenAI(**client_args)
        self.os_name = platform.system()
        self.shell_name = config.DEFAULT_SHELL
        self.system_prompt = None
        self.messages = []

    # Legacy non-JSON command generation removed

    def generate_structured(self, query: str) -> Tuple[dict, Optional[str]]:
        self.system_prompt = self._build_system_prompt()
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        try:
            response = self._request_json(self.messages)
            msg = response.choices[0].message
            raw = (getattr(msg, "content", None) or "") or (getattr(msg, "reasoning_content", None) or "")
            content = raw.strip()
            self.messages.append({"role": "assistant", "content": content})
            payload = self._parse_json(content)
            convo = self._format_conversation() if config.SHOW_REASONING else None
            if str(payload.get("status", "error")).lower() == "error":
                self.messages.append({"role": "user", "content": "仅返回JSON，严格遵循上述三种形态，不要任何其他文本"})
                response = self._request_json(self.messages)
                msg = response.choices[0].message
                raw = (getattr(msg, "content", None) or "") or (getattr(msg, "reasoning_content", None) or "")
                content = raw.strip()
                self.messages.append({"role": "assistant", "content": content})
                payload = self._parse_json(content)
                convo = self._format_conversation() if config.SHOW_REASONING else None
            return payload, convo
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}, None

    def continue_structured(self, user_reply: str) -> Tuple[dict, Optional[str]]:
        self.messages.append({"role": "user", "content": user_reply})
        try:
            response = self._request_json(self.messages)
            msg = response.choices[0].message
            raw = (getattr(msg, "content", None) or "") or (getattr(msg, "reasoning_content", None) or "")
            content = raw.strip()
            self.messages.append({"role": "assistant", "content": content})
            payload = self._parse_json(content)
            convo = self._format_conversation() if config.SHOW_REASONING else None
            if str(payload.get("status", "error")).lower() == "error":
                self.messages.append({"role": "user", "content": "仅返回JSON，严格遵循上述三种形态，不要任何其他文本"})
                response = self._request_json(self.messages)
                msg = response.choices[0].message
                raw = (getattr(msg, "content", None) or "") or (getattr(msg, "reasoning_content", None) or "")
                content = raw.strip()
                self.messages.append({"role": "assistant", "content": content})
                payload = self._parse_json(content)
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

    def _request_json(self, messages):
        # Try strict JSON schema first (if provider supports), then json_object, then plain
        schema = {
            "name": "nlcmd_protocol",
            "schema": {
                "type": "object",
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "status": {"const": "execute"},
                            "command": {"type": "string", "minLength": 1}
                        },
                        "required": ["status", "command"],
                        "additionalProperties": False
                    },
                    {
                        "type": "object",
                        "properties": {
                            "status": {"const": "choose"},
                            "options": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cmd": {"type": "string", "minLength": 1},
                                        "reason": {"type": "string"}
                                    },
                                    "required": ["cmd"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["status", "options"],
                        "additionalProperties": False
                    },
                    {
                        "type": "object",
                        "properties": {
                            "status": {"const": "clarify"},
                            "questions": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1}
                            }
                        },
                        "required": ["status", "questions"],
                        "additionalProperties": False
                    }
                ]
            },
            "strict": True
        }
        try:
            return self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_schema", "json_schema": schema},
            )
        except Exception:
            try:
                return self.client.chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )
            except Exception:
                return self.client.chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=300,
                )

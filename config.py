import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "glm-4.5-flash")
SHOW_REASONING = os.getenv("SHOW_REASONING", "false").lower() == "true"
DEFAULT_SHELL = os.getenv("SHELL", "/bin/bash")  # Default to bash if not set

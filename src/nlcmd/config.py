import os
import platform
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "glm-4-5-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
SHOW_REASONING = os.getenv("SHOW_REASONING", "false").lower() == "true"
SHOW_TOOLCALLING = os.getenv("SHOW_TOOLCALLING", "false").lower() == "true"

_workspace_env = os.getenv("WORKSPACE")
if _workspace_env:
    WORKSPACE = Path(_workspace_env).resolve()
else:
    WORKSPACE = (Path(__file__).parent.parent.parent / "workspace").resolve()

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
MODELS_DIR = PROJECT_ROOT / "models"

if platform.system() == "Windows":
    DEFAULT_SHELL = os.getenv("SHELL", "powershell")
else:
    DEFAULT_SHELL = os.getenv("SHELL", "/bin/bash")

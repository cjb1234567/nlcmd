"""
nlcmd - Natural Language Command Line Tool
"""

__version__ = "0.1.0"

from nlcmd.main import main
from nlcmd.llm import CommandGenerator
from nlcmd.config import WORKSPACE

__all__ = ["main", "CommandGenerator", "WORKSPACE"]

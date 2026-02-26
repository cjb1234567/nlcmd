import platform
import sys

def run(args: dict) -> str:
    items = [
        f"OS: {platform.system()} {platform.release()}",
        f"Version: {platform.version()}",
        f"Machine: {platform.machine()}",
        f"Processor: {platform.processor()}",
        f"Python: {sys.version.split()[0]}"
    ]
    return "\n".join(items)

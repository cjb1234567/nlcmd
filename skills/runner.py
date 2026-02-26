import importlib.util
from typing import Dict
from .loader import resolve_script

def run_skill(name: str, args: Dict) -> str:
    script = resolve_script(name)
    if not script:
        return f"Error: no script found for skill '{name}'"
    spec = importlib.util.spec_from_file_location(f"skill_{name}", script)
    if not spec or not spec.loader:
        return f"Error: cannot load script for '{name}'"
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore
    except Exception as e:
        return f"Error: failed to import script: {e}"
    if not hasattr(mod, "run"):
        return f"Error: script missing run(args) for '{name}'"
    try:
        result = mod.run(args or {})
        return str(result or "")
    except Exception as e:
        return f"Error: skill execution failed: {e}"

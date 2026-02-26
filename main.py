from llm import ToolPayload
from llm import ClarifyPayload
from llm import ChoosePayload
from llm import ExecutePayload
import sys
import os
import subprocess
from typing import Optional
import platform
from skills.runner import run_skill
from skills.loader import resolve_script
import sys as _sys
import asyncio
import tempfile
import re

try:
    import typer
    from rich.console import Console
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError as e:
    print(f"Error: Missing dependency {e.name}. Please run 'pip install -r requirements.txt'")
    sys.exit(1)

try:
    from llm import CommandGenerator
    import config
except ImportError:
    # If llm or config are missing (should not happen if files are there)
    print("Error: Missing internal modules.")
    sys.exit(1)

console = Console()

def adjust_command_for_skills(cmd: str) -> str:
    parts = cmd.split()
    if not parts:
        return cmd
    for i, p in enumerate(parts):
        token = p.strip("'\"")
        if token.startswith("scripts/"):
            name = os.path.splitext(os.path.basename(token))[0]
            resolved = resolve_script(name)
            if resolved:
                parts[i] = f"\"{resolved}\""
                head = parts[0].lower()
                ext = os.path.splitext(resolved)[1].lower()
                if ext == ".py":
                    if head not in ("python", "py") and head != _sys.executable.lower():
                        parts.insert(0, f"\"{_sys.executable}\"")
                elif ext == ".ps1":
                    if "powershell" not in head:
                        parts = ["powershell", "-NoProfile", "-File", f"\"{resolved}\""] + parts[i+1:]
                elif ext == ".sh":
                    if head not in ("bash", "sh"):
                        parts = ["bash", f"\"{resolved}\""] + parts[i+1:]
                # .bat/.cmd/.exe: rely on shell to execute directly
            return " ".join(parts)
    return cmd

def extract_skill_info(cmd: str):
    parts = cmd.split()
    for p in parts:
        tok = p.strip("'\"")
        if "skills" in tok and "scripts" in tok:
            base = os.path.basename(tok)
            stem, ext = os.path.splitext(base)
            return stem, ext.lower()
    return None, None

def transform_python_c(cmd: str):
    m = re.match(r'^\s*(python|py)\s+-c\s+(.+)$', cmd, re.IGNORECASE | re.DOTALL)
    if not m:
        return cmd, None
    code = m.group(2).strip()
    if (code.startswith('"') and code.endswith('"')) or (code.startswith("'") and code.endswith("'")):
        code = code[1:-1]
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8")
        tmp.write(code)
        tmp.flush()
        tmp.close()
        new_cmd = f"\"{_sys.executable}\" \"{tmp.name}\""
        return new_cmd, tmp.name
    except Exception:
        return cmd, None

async def process_payload(generator: CommandGenerator, payload: dict, reasoning: Optional[str], dry_run: bool):
    out = getattr(payload, "output", None) or payload
    if reasoning:
        console.print(Panel(reasoning, title="AI 对话记录", border_style="magenta"))
    if type(out) == ExecutePayload:
        cmd = adjust_command_for_skills(out.command).strip()
        cmd, cleanup_path = transform_python_c(cmd)
        if not cmd:
            console.print(Panel("未返回可执行命令", title="Response", border_style="yellow"))
            return
        syntax = Syntax(cmd, "bash", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="Generated Command", border_style="blue"))
        if dry_run:
            console.print("[yellow]Dry run mode enabled. Command not executed.[/yellow]")
            return
        if Confirm.ask("Do you want to execute this command?"):
            try:
                console.print(f"[dim]Executing: {cmd}[/dim]")
                skill_name, skill_ext = extract_skill_info(cmd)
                if platform.system() == "Windows" and str(getattr(config, "DEFAULT_SHELL", "")).lower().find("powershell") != -1:
                    ps_cmd_body = " ; ".join([l.strip() for l in cmd.split("\n") if l.strip()])
                    ps_cmd = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {ps_cmd_body}"
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                if cleanup_path and os.path.isfile(cleanup_path):
                    try:
                        os.remove(cleanup_path)
                    except Exception:
                        pass
                if result.stdout:
                    console.print(Panel(result.stdout, title="Output", border_style="green"))
                elif skill_ext == ".py" and skill_name:
                    output = run_skill(skill_name, {})
                    if output:
                        console.print(Panel(output, title="Tool Output", border_style="green"))
                if result.stderr:
                    console.print(Panel(result.stderr, title="Error Output", border_style="red"))
                if result.returncode != 0:
                    console.print(f"[bold red]Command failed with exit code {result.returncode}[/bold red]")
                else:
                    console.print("[bold green]Command executed successfully![/bold green]")
            except Exception as e:
                console.print(f"[bold red]Execution failed:[/bold red] {e}")
        else:
            console.print("[yellow]Execution cancelled.[/yellow]")
    elif type(out) == ChoosePayload:
        if not isinstance(out.options, list) or not out.options:
            console.print(Panel("未提供候选命令", title="Response", border_style="yellow"))
            return
        lines = []
        for i, opt in enumerate(out.options, start=1):
            cmd = str(getattr(opt, "cmd", "") or (isinstance(opt, dict) and opt.get("cmd", "") or "")).strip()
            reason = str(getattr(opt, "reason", "") or (isinstance(opt, dict) and opt.get("reason", "") or "")).strip()
            lines.append(f"{i}. {cmd}  ({reason})" if reason else f"{i}. {cmd}")
        console.print(Panel("\n".join(lines), title="候选命令", border_style="cyan"))
        choice = console.input("[bold blue]选择序号 > [/bold blue]").strip()
        try:
            idx = int(choice)
            if idx < 1 or idx > len(out.options):
                console.print(Panel("无效序号", title="提示", border_style="yellow"))
                return
            chosen_opt = out.options[idx - 1]
            chosen = str(getattr(chosen_opt, "cmd", "") or (isinstance(chosen_opt, dict) and chosen_opt.get("cmd", "") or "")).strip()
            if not chosen:
                console.print(Panel("所选项为空", title="提示", border_style="yellow"))
                return
            process_payload(generator, {"status": "execute", "command": chosen}, reasoning, dry_run)
        except ValueError:
            console.print(Panel("请输入有效数字", title="提示", border_style="yellow"))
    elif type(out) == ClarifyPayload:
        if not isinstance(out.questions, list) or not out.questions:
            console.print(Panel("需要更多信息，请补充细节", title="提示", border_style="yellow"))
        else:
            console.print(Panel("\n".join(f"- {q}" for q in out.questions), title="需要补充信息", border_style="yellow"))
        reply = console.input("[bold blue]你的回复 > [/bold blue]").strip()
        if not reply:
            return
        new_payload, new_reasoning = await generator.run_structured(reply)
        await process_payload(generator, new_payload, new_reasoning, dry_run)
    elif type(out) == ToolPayload:
        args = getattr(out, "args", {}) or {}
        if not out.tool:
            console.print(Panel("未指定工具名称", title="Response", border_style="yellow"))
            return
        if Confirm.ask(f"是否使用工具: {out.tool} ?"):
            output = run_skill(out.tool, args)
            console.print(Panel(output or "", title="Tool Output", border_style="green"))
        else:
            console.print("[yellow]已取消工具执行[/yellow]")
    else:
        console.print(Panel("未知操作类型", title="Response", border_style="yellow"))

async def process_query(generator: CommandGenerator, query: str, dry_run: bool):
    with console.status("[bold green]Generating command...[/bold green]"):
        try:
            payload, reasoning = await generator.run_structured(query)
        except Exception as e:
            console.print(f"[bold red]Error generating command:[/bold red] {e}")
            return
    await process_payload(generator, payload, reasoning, dry_run)

def main(
    query: Optional[str] = typer.Argument(None, help="The natural language query to execute"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Run in interactive mode"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Show command without executing")
):
    """
    A Linux console tool that translates natural language to shell commands.
    """
    # Check for API Key
    if not config.OPENAI_API_KEY:
        console.print(Panel("[bold red]OPENAI_API_KEY is not set![/bold red]\nPlease set it in .env file or environment variable.", title="Configuration Error"))
        sys.exit(1)

    try:
        generator = CommandGenerator()
    except Exception as e:
        console.print(f"[bold red]Error initializing CommandGenerator:[/bold red] {e}")
        sys.exit(1)

    if query:
        asyncio.run(process_query(generator, query, dry_run))
    elif interactive or not query:
        console.print(Panel("[bold green]Welcome to Natural Language Command Executor![/bold green]\nType 'exit' or 'quit' to leave.", title="NLCMD"))
        while True:
            try:
                user_input = console.input("[bold blue]nlcmd > [/bold blue]")
                if user_input.lower() in ["exit", "quit"]:
                    break
                if not user_input.strip():
                    continue
                asyncio.run(process_query(generator, user_input, dry_run))
            except KeyboardInterrupt:
                console.print("\nExiting...")
                break
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")

if __name__ == "__main__":
    typer.run(main)
    


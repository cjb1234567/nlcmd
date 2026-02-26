import sys
import os
import subprocess
from typing import Optional
import platform
from skills.runner import run_skill
from skills.loader import resolve_script
import sys as _sys

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

def process_payload(generator: CommandGenerator, payload: dict, reasoning: Optional[str], dry_run: bool):
    status = str(payload.get("status", "error")).lower()
    if reasoning:
        console.print(Panel(reasoning, title="AI 对话记录", border_style="magenta"))
    if status == "execute":
        cmd = adjust_command_for_skills(str(payload.get("command", "")).strip())
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
                    ps_cmd = " ; ".join([l.strip() for l in cmd.split("\n") if l.strip()])
                    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
                else:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
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
    elif status == "choose":
        options = payload.get("options", [])
        if not isinstance(options, list) or not options:
            console.print(Panel("未提供候选命令", title="Response", border_style="yellow"))
            return
        lines = []
        for i, opt in enumerate(options, start=1):
            cmd = str(opt.get("cmd", "")).strip()
            reason = str(opt.get("reason", "")).strip()
            lines.append(f"{i}. {cmd}  ({reason})" if reason else f"{i}. {cmd}")
        console.print(Panel("\n".join(lines), title="候选命令", border_style="cyan"))
        choice = console.input("[bold blue]选择序号 > [/bold blue]").strip()
        try:
            idx = int(choice)
            if idx < 1 or idx > len(options):
                console.print(Panel("无效序号", title="提示", border_style="yellow"))
                return
            chosen = str(options[idx - 1].get("cmd", "")).strip()
            if not chosen:
                console.print(Panel("所选项为空", title="提示", border_style="yellow"))
                return
            process_payload(generator, {"status": "execute", "command": chosen}, reasoning, dry_run)
        except ValueError:
            console.print(Panel("请输入有效数字", title="提示", border_style="yellow"))
    elif status == "clarify":
        questions = payload.get("questions", [])
        if not isinstance(questions, list) or not questions:
            console.print(Panel("需要更多信息，请补充细节", title="提示", border_style="yellow"))
        else:
            console.print(Panel("\n".join(f"- {q}" for q in questions), title="需要补充信息", border_style="yellow"))
        reply = console.input("[bold blue]你的回复 > [/bold blue]").strip()
        if not reply:
            return
        new_payload, new_reasoning = generator.continue_structured(reply)
        process_payload(generator, new_payload, new_reasoning, dry_run)
    elif status == "tool":
        tool = str(payload.get("tool", "")).strip()
        args = payload.get("args", {}) or {}
        if not tool:
            console.print(Panel("未指定工具名称", title="Response", border_style="yellow"))
            return
        if Confirm.ask(f"是否使用工具: {tool} ?"):
            output = run_skill(tool, args)
            console.print(Panel(output or "", title="Tool Output", border_style="green"))
        else:
            console.print("[yellow]已取消工具执行[/yellow]")
def process_query(generator: CommandGenerator, query: str, dry_run: bool):
    with console.status("[bold green]Generating command...[/bold green]"):
        try:
            payload, reasoning = generator.generate_structured(query)
        except Exception as e:
            console.print(f"[bold red]Error generating command:[/bold red] {e}")
            return

    if reasoning:
        console.print(Panel(reasoning, title="AI 对话记录", border_style="magenta"))

    status = str(payload.get("status", "error")).lower()
    if status == "error":
        msg = payload.get("message", "Unknown error")
        console.print(Panel(msg, title="Response", border_style="yellow"))
        return
    if status == "execute":
        command = adjust_command_for_skills(str(payload.get("command", "")).strip())
        if not command:
            console.print(Panel("未返回可执行命令", title="Response", border_style="yellow"))
            return
        syntax = Syntax(command, "bash", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="Generated Command", border_style="blue"))
        if dry_run:
            console.print("[yellow]Dry run mode enabled. Command not executed.[/yellow]")
            return
        if Confirm.ask("Do you want to execute this command?"):
            try:
                console.print(f"[dim]Executing: {command}[/dim]")
                skill_name, skill_ext = extract_skill_info(command)
                if platform.system() == "Windows" and str(getattr(config, "DEFAULT_SHELL", "")).lower().find("powershell") != -1:
                    ps_cmd = " ; ".join([l.strip() for l in command.split("\n") if l.strip()])
                    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
                else:
                    result = subprocess.run(command, shell=True, capture_output=True, text=True)
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
        return
    if status == "choose":
        options = payload.get("options", [])
        if not isinstance(options, list) or not options:
            console.print(Panel("未提供候选命令", title="Response", border_style="yellow"))
            return
        lines = []
        for i, opt in enumerate(options, start=1):
            cmd = str(opt.get("cmd", "")).strip()
            reason = str(opt.get("reason", "")).strip()
            lines.append(f"{i}. {cmd}  ({reason})" if reason else f"{i}. {cmd}")
        console.print(Panel("\n".join(lines), title="候选命令", border_style="cyan"))
        choice = console.input("[bold blue]选择序号 > [/bold blue]").strip()
        try:
            idx = int(choice)
            if idx < 1 or idx > len(options):
                console.print(Panel("无效序号", title="提示", border_style="yellow"))
                return
            chosen = str(options[idx - 1].get("cmd", "")).strip()
            if not chosen:
                console.print(Panel("所选项为空", title="提示", border_style="yellow"))
                return
            payload = {"status": "execute", "command": chosen}
            process_payload(generator, payload, reasoning, dry_run)
        except ValueError:
            console.print(Panel("请输入有效数字", title="提示", border_style="yellow"))
        return
    if status == "clarify":
        questions = payload.get("questions", [])
        if not isinstance(questions, list) or not questions:
            console.print(Panel("需要更多信息，请补充细节", title="提示", border_style="yellow"))
        else:
            console.print(Panel("\n".join(f"- {q}" for q in questions), title="需要补充信息", border_style="yellow"))
        reply = console.input("[bold blue]你的回复 > [/bold blue]").strip()
        if not reply:
            return
        payload, reasoning = generator.continue_structured(reply)
        status2 = str(payload.get("status", "error")).lower()
        if status2 == "error":
            msg = payload.get("message", "Unknown error")
            console.print(Panel(msg, title="Response", border_style="yellow"))
            return
        process_payload(generator, payload, reasoning, dry_run)
        return
    if status == "tool":
        tool = str(payload.get("tool", "")).strip()
        args = payload.get("args", {}) or {}
        if not tool:
            console.print(Panel("未指定工具名称", title="Response", border_style="yellow"))
            return
        if Confirm.ask(f"是否使用工具: {tool} ?"):
            output = run_skill(tool, args)
            console.print(Panel(output or "", title="Tool Output", border_style="green"))
        else:
            console.print("[yellow]已取消工具执行[/yellow]")
        return
    msg = payload.get("message", "无法识别的返回")
    console.print(Panel(msg, title="Response", border_style="yellow"))
    return

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
        process_query(generator, query, dry_run)
    elif interactive or not query:
        console.print(Panel("[bold green]Welcome to Natural Language Command Executor![/bold green]\nType 'exit' or 'quit' to leave.", title="NLCMD"))
        while True:
            try:
                user_input = console.input("[bold blue]nlcmd > [/bold blue]")
                if user_input.lower() in ["exit", "quit"]:
                    break
                if not user_input.strip():
                    continue
                process_query(generator, user_input, dry_run)
            except KeyboardInterrupt:
                console.print("\nExiting...")
                break
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")

if __name__ == "__main__":
    typer.run(main)


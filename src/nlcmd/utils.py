import os
import sys
import re
import tempfile
import platform
import asyncio
from pathlib import Path
from rich.syntax import Syntax
from rich.panel import Panel
from rich.prompt import Confirm

from nlcmd import config
from nlcmd.ui import console

class WorkspaceError(Exception):
    """Exception raised when workspace directory cannot be created or accessed."""
    pass

def _ensure_workspace_dir(cwd: str = None) -> str:
    """
    Ensure the workspace directory exists and is accessible.
    Returns the absolute path to the workspace directory.
    Raises WorkspaceError if the directory cannot be created.
    """
    work_dir = Path(cwd) if cwd else config.WORKSPACE
    work_dir = work_dir.resolve()
    
    if not work_dir.exists():
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[dim]Created workspace directory: {work_dir}[/dim]")
        except PermissionError as e:
            raise WorkspaceError(f"Permission denied: Cannot create workspace directory '{work_dir}': {e}")
        except OSError as e:
            raise WorkspaceError(f"Failed to create workspace directory '{work_dir}': {e}")
    
    if not work_dir.is_dir():
        raise WorkspaceError(f"Workspace path '{work_dir}' exists but is not a directory")
    
    return str(work_dir)

def _quote_arg(arg: str) -> str:
    if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
        return arg
    if re.search(r'\s', arg):
        return f"\"{arg}\""
    return arg

def build_powershell_command(cmd: str) -> str:
    parts = re.findall(r'\"[^\"]*\"|\S+', cmd)
    if not parts:
        return cmd
    head = parts[0]
    args = parts[1:]
    head_q = _quote_arg(head)
    args_q = " ".join(_quote_arg(a) for a in args)
    return f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & {head_q} {args_q}".strip()

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
        new_cmd = f"\"{sys.executable}\" \"{tmp.name}\""
        return new_cmd, tmp.name
    except Exception:
        return cmd, None

def prepare_shell_command(cmd: str) -> tuple[str, str, str]:
    """Prepare a shell command for execution. Returns (display_cmd, execution_cmd, cleanup_path)."""
    cmd = cmd.strip()
    cmd, cleanup_path = transform_python_c(cmd)
    return cmd, cmd, cleanup_path

async def execute_prepared_command_async(cmd: str, cleanup_path: str = None, cwd: str = None) -> str:
    """Execute a previously prepared shell command asynchronously using asyncio.subprocess."""
    try:
        work_dir = _ensure_workspace_dir(cwd)
        console.print(f"[dim]Executing: {cmd}[/dim]")
        console.print(f"[dim]Working directory: {work_dir}[/dim]")
        
        if platform.system() == "Windows" and str(getattr(config, "DEFAULT_SHELL", "")).lower().find("powershell") != -1:
            ps_cmd = build_powershell_command(cmd)
            process = await asyncio.create_subprocess_shell(
                f'powershell -NoProfile -Command "{ps_cmd}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
        
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        
        if cleanup_path and os.path.isfile(cleanup_path):
            try:
                os.remove(cleanup_path)
            except Exception:
                pass
                
        output_parts = []
        if stdout:
            console.print(Panel(stdout, title="Output", border_style="green"))
            output_parts.append(f"Stdout:\n{stdout}")
                
        if stderr:
            console.print(Panel(stderr, title="Error Output", border_style="red"))
            output_parts.append(f"Stderr:\n{stderr}")
            
        if process.returncode != 0:
            console.print(f"[bold red]Command failed with exit code {process.returncode}[/bold red]")
            output_parts.append(f"Exit Code: {process.returncode}")
        else:
            console.print("[bold green]Command executed successfully![/bold green]")
            
        return "\n".join(output_parts) if output_parts else "Command executed with no output"
        
    except Exception as e:
        console.print(f"[bold red]Execution failed:[/bold red] {e}")
        return f"Error: {str(e)}"

def execute_prepared_command(cmd: str, cleanup_path: str = None, cwd: str = None) -> str:
    """Execute a previously prepared shell command (synchronous wrapper for backward compatibility)."""
    return asyncio.run(execute_prepared_command_async(cmd, cleanup_path, cwd))

async def run_shell_command_with_confirmation_async(cmd: str, dry_run: bool = False, cwd: str = None) -> str:
    """
    Run a shell command with user confirmation (async version).
    Args:
        cmd: The command to execute
        dry_run: If True, only show the command without executing
        cwd: Working directory for command execution (defaults to config.WORKSPACE)
    Raises:
        WorkspaceError: If workspace directory cannot be created or accessed
    """
    work_dir = _ensure_workspace_dir(cwd)
    
    display_cmd, exec_cmd, cleanup = prepare_shell_command(cmd)
    
    if not display_cmd:
        return "Error: Empty command"
        
    syntax = Syntax(display_cmd, "bash", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title="Generated Command", border_style="blue"))
    console.print(f"[dim]Working directory: {work_dir}[/dim]")
    
    if dry_run:
        console.print("[yellow]Dry run mode enabled. Command not executed.[/yellow]")
        return "Dry run: Command not executed"
        
    try:
        if Confirm.ask("Do you want to execute this command?"):
            return await execute_prepared_command_async(exec_cmd, cleanup, cwd=work_dir)
        else:
            console.print("[yellow]Execution cancelled.[/yellow]")
            return "Execution cancelled by user"
    except WorkspaceError:
        raise
    except Exception as e:
        console.print(f"[bold red]Execution failed:[/bold red] {e}")
        return f"Error: {str(e)}"

def run_shell_command_with_confirmation(cmd: str, dry_run: bool = False, cwd: str = None) -> str:
    """
    Run a shell command with user confirmation (synchronous wrapper for backward compatibility).
    Args:
        cmd: The command to execute
        dry_run: If True, only show the command without executing
        cwd: Working directory for command execution (defaults to config.WORKSPACE)
    Raises:
        WorkspaceError: If workspace directory cannot be created or accessed
    """
    return asyncio.run(run_shell_command_with_confirmation_async(cmd, dry_run, cwd))

def execute_shell_command(cmd: str, dry_run: bool = False, cwd: str = None) -> str:
    """
    Deprecated: Kept for backward compatibility.
    Use run_shell_command_with_confirmation or execute_prepared_command instead.
    """
    return run_shell_command_with_confirmation(cmd, dry_run, cwd=cwd)

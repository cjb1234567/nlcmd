import sys
import asyncio
from typing import Optional

try:
    import typer
    from rich.panel import Panel
except ImportError as e:
    print(f"Error: Missing dependency {e.name}. Please run 'pip install -r requirements.txt'")
    sys.exit(1)

try:
    from llm import CommandGenerator
    from utils import WorkspaceError
    import config
    from ui import console
except ImportError as e:
    print(f"Error: Missing internal modules. {e}")
    sys.exit(1)

async def process_query(generator: CommandGenerator, query: str, dry_run: bool):
    def show_reasoning(text: str):
        if config.SHOW_REASONING:
            console.print(Panel(text.rstrip(), title="AI Reasoning", border_style="magenta"))
    
    try:
        response = await generator.run_task(
            query, 
            dry_run=dry_run, 
            reasoning_callback=show_reasoning
        )
    except WorkspaceError as e:
        console.print(Panel(f"[bold red]{str(e)}[/bold red]", title="Workspace Error", border_style="red"))
        return
    except Exception as e:
        console.print(f"Error executing command: {e}", markup=False)
        return

    if isinstance(response, str) and response.strip():
        console.print(Panel(response, title="AI Response", border_style="green"))

def main(
    query: Optional[str] = typer.Argument(None, help="The natural language query to execute"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Run in interactive mode"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Show command without executing")
):
    """
    A Linux console tool that translates natural language to shell commands.
    """
    if not config.OPENAI_API_KEY:
        console.print(Panel("[bold red]OPENAI_API_KEY is not set![/bold red]\nPlease set it in .env file or environment variable.", title="Configuration Error"))
        sys.exit(1)

    try:
        generator = CommandGenerator()
        console.print(f"[dim]Workspace: {generator.workspace}[/dim]")
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
                console.print(f"Error: {e}", markup=False)

if __name__ == "__main__":
    typer.run(main)

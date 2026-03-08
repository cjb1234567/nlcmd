import asyncio
import typer
from typing import Optional
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from nlcmd.ui import console
from nlcmd.cron.scheduler import TaskManager, start_scheduler
from nlcmd.cron.tasks import TASK_FUNCS

cron_app = typer.Typer(help="Manage scheduled tasks")

TASK_CHOICES = {
    "1": "run_thinking_agent",
    "2": "run_reindexing",
}


def _get_task_params(func_name: str) -> dict:
    if func_name == "run_thinking_agent":
        prompt = Prompt.ask("[cyan]Prompt[/cyan]")
        return {"prompt": prompt}
    elif func_name == "run_reindexing":
        return {}
    return {}


@cron_app.command("add")
def cron_add(
    name: str = typer.Argument(..., help="Unique name for the task"),
    func_name: str = typer.Option(None, "--func", "-f", help="Function name (run_thinking_agent, run_reindexing)"),
    schedule: str = typer.Option(None, "--schedule", "-s", help="Schedule string (e.g., 'every 10 seconds', 'daily')"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Prompt for run_thinking_agent"),
):
    if func_name is None:
        console.print("\n[cyan]Available task types:[/cyan]")
        console.print("  [1] run_thinking_agent - Execute thinking task")
        console.print("  [2] run_reindexing     - Reindex memory files")
        choice = Prompt.ask("[cyan]Select task type[/cyan]", choices=list(TASK_CHOICES.keys()), default="1")
        func_name = TASK_CHOICES[choice]
    
    if schedule is None:
        console.print("\n[dim]Schedule formats:[/dim]")
        console.print("  • every N seconds/minutes/hours/days  (e.g., 'every 10 minutes')")
        console.print("  • daily")
        console.print("  • cron: * * * * *  (standard cron expression)")
        schedule = Prompt.ask("[cyan]Schedule[/cyan]")
    
    kwargs = {}
    if func_name == "run_thinking_agent":
        if prompt is None:
            prompt = Prompt.ask("[cyan]Prompt[/cyan]")
        kwargs = {"prompt": prompt}
    
    TaskManager().add_task(name, func_name, kwargs, schedule)


@cron_app.command("remove")
def cron_remove(name: str):
    TaskManager().remove_task(name)


@cron_app.command("list")
def cron_list():
    TaskManager().list_tasks()


@cron_app.command("start")
def cron_start():
    asyncio.run(start_scheduler())


def cron_interactive():
    console.print(Panel("[bold green]Cron Task Manager - Interactive Mode[/bold green]", border_style="green"))
    
    while True:
        console.print("\n[bold cyan]Available actions:[/bold cyan]")
        console.print("  [1] Add task")
        console.print("  [2] Remove task")
        console.print("  [3] List tasks")
        console.print("  [4] Start scheduler")
        console.print("  [q] Quit")
        
        choice = Prompt.ask("\n[bold blue]Select action[/bold blue]", choices=["1", "2", "3", "4", "q"], default="1")
        
        if choice == "q":
            console.print("[dim]Goodbye![/dim]")
            break
        
        if choice == "1":
            console.print("\n[bold]--- Add New Task ---[/bold]")
            name = Prompt.ask("[cyan]Task name[/cyan]")
            
            console.print("\n[cyan]Available task types:[/cyan]")
            console.print("  [1] run_thinking_agent - Execute thinking task")
            console.print("  [2] run_reindexing     - Reindex memory files")
            func_choice = Prompt.ask("[cyan]Select task type[/cyan]", choices=list(TASK_CHOICES.keys()), default="1")
            func_name = TASK_CHOICES[func_choice]
            
            console.print("\n[dim]Schedule formats:[/dim]")
            console.print("  • every N seconds/minutes/hours/days  (e.g., 'every 10 minutes')")
            console.print("  • daily")
            console.print("  • cron: * * * * *  (standard cron expression)")
            schedule = Prompt.ask("[cyan]Schedule[/cyan]")
            
            kwargs = _get_task_params(func_name)
            
            enabled = Confirm.ask("[cyan]Enable task now?[/cyan]", default=True)
            
            manager = TaskManager()
            manager.add_task(name, func_name, kwargs, schedule)
            if not enabled:
                tasks = manager.load_tasks()
                for t in tasks:
                    if t.name == name:
                        t.enabled = False
                manager.save_tasks(tasks)
                console.print(f"[green]Task '{name}' added (disabled).[/green]")
        
        elif choice == "2":
            console.print("\n[bold]--- Remove Task ---[/bold]")
            manager = TaskManager()
            tasks = manager.load_tasks()
            
            if not tasks:
                console.print("[yellow]No tasks found.[/yellow]")
                continue
            
            console.print("\n[cyan]Existing tasks:[/cyan]")
            for i, t in enumerate(tasks, 1):
                status = "[green]●[/green]" if t.enabled else "[red]○[/red]"
                console.print(f"  [{i}] {status} {t.name} - {t.func_name} ({t.schedule})")
            
            choices = [str(i) for i in range(1, len(tasks) + 1)] + ["q"]
            task_choice = Prompt.ask("\n[cyan]Select task to remove[/cyan] (or 'q' to cancel)", choices=choices, default="q")
            
            if task_choice != "q":
                idx = int(task_choice) - 1
                manager.remove_task(tasks[idx].name)
        
        elif choice == "3":
            TaskManager().list_tasks()
        
        elif choice == "4":
            console.print("[yellow]Starting scheduler... Press Ctrl+C to stop.[/yellow]")
            try:
                asyncio.run(start_scheduler())
            except KeyboardInterrupt:
                pass
            break

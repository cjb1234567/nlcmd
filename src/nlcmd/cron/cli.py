import asyncio
import typer
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from nlcmd.ui import console
from nlcmd.cron.scheduler import TaskManager, start_scheduler

cron_app = typer.Typer(help="Manage scheduled thinking tasks")

@cron_app.command("start")
def cron_start():
    """Start the scheduler to run thinking tasks."""
    asyncio.run(start_scheduler())

@cron_app.command("add")
def cron_add(
    name: str = typer.Argument(..., help="Unique name for the task"),
    schedule: str = typer.Argument(..., help="Schedule string (e.g., 'every 10 seconds', 'daily')"),
    prompt: str = typer.Argument(..., help="The prompt to run")
):
    """Add a new thinking task."""
    TaskManager().add_task(name, prompt, schedule)

@cron_app.command("remove")
def cron_remove(name: str):
    """Remove a thinking task."""
    TaskManager().remove_task(name)

@cron_app.command("list")
def cron_list():
    """List all thinking tasks."""
    TaskManager().list_tasks()

def cron_interactive():
    """Interactive mode for cron management."""
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
            
            console.print("\n[dim]Schedule formats:[/dim]")
            console.print("  • every N seconds/minutes/hours/days  (e.g., 'every 10 minutes')")
            console.print("  • daily")
            console.print("  • cron: * * * * *  (standard cron expression)")
            schedule = Prompt.ask("[cyan]Schedule[/cyan]")
            
            prompt = Prompt.ask("[cyan]Prompt[/cyan]")
            
            enabled = Confirm.ask("[cyan]Enable task now?[/cyan]", default=True)
            
            manager = TaskManager()
            if enabled:
                manager.add_task(name, prompt, schedule)
            else:
                manager.add_task(name, prompt, schedule)
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
                console.print(f"  [{i}] {status} {t.name} ({t.schedule})")
            
            choices = [str(i) for i in range(1, len(tasks) + 1)] + ["q"]
            choice = Prompt.ask("\n[cyan]Select task to remove[/cyan] (or 'q' to cancel)", choices=choices, default="q")
            
            if choice != "q":
                idx = int(choice) - 1
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

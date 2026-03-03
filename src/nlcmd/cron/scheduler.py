import asyncio
import tomllib
from typing import List
import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from nlcmd import config

console = Console()

class ThinkingTask(BaseModel):
    name: str
    prompt: str
    schedule: str
    enabled: bool = True

def _escape_toml_string(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

def _dump_tasks_to_toml(tasks: List[ThinkingTask]) -> str:
    lines = []
    for task in tasks:
        lines.append("[[tasks]]")
        lines.append(f'name = "{_escape_toml_string(task.name)}"')
        lines.append(f'schedule = "{_escape_toml_string(task.schedule)}"')
        lines.append(f'prompt = "{_escape_toml_string(task.prompt)}"')
        lines.append(f'enabled = {"true" if task.enabled else "false"}')
        lines.append("")
    return "\n".join(lines)

class TaskManager:
    def __init__(self):
        self.cron_dir = config.WORKSPACE / "cron"
        self.config_file = self.cron_dir / "thinking.toml"
        self._ensure_config()

    def _ensure_config(self):
        if not self.cron_dir.exists():
            self.cron_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write("")

    def load_tasks(self) -> List[ThinkingTask]:
        try:
            with open(self.config_file, "rb") as f:
                try:
                    data = tomllib.load(f)
                    return [ThinkingTask(**t) for t in data.get("tasks", [])]
                except tomllib.TOMLDecodeError:
                    return []
        except Exception as e:
            console.print(f"[red]Error loading tasks: {e}[/red]")
            return []

    def save_tasks(self, tasks: List[ThinkingTask]):
        try:
            content = _dump_tasks_to_toml(tasks)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            console.print(f"[red]Error saving tasks: {e}[/red]")

    def add_task(self, name: str, prompt: str, schedule: str):
        tasks = self.load_tasks()
        if any(t.name == name for t in tasks):
            console.print(f"[red]Task with name '{name}' already exists.[/red]")
            return
        
        new_task = ThinkingTask(name=name, prompt=prompt, schedule=schedule)
        tasks.append(new_task)
        self.save_tasks(tasks)
        console.print(f"[green]Task '{name}' added successfully.[/green]")

    def remove_task(self, name: str):
        tasks = self.load_tasks()
        initial_count = len(tasks)
        tasks = [t for t in tasks if t.name != name]
        if len(tasks) < initial_count:
            self.save_tasks(tasks)
            console.print(f"[green]Task '{name}' removed successfully.[/green]")
        else:
            console.print(f"[yellow]Task '{name}' not found.[/yellow]")

    def list_tasks(self):
        tasks = self.load_tasks()
        if not tasks:
            console.print("No tasks found.")
            return

        table = Table(title="Thinking Tasks")
        table.add_column("Name", style="cyan")
        table.add_column("Schedule", style="magenta")
        table.add_column("Prompt", style="green")
        table.add_column("Enabled", style="yellow")

        for task in tasks:
            table.add_row(task.name, task.schedule, task.prompt, str(task.enabled))
        
        console.print(table)

scheduler = AsyncIOScheduler()

async def run_thinking_agent(prompt: str):
    try:
        from nlcmd.llm import CommandGenerator
        generator = CommandGenerator()
        console.print(f"[bold blue]Running thinking task:[/bold blue] {prompt}")
        
        response = await generator.run_task(prompt, dry_run=False)
        
        console.print(f"[bold green]Task completed:[/bold green]\n{response}")
    except Exception as e:
        console.print(f"[bold red]Error running thinking task:[/bold red] {e}")

def parse_trigger(schedule_str: str):
    schedule_str = schedule_str.lower().strip()
    
    if schedule_str == "daily":
        return IntervalTrigger(days=1)
    
    if schedule_str.startswith("cron:"):
        cron_expr = schedule_str[5:].strip()
        return CronTrigger.from_crontab(cron_expr)

    match = re.match(r"every\s+(\d+)\s+(second|minute|hour|day)s?", schedule_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        kwargs = {f"{unit}s": value}
        return IntervalTrigger(**kwargs)

    raise ValueError(f"Unsupported schedule format: {schedule_str}")

async def start_scheduler():
    manager = TaskManager()
    tasks = manager.load_tasks()
    
    if not tasks:
        console.print("[yellow]No tasks to schedule.[/yellow]")

    for task in tasks:
        if task.enabled:
            try:
                trigger = parse_trigger(task.schedule)
                scheduler.add_job(
                    run_thinking_agent,
                    trigger,
                    id=task.name,
                    args=[task.prompt]
                )
                console.print(f"[dim]Scheduled task '{task.name}' with schedule '{task.schedule}'[/dim]")
            except Exception as e:
                console.print(f"[red]Failed to schedule task '{task.name}': {e}[/red]")

    scheduler.start()
    console.print("[bold green]Scheduler started. Press Ctrl+C to stop.[/bold green]")
    
    try:
        while scheduler.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        if scheduler.running:
            scheduler.shutdown()
            console.print("\n[dim]Scheduler stopped.[/dim]")

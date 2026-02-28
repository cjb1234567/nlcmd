from typing import Tuple, Optional, Any, Callable, List, Dict
from pydantic import BaseModel
from pydantic_ai import Agent, CallToolsNode, ModelRequestNode, RunContext, ToolReturnPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
import platform
from pathlib import Path
from pydantic_ai_skills import SkillsToolset
from rich.panel import Panel

from nlcmd import config
from nlcmd.utils import run_shell_command_with_confirmation, WorkspaceError
from nlcmd.ui import console

MAX_CONTENT_DISPLAY = 500

def truncate_content(content: str, max_len: int = MAX_CONTENT_DISPLAY) -> str:
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."

class AgentState(BaseModel):
    os_name: str
    shell_name: str
    dry_run: bool = False
    workspace: str = ""

def build_system_prompt(deps: AgentState) -> str:
    base = (
        "You are a helpful assistant for task execution.\n"
        f"The user is running on {deps.os_name} using {deps.shell_name}.\n"
        f"The user's workspace directory is: {deps.workspace}\n"
        "All file operations should be relative to this workspace unless an absolute path is specified.\n"
        "You have access to tools to execute shell commands ('run_shell_command'), propose options ('propose_options'), and manage skills.\n"
        "Workflow:\n"
        "1. Analyze the user's request.\n"
        "2. If the request is clear and simple -> Call `run_shell_command` directly.\n"
        "3. If the request is ambiguous -> Call `propose_options` with possible commands.\n"
        "4. If the request is vague -> Ask the user for clarification (text response).\n"
        "5. If a skill is relevant -> Use `load_skill` and follow the skill instructions.\n"
        "IMPORTANT: When calling a tool, do NOT output any conversational text. Just call the tool.\n"
        "\n## File Operations:\n"
        "- OPEN vs READ: If the user says 'open [file]', they usually mean 'launch in default application'. Use `start [file]` or `Invoke-Item [file]` (Windows).\n"
        "- Only use specialized skills (like docx/pandoc) if the user asks to 'read content', 'extract text', 'summarize', or 'analyze' the file.\n"
    )
    
    if deps.shell_name.lower().find("powershell") != -1:
        base += (
            "\n## PowerShell-Specific Rules:\n"
            "- To OPEN a file in the default app: `Invoke-Item 'filename'` or `start 'filename'`.\n"
            "- NEVER use bash syntax like `cat > file << 'EOF'` or `<<EOF` - these do NOT work in PowerShell\n"
            "- To create a file with content in PowerShell, use one of these methods:\n"
            "  1. For small files: `Set-Content -Path 'file.txt' -Value 'content'`\n"
            "  2. For multi-line files: Use `@'...'@` here-string: `$content = @'\nline1\nline2\n'@; $content | Out-File -FilePath 'file.txt' -Encoding utf8`\n"
            "  3. Use Python for complex file creation: `python -c \"code\"`\n"
            "- Use `;` to separate commands (not `&&`)\n"
            "- Use `$env:VAR` for environment variables (not `$VAR`)\n"
        )
    
    return base

def create_agent(model) -> Tuple[Agent[AgentState], SkillsToolset]:
    skills_dir = Path(__file__).parent.parent.parent / 'skills'
    
    skills_toolset = SkillsToolset(directories=[skills_dir])
    
    agent = Agent(
        model, 
        toolsets=[skills_toolset]
    )
    
    @agent.instructions
    async def system_instruction(ctx: RunContext[AgentState]) -> str:
        return build_system_prompt(ctx.deps)
    
    @agent.instructions
    async def add_skills(ctx: RunContext[AgentState]) -> str | None:
        return await skills_toolset.get_instructions(ctx)

    @agent.tool
    def run_shell_command(ctx: RunContext[AgentState], command: str) -> str:
        """
        Execute a shell command directly. Use this when the user's intent is clear and a single command can solve it.
        This tool will ask for user confirmation before execution.
        Raises WorkspaceError if workspace directory cannot be created or accessed.
        """
        try:
            return run_shell_command_with_confirmation(command, dry_run=ctx.deps.dry_run, cwd=ctx.deps.workspace)
        except WorkspaceError:
            raise

    @agent.tool
    def propose_options(ctx: RunContext[AgentState], options: List[Dict[str, str]]) -> str:
        """
        Propose multiple command options to the user when the request is ambiguous.
        options: List of dicts with 'command' and 'description'.
        Example: [{"command": "ls -l", "description": "List detailed files"}, {"command": "ls -a", "description": "List all files"}]
        Raises WorkspaceError if workspace directory cannot be created or accessed.
        """
        console.print(Panel("Please choose an option:", title="Ambiguous Request", border_style="yellow"))
        for i, opt in enumerate(options):
            console.print(f"{i+1}. [bold cyan]{opt['command']}[/bold cyan] - {opt['description']}")
        
        choice = console.input("[bold yellow]Enter number (or 'c' to cancel): [/bold yellow]")
        if choice.lower() == 'c':
            return "User cancelled selection."
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                selected_cmd = options[idx]['command']
                return run_shell_command_with_confirmation(selected_cmd, dry_run=ctx.deps.dry_run, cwd=ctx.deps.workspace)
            else:
                return "Invalid selection."
        except ValueError:
            return "Invalid input."
        except WorkspaceError:
            raise

    return agent, skills_toolset

class CommandGenerator:
    def __init__(self, workspace: str = None):
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Please set it in .env file.")
        self.model = OpenAIChatModel(
            config.OPENAI_MODEL,
            provider=LiteLLMProvider(
                api_key=config.OPENAI_API_KEY,
                api_base=config.OPENAI_BASE_URL or None,
            ),
        )
        self.os_name = platform.system()
        self.shell_name = config.DEFAULT_SHELL
        self.workspace = workspace or str(config.WORKSPACE)
        self.agent, self.skills_toolset = create_agent(self.model)
        self.message_history = []

    async def run_task(self, text: str, dry_run: bool = False, reasoning_callback: Optional[Callable[[str], None]] = None) -> Any:
        deps = AgentState(
            os_name=self.os_name, 
            shell_name=self.shell_name, 
            dry_run=dry_run,
            workspace=self.workspace
        )
        
        try:
            if config.SHOW_REASONING and reasoning_callback:
                reasoning_callback("Generating system prompt...\n")
            
            full_response = ""
            async with self.agent.iter(text, deps=deps, message_history=self.message_history) as run:
                async for node in run:
                    if config.SHOW_REASONING and reasoning_callback:
                        if isinstance(node, ModelRequestNode):
                            reasoning_callback("\n[bold cyan]🚀 Sending Request to LLM:[/bold cyan]\n")
                            for part in node.request.parts:
                                if hasattr(part, 'content') and part.content:
                                    if "SystemPromptPart" in str(type(part)):
                                        reasoning_callback(f"[System Prompt] (len={len(str(part.content))})...\n")
                                    else:
                                        reasoning_callback(f"{truncate_content(str(part.content))}\n")
                                elif isinstance(part, ToolReturnPart):
                                    reasoning_callback(f"[Tool Return: {part.tool_name}]\n{truncate_content(str(part.content))}\n")
                        
                        elif isinstance(node, CallToolsNode):
                            reasoning_callback("\n[bold yellow]🛠️ LLM Decided to Call Tools:[/bold yellow]\n")
                            for part in node.model_response.parts:
                                if hasattr(part, 'content') and part.content:
                                    reasoning_callback(f"[Reasoning]: {truncate_content(str(part.content))}\n")
                                elif hasattr(part, 'tool_name') and config.SHOW_TOOLCALLING:
                                    args_str = str(part.args) if part.args else ""
                                    reasoning_callback(f"[Tool Call]: {part.tool_name}({truncate_content(args_str, 200)})\n")
                    
                    self.message_history = run.all_messages()
                
                if self.message_history:
                    last_msg = self.message_history[-1]
                    if hasattr(last_msg, 'parts'):
                        for part in last_msg.parts:
                            if hasattr(part, 'content') and isinstance(part.content, str):
                                full_response += part.content
            
            return str(full_response) if full_response else ""

        except WorkspaceError:
            raise
        except Exception as e:
            return f"Error: {str(e)}"

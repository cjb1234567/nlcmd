from typing import Tuple, Optional, Any, Callable, List, Dict, Literal
from datetime import datetime
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
from nlcmd.memory import MemoryStore

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

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
    memory_store: Any = None  # Holds the MemoryStore instance

def build_system_prompt(deps: AgentState) -> str:
    base = (
        "You are a helpful assistant for task execution.\n"
        f"The user is running on {deps.os_name} using {deps.shell_name}.\n"
        f"The user's workspace directory is: {deps.workspace}\n"
        "All file operations should be relative to this workspace unless an absolute path is specified.\n"
        "You have access to tools to execute shell commands ('run_shell_command'), propose options ('propose_options'), write files ('write_file'), save memories ('save_memory'), recall memories ('recall_memory'), and manage skills.\n"
        "Workflow:\n"
        "1. Analyze the user's request.\n"
        "2. If the request is clear and simple -> Call `run_shell_command` directly.\n"
        "3. If the request is ambiguous -> Call `propose_options` with possible commands.\n"
        "4. If the request is vague -> Ask the user for clarification (text response).\n"
        "5. If a skill is relevant -> Use `load_skill` and follow the skill instructions.\n"
        "6. To save a memory:\n"
        "   a. Call `list_memories` to check existing categories.\n"
        "   b. Call `save_memory` to append to an existing category OR create a new one.\n"
        "7. To recall a memory -> Call `recall_memory` with a relevant query.\n"
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
            "- To create a file with content, PREFER using the `write_file` tool instead of shell commands like `echo` or `Set-Content`.\n"
            "- Use `;` to separate commands (not `&&`)\n"
            "- Use `$env:VAR` for environment variables (not `$VAR`)\n"
        )
    
    return base

def create_agent(model) -> Tuple[Agent[AgentState], SkillsToolset]:
    skills_dir = Path(__file__).parent.parent.parent / 'skills'
    
    skills_toolset = SkillsToolset(directories=[skills_dir])
    
    agent = Agent(
        model, 
        toolsets=[skills_toolset],
        deps_type=AgentState
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
    def write_file(ctx: RunContext[AgentState], filepath: str, content: str) -> str:
        """
        Write content to a file directly WITHOUT asking for user confirmation.
        Use this tool for:
        1. Creating temporary files needed for intermediate steps.
        2. Creating new files when the user explicitly asks to "create a file with content".
        3. Overwriting files if necessary (be careful).
        
        The filepath is relative to the workspace.
        """
        try:
            # Construct absolute path relative to workspace
            workspace_path = Path(ctx.deps.workspace).resolve()
            full_path = (workspace_path / filepath).resolve()
            
            # Security check: Ensure the file is within the workspace
            if not str(full_path).startswith(str(workspace_path)):
                 return f"Error: Access denied. Cannot write to {filepath} outside of workspace {workspace_path}."

            if ctx.deps.dry_run:
                return f"[Dry Run] Would write to {filepath}:\n{truncate_content(content, 100)}"
            
            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return f"Successfully wrote {len(content)} characters to {filepath}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @agent.tool
    def list_memories(ctx: RunContext[AgentState], memory_type: Literal["important", "normal"]) -> str:
        """
        List existing memory files for a specific type (important/normal).
        Use this BEFORE saving a new memory to check if a relevant memory file already exists.
        
        Returns:
            A list of strings formatted as "filename: [description extracted from metadata]"
        """
        try:
            workspace_path = Path(ctx.deps.workspace).resolve()
            memory_dir = workspace_path / "memory" / memory_type
            
            if not memory_dir.exists():
                return "No existing memories found."
            
            memories = []
            for file_path in memory_dir.glob("*.md"):
                try:
                    content = file_path.read_text(encoding='utf-8')
                    description = "No description"
                    # Try to extract description from metadata
                    for line in content.splitlines():
                        if line.lower().startswith("description:"):
                            description = line.split(":", 1)[1].strip()
                            break
                    memories.append(f"{file_path.name}: {description}")
                except Exception:
                    memories.append(f"{file_path.name}: (Error reading file)")
            
            if not memories:
                return "No existing memories found."
            
            return "\n".join(memories)
        except Exception as e:
            return f"Error listing memories: {str(e)}"

    @agent.tool
    def save_memory(ctx: RunContext[AgentState], content: str, memory_type: Literal["important", "normal"], category_name: str, description: str = "") -> str:
        """
        Save a memory about the user or task.
        
        Workflow:
        1. Call `list_memories` first to see existing categories.
        2. If a suitable file exists (e.g. `user_preference.md`), reuse its `category_name` (filename without extension).
        3. If no suitable file exists, choose a new `category_name` (e.g. `user_preference`, `project_context`).
        
        Args:
            content: The detailed content to append.
            memory_type: "important" or "normal".
            category_name: The category identifier (used as filename, e.g. "user_preference"). 
                           Do NOT include date or extension.
            description: Description of this memory category (required only when creating a NEW file).
        """
        try:
            # Determine directory based on type
            workspace_path = Path(ctx.deps.workspace).resolve()
            memory_dir = workspace_path / "memory" / memory_type
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            # Sanitize category_name to be safe for filenames
            safe_name = "".join(c for c in category_name if c.isalnum() or c in ('_', '-')).strip()
            if not safe_name:
                return "Error: Invalid category_name"
            
            filename = f"{safe_name}.md"
            file_path = memory_dir / filename
            
            is_new_file = not file_path.exists()
            today = datetime.now().strftime("%Y-%m-%d")
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Prepare full entry content
            entry_header = f"### [{today} {timestamp}]"
            full_entry = f"{entry_header}\n{content}\n\n"
            
            with open(file_path, 'a', encoding='utf-8') as f:
                if is_new_file:
                    if not description:
                        description = f"Memories related to {safe_name}"
                    # Write metadata header
                    f.write(f"---\nName: {safe_name}\nDescription: {description}\nCreated: {today}\n---\n\n")
                
                # Append new memory
                f.write(full_entry)
            
            # Update search index
            if ctx.deps.memory_store:
                try:
                    metadata = {
                        "filename": filename,
                        "type": memory_type,
                        "category": safe_name,
                        "timestamp": f"{today} {timestamp}"
                    }
                    ctx.deps.memory_store.index_memory(full_entry, metadata)
                except Exception as e:
                    return f"Memory saved to file, but indexing failed: {str(e)}"

            status = "Created new" if is_new_file else "Appended to"
            return f"Successfully {status} memory file: {file_path.relative_to(workspace_path)}"
            
        except Exception as e:
            return f"Error saving memory: {str(e)}"

    @agent.tool
    def recall_memory(ctx: RunContext[AgentState], query: str, limit: int = 5) -> str:
        """
        Recall memories related to a specific query using semantic search.
        Use this when you need to remember past interactions, user preferences, or project context.
        
        Args:
            query: The search query (e.g., "user python preference", "project deployment steps").
            limit: Maximum number of results to return (default: 5).
        
        Returns:
            A formatted string containing relevant memory snippets.
        """
        if not ctx.deps.memory_store:
            return "Memory search is not available (txtai dependency missing or initialization failed)."
            
        try:
            results = ctx.deps.memory_store.search(query, limit)
            if not results:
                return f"No memories found for query: '{query}'"
            
            formatted_results = []
            for i, res in enumerate(results):
                score = res.get('score', 0.0)
                text = res.get('text', '').strip()
                meta = res.get('metadata', {})
                category = meta.get('category', 'unknown')
                formatted_results.append(f"Result {i+1} (Score: {score:.2f}) [{category}]:\n{text}\n---")
                
            return "\n".join(formatted_results)
        except Exception as e:
            return f"Error recalling memory: {str(e)}"

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
        # Initialize memory store
        memory_store = None
        try:
            memory_store = MemoryStore(self.workspace)
        except Exception as e:
            if config.SHOW_REASONING and reasoning_callback:
                reasoning_callback(f"\n[yellow]Warning: Memory store initialization failed: {e}[/yellow]\n")

        deps = AgentState(
            os_name=self.os_name, 
            shell_name=self.shell_name, 
            dry_run=dry_run,
            workspace=self.workspace,
            memory_store=memory_store
        )
        try:
            if config.SHOW_REASONING and reasoning_callback:
                reasoning_callback("Generating system prompt...\n")   
            full_response = ""
            with logfire.span("agent_execution", prompt_version="v2"):
                async with self.agent.iter(text, deps=deps, message_history=self.message_history[-4:]) as run:
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

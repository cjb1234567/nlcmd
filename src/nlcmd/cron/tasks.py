import hashlib
import json
from typing import Dict, Any, List

import anyio
from rich.console import Console

from nlcmd import config

console = Console()


async def run_thinking_agent(prompt: str):
    try:
        from nlcmd.llm import CommandGenerator
        generator = CommandGenerator()
        console.print(f"[bold blue]Running thinking task:[/bold blue] {prompt}")
        
        response = await generator.run_task(prompt, dry_run=False)
        
        console.print(f"[bold green]Task completed:[/bold green]\n{response}")
    except Exception as e:
        console.print(f"[bold red]Error running thinking task:[/bold red] {e}")


async def _compute_file_hash(file_path: anyio.Path) -> str:
    hasher = hashlib.sha256()
    async with await file_path.open('rb') as f:
        while chunk := await f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


async def _load_snapshot(snapshot_path: anyio.Path) -> Dict[str, Dict[str, Any]]:
    if not await snapshot_path.exists():
        return {}
    try:
        content = await snapshot_path.read_text(encoding='utf-8')
        return json.loads(content)
    except Exception:
        return {}


async def _save_snapshot(snapshot_path: anyio.Path, snapshot: Dict[str, Dict[str, Any]]):
    await snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    await snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')


async def run_reindexing():
    from nlcmd.memory.indexer import MemoryIndexer
    
    memory_dir = anyio.Path(config.WORKSPACE / "memory" / "important")
    snapshot_path = anyio.Path(config.WORKSPACE / "memory" / "important" / "snapshot.json")
    
    if not await memory_dir.exists():
        console.print("[yellow]No memory directory found.[/yellow]")
        return
    
    snapshot = await _load_snapshot(snapshot_path)
    current_snapshot: Dict[str, Dict[str, Any]] = {}
    changed_files: List[str] = []
    
    async for md_file in memory_dir.glob("*.md"):
        file_path_str = str(md_file)
        stat = await md_file.stat()
        mtime = stat.st_mtime
        size = stat.st_size
        
        current_snapshot[file_path_str] = {
            "mtime": mtime,
            "size": size,
            "hash": None
        }
        
        old_info = snapshot.get(file_path_str)
        needs_reindex = False
        
        if old_info is None:
            needs_reindex = True
        elif old_info.get("mtime") != mtime or old_info.get("size") != size:
            current_hash = await _compute_file_hash(md_file)
            current_snapshot[file_path_str]["hash"] = current_hash
            if old_info.get("hash") != current_hash:
                needs_reindex = True
        else:
            if old_info.get("hash"):
                current_snapshot[file_path_str]["hash"] = old_info["hash"]
        
        if needs_reindex:
            changed_files.append(file_path_str)
    
    if not changed_files:
        console.print("[dim]No changes detected in memory files.[/dim]")
        await _save_snapshot(snapshot_path, current_snapshot)
        return
    
    console.print(f"[bold blue]Detected {len(changed_files)} changed file(s), reindexing...[/bold blue]")
    
    index_path = config.WORKSPACE / "memory" / "index"
    indexer = MemoryIndexer(index_path)
    
    documents: List[tuple] = []
    
    for file_path_str in changed_files:
        file_path = anyio.Path(file_path_str)
        
        if not await file_path.exists():
            continue
            
        try:
            content = await file_path.read_text(encoding="utf-8")
            entries = content.split("\n### [")
            category = file_path.stem
            
            for i, entry in enumerate(entries[1:]):
                full_entry = "### [" + entry
                uid = f"{category}_{i}"
                metadata = {
                    "filename": file_path.name,
                    "type": "important",
                    "category": category
                }
                data = {"text": full_entry, **metadata}
                documents.append((uid, data, None))
                
        except Exception as e:
            console.print(f"[red]Error reading {file_path}: {e}[/red]")
    
    if documents:
        await indexer.index_documents_async(documents)
        console.print(f"[bold green]Reindexed {len(documents)} entries from {len(changed_files)} file(s).[/bold green]")
    
    for file_path_str in changed_files:
        if current_snapshot[file_path_str].get("hash") is None:
            current_snapshot[file_path_str]["hash"] = await _compute_file_hash(anyio.Path(file_path_str))
    
    await _save_snapshot(snapshot_path, current_snapshot)


TASK_FUNCS = {
    "run_thinking_agent": run_thinking_agent,
    "run_reindexing": run_reindexing,
}

from __future__ import annotations
from pathlib import Path
from typing import List, TYPE_CHECKING
if TYPE_CHECKING:
    from nlcmd.memory.indexer import MemoryIndexer

class MemoryStore:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()
        self.index_path = self.workspace / "memory" / "index"
        self.memory_root = self.workspace / "memory"

    def list_memories(self, memory_type: str) -> List[str]:
        memory_dir = self.memory_root / memory_type
        if not memory_dir.exists():
            return []
        return [f.name for f in memory_dir.glob("*.md")]

    def append_memory(self, memory_type: str, category: str, content: str, description: str = "") -> Path:
        from datetime import datetime
        
        safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in category)
        filename = f"{safe_name}.md"
        file_path = self.memory_root / memory_type / filename
        
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        
        is_new_file = not file_path.exists()
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        entry_header = f"### [{today} {timestamp}]"
        full_entry = f"{entry_header}\n{content}\n\n"
        
        with open(file_path, 'a', encoding='utf-8') as f:
            if is_new_file:
                if not description:
                    description = f"Memories related to {safe_name}"
                f.write(f"---\nName: {safe_name}\nDescription: {description}\nCreated: {today}\n---\n\n")
            f.write(full_entry)
        
        return file_path, full_entry, {
            "filename": filename,
            "type": memory_type,
            "category": safe_name,
            "timestamp": f"{today} {timestamp}"
        }

    def reindex_all(self, indexer: MemoryIndexer):
        documents = []
        for memory_type in ["important", "temp"]:
            type_dir = self.memory_root / memory_type
            if not type_dir.exists():
                continue
                
            for file_path in type_dir.glob("*.md"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    entries = content.split("\n### [")
                    category = file_path.stem
                    
                    for i, entry in enumerate(entries[1:]):
                        full_entry = "### [" + entry
                        uid = f"{category}_{i}"
                        metadata = {
                            "filename": file_path.name,
                            "type": memory_type,
                            "category": category
                        }
                        data = {"text": full_entry, **metadata}
                        documents.append((uid, data, None))
                        
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
        
        if documents:
            indexer.index_documents(documents)

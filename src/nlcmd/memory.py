from pathlib import Path
from typing import List, Dict, Any
import json
import hashlib
import shutil
import warnings

# Suppress warnings from transformers/huggingface
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", message=".*embeddings.position_ids.*")

try:
    from txtai.embeddings import Embeddings
except ImportError:
    Embeddings = None

from nlcmd import config

class MemoryStore:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()
        self.index_path = self.workspace / "memory" / "index"
        self.memory_root = self.workspace / "memory"
        self._embeddings = None

    def _ensure_model(self):
        """
        Ensure the embedding model exists locally.
        """
        model_name = config.EMBEDDING_MODEL
        # Extract model folder name (e.g., bge-small-zh-v1.5)
        model_folder_name = model_name.split("/")[-1]
        local_model_path = config.MODELS_DIR / model_folder_name

        if not local_model_path.exists():
            print(f"Downloading model {model_name} to {local_model_path}...")
            config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            
            # Use huggingface_hub to download model
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(
                    repo_id=model_name,
                    local_dir=local_model_path,
                    local_dir_use_symlinks=False
                )
                print(f"Model downloaded successfully to {local_model_path}")
            except ImportError:
                print("huggingface_hub not installed. Using remote model path.")
                return model_name
            except Exception as e:
                print(f"Failed to download model: {e}. Using remote model path.")
                return model_name
        
        return str(local_model_path)

    @property
    def embeddings(self):
        if self._embeddings is None:
            if Embeddings is None:
                raise ImportError("txtai is not installed. Please run 'uv sync' to install dependencies.")
            
            # Get model path (local or remote)
            model_path = self._ensure_model()
            
            # Configure hybrid search (BM25 + Vector)
            # Use bge-small-zh for better Chinese support
            config_params = {
                "path": model_path,
                "content": True,
                "hybrid": True
            }
            
            # Suppress specific loading warnings during initialization
            import logging
            logging.getLogger("transformers").setLevel(logging.ERROR)
            
            self._embeddings = Embeddings(config_params)
            
            if self.index_path.exists():
                self._embeddings.load(str(self.index_path))
                
        return self._embeddings

    def index_memory(self, content: str, metadata: Dict[str, Any]):
        """
        Index a memory chunk.
        """
        # Generate a unique ID for the chunk (e.g., hash of content + timestamp)
        uid = hashlib.md5(f"{content}{metadata.get('timestamp', '')}".encode()).hexdigest()
        
        # Upsert into txtai index
        # Format: (id, data, tags) where data is a dict containing "text" and metadata
        data = {"text": content, **metadata}
        document = (uid, data, None)
        self.embeddings.upsert([document])
        
        # Ensure parent directory exists before saving
        if not self.index_path.parent.exists():
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            
        self.embeddings.save(str(self.index_path))

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using hybrid search (BM25 + Vector).
        Returns a list of dictionaries with 'text', 'score', and metadata fields.
        """
        # Escape single quotes for SQL
        safe_query = query.replace("'", "''")
        
        # Use SQL to select all fields including the 'data' column which stores metadata
        sql = f"SELECT id, text, score, data FROM txtai WHERE similar('{safe_query}') LIMIT {limit}"
        results = self.embeddings.search(sql)
        
        parsed_results = []
        
        for r in results:
            item = {
                "id": r["id"],
                "text": r["text"],
                "score": r["score"]
            }
            
            # Parse 'data' JSON if present to extract metadata
            if "data" in r and r["data"]:
                try:
                    # 'data' is returned as a JSON string by txtai SQLite backend
                    data_obj = json.loads(r["data"])
                    # Merge metadata, excluding 'text' which we already have
                    for k, v in data_obj.items():
                        if k != "text":
                            item[k] = v
                except Exception:
                    # If parsing fails, just ignore metadata
                    pass
                    
            parsed_results.append(item)
            
        return parsed_results

    def reindex_all(self):
        """
        Rebuild index from all markdown files in memory directory.
        """
        documents = []
        for memory_type in ["important", "normal"]:
            type_dir = self.memory_root / memory_type
            if not type_dir.exists():
                continue
                
            for file_path in type_dir.glob("*.md"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    # Split content by timestamp headers or treat as chunks
                    # Simple strategy: Index the whole file content for now, 
                    # or split by "### [" if possible.
                    # Let's split by memory entries
                    entries = content.split("\n### [")
                    
                    # First part is header metadata
                    header = entries[0]
                    category = file_path.stem
                    
                    for i, entry in enumerate(entries[1:]):
                        # Re-add the split delimiter
                        full_entry = "### [" + entry
                        uid = f"{category}_{i}"
                        metadata = {
                            "filename": file_path.name,
                            "type": memory_type,
                            "category": category
                        }
                        documents.append((uid, full_entry, metadata))
                        
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
        
        if documents:
            self.embeddings.index(documents)
            self.embeddings.save(str(self.index_path))

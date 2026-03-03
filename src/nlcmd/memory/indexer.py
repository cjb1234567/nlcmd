import asyncio
import hashlib
import time
import warnings
from typing import List, Dict, Any, Tuple
from pathlib import Path

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", message=".*embeddings.position_ids.*")

try:
    from txtai.embeddings import Embeddings
except ImportError:
    Embeddings = None

from nlcmd import config


class MemoryIndexer:
    def __init__(self, index_path: Path):
        self.index_path = Path(index_path)
        self._embeddings = None
        self._index_lock = asyncio.Lock()

    def _ensure_model(self) -> str:
        model_name = config.EMBEDDING_MODEL
        model_folder_name = model_name.split("/")[-1]
        local_model_path = config.MODELS_DIR / model_folder_name

        if not local_model_path.exists():
            print(f"Downloading model {model_name} to {local_model_path}...")
            config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            
            original_offline = os.environ.get("HF_HUB_OFFLINE")
            os.environ.pop("HF_HUB_OFFLINE", None)
            
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
            finally:
                if original_offline:
                    os.environ["HF_HUB_OFFLINE"] = original_offline
        
        return str(local_model_path)

    @property
    def embeddings(self):
        if self._embeddings is None:
            if Embeddings is None:
                raise ImportError("txtai is not installed. Please run 'uv sync' to install dependencies.")
            
            model_path = self._ensure_model()
            
            os.environ["HF_HUB_OFFLINE"] = "1"
            
            config_params = {
                "path": model_path,
                "content": True,
                "hybrid": True,
                "sqlite": {"wal": True}
            }
            
            import logging
            logging.getLogger("transformers").setLevel(logging.ERROR)
            
            self._embeddings = Embeddings(config_params)
            
            if self.index_path.exists():
                self._embeddings.load(str(self.index_path))
                
        return self._embeddings

    def index_memory(self, content: str, metadata: Dict[str, Any], max_retries: int = 5):
        uid = hashlib.md5(f"{content}{metadata.get('timestamp', '')}".encode()).hexdigest()
        data = {"text": content, **metadata}
        document = (uid, data, None)
        
        if not self.index_path.parent.exists():
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        for attempt in range(max_retries):
            try:
                self.embeddings.upsert([document])
                self.embeddings.save(str(self.index_path))
                return
            except Exception as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise

    def index_documents(self, documents: List[Tuple[str, str, Dict[str, Any]]]):
        if not self.index_path.parent.exists():
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.embeddings.index(documents)
        self.embeddings.save(str(self.index_path))

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        import json
        
        safe_query = query.replace("'", "''")
        sql = f"SELECT id, text, score, data FROM txtai WHERE similar('{safe_query}') LIMIT {limit}"
        results = self.embeddings.search(sql)
        
        parsed_results = []
        for r in results:
            item = {
                "id": r["id"],
                "text": r["text"],
                "score": r["score"]
            }
            
            if "data" in r and r["data"]:
                try:
                    data_obj = json.loads(r["data"])
                    for k, v in data_obj.items():
                        if k != "text":
                            item[k] = v
                except Exception:
                    pass
                    
            parsed_results.append(item)
            
        return parsed_results
    
    async def search_async(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self.search, query, limit)
    
    async def index_memory_async(self, content: str, metadata: Dict[str, Any], max_retries: int = 3):
        async with self._index_lock:
            await asyncio.to_thread(self.index_memory, content, metadata, max_retries)
    
    async def index_documents_async(self, documents: List[Tuple[str, str, Dict[str, Any]]]):
        async with self._index_lock:
            await asyncio.to_thread(self.index_documents, documents)

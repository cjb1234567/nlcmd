from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from nlcmd.memory.store import MemoryStore


class TestMemoryStoreInit:
    def test_init_sets_paths(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        assert store.workspace == tmp_path.resolve()
        assert store.index_path == tmp_path / "memory" / "index"
        assert store.memory_root == tmp_path / "memory"


class TestListMemories:
    def test_list_empty_directory(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        result = store.list_memories("important")
        
        assert result == []

    def test_list_nonexistent_type(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        result = store.list_memories("nonexistent")
        
        assert result == []

    def test_list_returns_md_files(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        memory_dir = tmp_path / "memory" / "important"
        memory_dir.mkdir(parents=True)
        
        (memory_dir / "test1.md").touch()
        (memory_dir / "test2.md").touch()
        (memory_dir / "ignore.txt").touch()
        
        result = store.list_memories("important")
        
        assert sorted(result) == ["test1.md", "test2.md"]


class TestAppendMemory:
    def test_creates_new_file(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        file_path, full_entry, metadata = store.append_memory(
            "important", "user_preference", "Test content", "User preferences"
        )
        
        assert file_path.exists()
        assert file_path.name == "user_preference.md"
        assert "user_preference" in file_path.read_text(encoding="utf-8")
        assert "Test content" in file_path.read_text(encoding="utf-8")

    def test_appends_to_existing_file(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        store.append_memory("important", "test", "First content")
        file_path, _, _ = store.append_memory("important", "test", "Second content")
        
        content = file_path.read_text(encoding="utf-8")
        assert "First content" in content
        assert "Second content" in content

    def test_sanitizes_category_name(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        file_path, _, _ = store.append_memory("important", "test file@name!", "content")
        
        assert file_path.name == "test_file_name_.md"

    def test_creates_directory_structure(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        file_path, _, _ = store.append_memory("normal", "test", "content")
        
        assert file_path.parent.exists()
        assert file_path.parent.name == "normal"

    def test_writes_metadata_header_for_new_file(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        file_path, _, _ = store.append_memory("important", "my_category", "content", "My description")
        
        content = file_path.read_text(encoding="utf-8")
        assert "---" in content
        assert "Name: my_category" in content
        assert "Description: My description" in content
        assert "Created:" in content

    def test_no_metadata_header_for_existing_file(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        store.append_memory("important", "test", "First", "Description")
        file_path, _, _ = store.append_memory("important", "test", "Second")
        
        content = file_path.read_text(encoding="utf-8")
        assert content.count("---") == 2

    def test_returns_correct_metadata(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        _, full_entry, metadata = store.append_memory("important", "test_cat", "content")
        
        assert metadata["filename"] == "test_cat.md"
        assert metadata["type"] == "important"
        assert metadata["category"] == "test_cat"
        assert "timestamp" in metadata

    def test_default_description(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        file_path, _, _ = store.append_memory("important", "my_category", "content")
        
        content = file_path.read_text(encoding="utf-8")
        assert "Memories related to my_category" in content


class TestReindexAll:
    def test_calls_indexer_with_documents(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        memory_dir = tmp_path / "memory" / "important"
        memory_dir.mkdir(parents=True)
        
        file_path = memory_dir / "test.md"
        file_path.write_text("""---
Name: test
---
### [2024-01-01 10:00:00]
First entry

### [2024-01-02 11:00:00]
Second entry
""", encoding="utf-8")
        
        mock_indexer = MagicMock()
        
        store.reindex_all(mock_indexer)
        
        mock_indexer.index_documents.assert_called_once()
        args = mock_indexer.index_documents.call_args[0][0]
        assert len(args) == 2

    def test_handles_empty_directory(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        mock_indexer = MagicMock()
        
        store.reindex_all(mock_indexer)
        
        mock_indexer.index_documents.assert_not_called()

    def test_handles_both_types(self, tmp_path):
        store = MemoryStore(str(tmp_path))
        
        for mem_type in ["important", "normal"]:
            memory_dir = tmp_path / "memory" / mem_type
            memory_dir.mkdir(parents=True)
            file_path = memory_dir / f"{mem_type}.md"
            file_path.write_text(f"---\nName: {mem_type}\n---\n### [2024-01-01 10:00:00]\nEntry\n", encoding="utf-8")
        
        mock_indexer = MagicMock()
        
        store.reindex_all(mock_indexer)
        
        args = mock_indexer.index_documents.call_args[0][0]
        assert len(args) == 2

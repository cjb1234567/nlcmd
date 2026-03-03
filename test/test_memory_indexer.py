import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from nlcmd.memory.indexer import MemoryIndexer


class TestMemoryIndexerInit:
    def test_init_sets_index_path(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        
        indexer = MemoryIndexer(index_path)
        
        assert indexer.index_path == index_path
        assert indexer._embeddings is None


class TestEmbeddingsProperty:
    def test_raises_import_error_without_txtai(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        
        with patch("nlcmd.memory.indexer.Embeddings", None):
            indexer = MemoryIndexer(index_path)
            
            with pytest.raises(ImportError, match="txtai is not installed"):
                _ = indexer.embeddings

    def test_creates_embeddings_with_config(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            indexer._ensure_model = lambda: "test_model"
            result = indexer.embeddings
            
            assert result == mock_embeddings
            MockEmbeddings.assert_called_once()
            call_args = MockEmbeddings.call_args[0][0]
            assert call_args["path"] == "test_model"
            assert call_args["content"] is True
            assert call_args["hybrid"] is True

    def test_loads_existing_index(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.touch()
        
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            _ = indexer.embeddings
            
            mock_embeddings.load.assert_called_once_with(str(index_path))


class TestIndexMemory:
    def test_creates_index_directory(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            indexer.index_memory("test content", {"timestamp": "2024-01-01 10:00:00"})
            
            assert index_path.parent.exists()

    def test_generates_consistent_uid(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            content = "test content"
            metadata = {"timestamp": "2024-01-01 10:00:00"}
            
            expected_uid = hashlib.md5(f"{content}{metadata['timestamp']}".encode()).hexdigest()
            
            indexer.index_memory(content, metadata)
            
            upsert_args = mock_embeddings.upsert.call_args[0][0]
            assert upsert_args[0][0] == expected_uid

    def test_includes_metadata_in_document(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            metadata = {
                "filename": "test.md",
                "type": "important",
                "category": "test",
                "timestamp": "2024-01-01"
            }
            
            indexer.index_memory("content", metadata)
            
            upsert_args = mock_embeddings.upsert.call_args[0][0]
            doc_data = upsert_args[0][1]
            assert doc_data["text"] == "content"
            assert doc_data["filename"] == "test.md"
            assert doc_data["type"] == "important"

    def test_saves_after_upsert(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            indexer.index_memory("content", {})
            
            mock_embeddings.save.assert_called_once_with(str(index_path))

    def test_retries_on_database_locked(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.upsert.side_effect = [
            Exception("database is locked"),
            None
        ]
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            with patch("nlcmd.memory.indexer.time.sleep") as mock_sleep:
                
                indexer = MemoryIndexer(index_path)
                indexer.index_memory("content", {}, max_retries=3)
                
                assert mock_embeddings.upsert.call_count == 2
                mock_sleep.assert_called_once()

    def test_raises_after_max_retries(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.upsert.side_effect = Exception("database is locked")
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            with patch("nlcmd.memory.indexer.time.sleep"):
                
                indexer = MemoryIndexer(index_path)
                
                with pytest.raises(Exception, match="database is locked"):
                    indexer.index_memory("content", {}, max_retries=2)


class TestIndexDocuments:
    def test_creates_index_directory(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            documents = [("uid1", "text1", {"type": "important"})]
            
            indexer.index_documents(documents)
            
            assert index_path.parent.exists()

    def test_indexes_and_saves(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            documents = [
                ("uid1", "text1", {"type": "important"}),
                ("uid2", "text2", {"type": "normal"})
            ]
            
            indexer.index_documents(documents)
            
            mock_embeddings.index.assert_called_once_with(documents)
            mock_embeddings.save.assert_called_once_with(str(index_path))


class TestSearch:
    def test_search_returns_parsed_results(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.search.return_value = [
            {
                "id": "uid1",
                "text": "result text",
                "score": 0.95,
                "data": '{"category": "test", "type": "important"}'
            }
        ]
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            results = indexer.search("test query", limit=5)
            
            assert len(results) == 1
            assert results[0]["id"] == "uid1"
            assert results[0]["text"] == "result text"
            assert results[0]["score"] == 0.95
            assert results[0]["category"] == "test"
            assert results[0]["type"] == "important"

    def test_search_handles_malformed_data(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.search.return_value = [
            {
                "id": "uid1",
                "text": "result",
                "score": 0.8,
                "data": "invalid json"
            }
        ]
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            results = indexer.search("query")
            
            assert len(results) == 1
            assert results[0]["id"] == "uid1"
            assert "category" not in results[0]

    def test_search_escapes_quotes_in_query(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.search.return_value = []
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            indexer.search("test's query")
            
            call_sql = mock_embeddings.search.call_args[0][0]
            assert "test''s query" in call_sql

    def test_search_uses_limit(self, tmp_path):
        index_path = tmp_path / "memory" / "index"
        mock_embeddings = MagicMock()
        mock_embeddings.search.return_value = []
        
        with patch("nlcmd.memory.indexer.Embeddings") as MockEmbeddings:
            MockEmbeddings.return_value = mock_embeddings
            
            indexer = MemoryIndexer(index_path)
            indexer.search("query", limit=10)
            
            call_sql = mock_embeddings.search.call_args[0][0]
            assert "LIMIT 10" in call_sql

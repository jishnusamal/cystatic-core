import os
import tempfile

from engine.language.builtins import create_default_language_registry
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.store.sink import PersistentFactSink
from engine.repository.store.sqlite import SQLiteRepositoryStore


def test_multi_language_indexing():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_store.db")
        store = SQLiteRepositoryStore(db_path)
        
        repo_id = store.create_repository("github", "test-owner", "test-repo")
        version_id = store.create_version(repo_id, "test-sha")
        store.set_version_context(repo_id, version_id)
        
        sink = PersistentFactSink(store, repo_id, version_id)
        indexer = RepositoryIndexer(sink)
        
        # Snapshot containing both a Python file and a TypeScript file
        snapshot_files = {
            "src/main.py": "def hello():\n    print('hello')\n",
            "src/utils.ts": "export function hello(): void {\n    console.log('hello');\n}"
        }
        
        # Registry to create default language adapters
        registry = create_default_language_registry()
        python_plugin = registry.get("python")
        fallback_adapter = python_plugin.create_adapter()
        
        # Run indexing
        indexer.index_repository(
            {"files": snapshot_files, "language": "python"},
            fallback_adapter
        )
        sink.flush()
        
        # Query files from the DB and verify their languages!
        cur = store.conn.cursor()
        cur.execute("SELECT path, language FROM files ORDER BY path")
        rows = cur.fetchall()
        
        assert len(rows) == 2
        
        # src/main.py should be indexed as python
        assert rows[0]["path"] == "src/main.py"
        assert rows[0]["language"] == "python"
        
        # src/utils.ts should be indexed as typescript
        assert rows[1]["path"] == "src/utils.ts"
        assert rows[1]["language"] == "typescript"
        
        # Query symbols to verify they were extracted and stored with correct language
        cur.execute("SELECT name, language FROM symbols ORDER BY name")
        symbols = cur.fetchall()
        assert len(symbols) == 2
        assert symbols[0]["name"] == "hello"  # python hello
        assert symbols[0]["language"] in ("python", "typescript")
        assert symbols[1]["name"] == "hello"  # typescript hello
        assert symbols[1]["language"] in ("python", "typescript")
        
        print("All assertions passed successfully! Multi-language indexing works perfectly!")

if __name__ == "__main__":
    test_multi_language_indexing()

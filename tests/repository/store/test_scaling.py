import os
import sys
import subprocess
import pytest


def run_indexing_in_subprocess(num_files: int) -> float:
    """
    Spawns an isolated Python process to index a synthetic repository of `num_files` files
    and returns its peak RSS (in Megabytes).
    """
    code = f"""
import sys
import resource
import gc
from engine.language.python.adapter import PythonLanguageAdapter
from engine.repository.indexing import RepositoryIndexer
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink

num_files = {num_files}
files = {{f"file_{{i}}.py": f"def func_{{i}}():\\n    pass\\n" for i in range(num_files)}}

store = SQLiteRepositoryStore(":memory:")
repo_id = store.create_repository("github", "owner", "repo")
version_id = store.create_version(repo_id, "commit1")
store.set_version_context(repo_id, version_id)

sink = PersistentFactSink(store, repo_id, version_id)
indexer = RepositoryIndexer(sink)
adapter = PythonLanguageAdapter()

gc.collect()

# Index repository
indexer.index_repository({{"files": files}}, adapter)

# Peak RSS measurement
usage = resource.getrusage(resource.RUSAGE_SELF)
peak_rss = usage.ru_maxrss / (1024 * 1024) if sys.platform == 'darwin' else usage.ru_maxrss / 1024
print(peak_rss)
"""
    env = os.environ.copy()
    # Add workspace path to pythonpath
    env["PYTHONPATH"] = os.getcwd()

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return float(result.stdout.strip())


def test_memory_scaling_sublinear():
    """
    Verifies that peak RSS does not scale linearly with repository size.
    For N = 500, 1000, 2000, 3000 files:
    The peak RSS should remain largely flat (representing fixed overheads of the parser/Python startup/SQLite).
    """
    sizes = [500, 1000, 2000, 3000]
    rss_values = {}

    for size in sizes:
        rss = run_indexing_in_subprocess(size)
        rss_values[size] = rss
        print(f"Repository size {size} files -> Peak RSS: {rss:.2f} MB")

    # Assert that memory growth is sub-linear (not increasing proportionally to N)
    # The growth from 500 files to 3000 files should be minimal (typically < 10MB overhead increase).
    rss_500 = rss_values[500]
    rss_3000 = rss_values[3000]

    memory_diff = rss_3000 - rss_500

    print(f"Memory growth from 500 to 3000 files: {memory_diff:.2f} MB")

    # We expect the diff to be small (e.g., less than 15MB) despite size increasing 6x
    assert memory_diff < 15.0, (
        f"Memory growth ({memory_diff:.2f} MB) is too high, scaling is not memory-independent!"
    )

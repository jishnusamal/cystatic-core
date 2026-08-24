import asyncio
import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from integrations.base import RepositoryAcquisitionMode
from integrations.github.repositories import GitHubRepositoryProvider


async def main():
    # Use cystatichq/cystatic-core as the benchmark target
    repo = "cystatichq/cystatic-core"
    # A valid commit SHA from cystatic-core history
    commit_sha = "3ce820226db7a51284ae070a476aae0dec57d9ed"
    
    # Representative changed files
    changed_paths = [
        "core/config.py",
        "core/errors.py",
        "integrations/base/repository_provider.py",
    ]
    
    provider = GitHubRepositoryProvider(acquisition_mode=RepositoryAcquisitionMode.GIT)
    
    print(f"Starting Git-native acquisition benchmark for {repo} @ {commit_sha[:8]}...\n")
    
    try:
        commit = await provider.get_commit(repo, commit_sha)
        print(f"Repository: {commit.repository}")
        print(f"Commit: {commit.sha}")
        
        tree = await provider.get_tree(repo, commit_sha)
        total_entries = len(tree)
        files_count = len([e for e in tree if e.type == "blob"])
        print("\nTree:")
        print(f"  entries: {total_entries:,}")
        print(f"  files: {files_count:,}")
        
        # Find paths from our set that exist, or pick the first few files from the tree
        tree_paths = {e.path for e in tree if e.type == "blob"}
        paths_to_fetch = [p for p in changed_paths if p in tree_paths]
        if not paths_to_fetch:
            # Take a small batch of actual files from the tree for testing
            paths_to_fetch = [e.path for e in tree if e.type == "blob"][:10]
            
        print("\nRequested:")
        print(f"  files: {len(paths_to_fetch)}")
        
        blobs = await provider.get_files(repo, paths_to_fetch, commit_sha)
        total_bytes = sum(len(b.content) for b in blobs)
        
        print("\nRetrieved:")
        print(f"  files: {len(blobs)}")
        print(f"  bytes: {total_bytes / (1024 * 1024):.6f} MB ({total_bytes:,} bytes)")
        print("\nZIP:")
        print("  NOT USED")
        
    except Exception as e:  # noqa: BLE001 -- benchmark script reports and exits
        print(f"\nError running benchmark: {e}")
        print("\nNote: Make sure GITHUB_ACCESS_TOKEN is set in your environment if you hit rate limits/access denied.")

if __name__ == "__main__":
    asyncio.run(main())

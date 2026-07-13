"""Repository model storage abstraction.

Provides caching for compiled RepositoryModel instances to avoid
recompilation on every request.

Initially filesystem-based, designed for future database replacement.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from language_adapters.model import RepositoryModel


class RepositoryStore(ABC):
    """
    Abstract interface for repository model storage.
    
    Implementations can use filesystem, database, or any other backend.
    The pipeline depends only on this interface.
    """
    
    @abstractmethod
    async def load(self, repository: str, ref: str) -> RepositoryModel | None:
        """
        Load a cached repository model.
        
        Args:
            repository: Repository identifier (e.g., "owner/repo")
            ref: Git reference (branch, tag, or commit SHA)
            
        Returns:
            RepositoryModel if cached, None otherwise
        """
        pass
    
    @abstractmethod
    async def save(self, repository: str, ref: str, model: RepositoryModel) -> None:
        """
        Save a repository model to cache.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            model: Compiled RepositoryModel to cache
        """
        pass
    
    @abstractmethod
    async def exists(self, repository: str, ref: str) -> bool:
        """
        Check if a repository model is cached.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            
        Returns:
            True if cached, False otherwise
        """
        pass
    
    @abstractmethod
    async def invalidate(self, repository: str, ref: str | None = None) -> None:
        """
        Invalidate cached repository model(s).
        
        Args:
            repository: Repository identifier
            ref: Git reference, or None to invalidate all refs for the repository
        """
        pass
    
    @abstractmethod
    def _make_key(self, repository: str, ref: str) -> str:
        """
        Generate a cache key for a repository model.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            
        Returns:
            Cache key string
        """
        pass


class FilesystemRepositoryStore(RepositoryStore):
    """
    Filesystem-based repository model storage.
    
    Stores compiled models as pickle files in a cache directory.
    """
    
    def __init__(self, cache_dir: str | Path = ".cache/repositories") -> None:
        """
        Initialize the filesystem repository store.
        
        Args:
            cache_dir: Directory to store cached models
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _make_key(self, repository: str, ref: str) -> str:
        """Generate a filesystem-safe cache key."""
        # Use SHA256 to create a filesystem-safe key
        key_string = f"{repository}:{ref}"
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def _get_cache_path(self, repository: str, ref: str) -> Path:
        """Get the filesystem path for a cache entry."""
        key = self._make_key(repository, ref)
        return self.cache_dir / f"{key}.pkl"
    
    async def load(self, repository: str, ref: str) -> RepositoryModel | None:
        """
        Load a cached repository model from filesystem.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            
        Returns:
            RepositoryModel if cached and valid, None otherwise
        """
        cache_path = self._get_cache_path(repository, ref)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, "rb") as f:
                model = pickle.load(f)
            
            # Validate that we got a RepositoryModel
            if not isinstance(model, RepositoryModel):
                return None
            
            return model
        except Exception:
            # If we can't load the cache, treat it as a miss
            return None
    
    async def save(self, repository: str, ref: str, model: RepositoryModel) -> None:
        """
        Save a repository model to filesystem cache.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            model: RepositoryModel to cache
        """
        cache_path = self._get_cache_path(repository, ref)
        
        # Ensure parent directory exists
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write atomically using a temporary file
        temp_path = cache_path.with_suffix(".tmp")
        try:
            with open(temp_path, "wb") as f:
                pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
            temp_path.replace(cache_path)
        except Exception as exc:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            raise exc
    
    async def exists(self, repository: str, ref: str) -> bool:
        """
        Check if a repository model is cached.
        
        Args:
            repository: Repository identifier
            ref: Git reference
            
        Returns:
            True if cached, False otherwise
        """
        cache_path = self._get_cache_path(repository, ref)
        return cache_path.exists()
    
    async def invalidate(self, repository: str, ref: str | None = None) -> None:
        """
        Invalidate cached repository model(s).
        
        Args:
            repository: Repository identifier
            ref: Git reference, or None to invalidate all refs
        """
        if ref is not None:
            # Invalidate specific ref
            cache_path = self._get_cache_path(repository, ref)
            if cache_path.exists():
                cache_path.unlink()
        else:
            # Invalidate all refs for this repository
            # We need to find all cache files for this repository
            # Since we use hashed keys, we need to scan the directory
            # This is inefficient but acceptable for the initial implementation
            prefix = hashlib.sha256(f"{repository}:".encode()).hexdigest()
            for cache_file in self.cache_dir.glob(f"{prefix}*.pkl"):
                try:
                    cache_file.unlink()
                except Exception:
                    pass
    
    async def cleanup(self, max_age_days: int = 7) -> int:
        """
        Remove cache entries older than max_age_days.
        
        Args:
            max_age_days: Maximum age of cache entries in days
            
        Returns:
            Number of entries removed
        """
        import time
        
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        removed = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                if cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    removed += 1
            except Exception:
                pass
        
        return removed


class MemoryRepositoryStore(RepositoryStore):
    """
    In-memory repository model storage for testing.
    
    Not suitable for production - models are lost on restart.
    """
    
    def __init__(self) -> None:
        """Initialize the memory store."""
        self._cache: dict[str, RepositoryModel] = {}
    
    def _make_key(self, repository: str, ref: str) -> str:
        """Generate a cache key."""
        return f"{repository}:{ref}"
    
    async def load(self, repository: str, ref: str) -> RepositoryModel | None:
        """Load from memory cache."""
        key = self._make_key(repository, ref)
        return self._cache.get(key)
    
    async def save(self, repository: str, ref: str, model: RepositoryModel) -> None:
        """Save to memory cache."""
        key = self._make_key(repository, ref)
        self._cache[key] = model
    
    async def exists(self, repository: str, ref: str) -> bool:
        """Check if in memory cache."""
        key = self._make_key(repository, ref)
        return key in self._cache
    
    async def invalidate(self, repository: str, ref: str | None = None) -> None:
        """Invalidate memory cache."""
        if ref is not None:
            key = self._make_key(repository, ref)
            self._cache.pop(key, None)
        else:
            # Remove all entries for this repository
            prefix = f"{repository}:"
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cached models."""
        self._cache.clear()
from dataclasses import dataclass


@dataclass(frozen=True)
class MaterializationRequest:
    """Immutable request representing files to materialize for a repository commit."""
    repository_id: str
    commit_sha: str
    paths: tuple[str, ...]
    reason: str

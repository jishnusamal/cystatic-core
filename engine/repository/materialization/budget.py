from dataclasses import dataclass

class MaterializationBudgetExceeded(Exception):
    """Raised when the materialization request exceeds the allowed budget."""
    pass

@dataclass(frozen=True)
class MaterializationBudget:
    """Acquisition-related limits for repository materialization."""
    max_files: int
    max_bytes: int
    max_remote_requests: int

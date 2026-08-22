from .budget import (
    BudgetDecision,
    BudgetExceededReason,
    MaterializationBudget,
    MaterializationBudgetExceeded,
    ResolutionBudget,
    ResolutionConfig,
    ResolutionUsage,
)
from .full_index import FallbackResult, FullIndexFallback
from .materializer import MaterializationResult, RepositoryMaterializer, normalize_path
from .request import MaterializationRequest

__all__ = [
    # Phase 11 resolution budget types
    "ResolutionBudget",
    "ResolutionUsage",
    "BudgetDecision",
    "BudgetExceededReason",
    # Legacy alias
    "MaterializationBudget",
    "MaterializationBudgetExceeded",
    # Materialization
    "MaterializationResult",
    "MaterializationRequest",
    "RepositoryMaterializer",
    "normalize_path",
    # Phase 12 fallback
    "ResolutionConfig",
    "FullIndexFallback",
    "FallbackResult",
]


from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, cast
from core_engine.risk_flags import RiskEventType


def _jsonable(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())

    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)))

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_jsonable(item) for item in value]

    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]

    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]

    return value


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_repo_full_name(repo_full_name: str) -> tuple[str, str]:
    if "/" in repo_full_name:
        owner, name = repo_full_name.split("/", 1)
        return owner, name
    return repo_full_name, repo_full_name


def _confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _severity_for_category(category: str) -> str:
    category_upper = category.upper()
    if category_upper in {
        RiskEventType.BACKDOOR_INTRODUCED.value,
        RiskEventType.AUTH_BYPASS.value,
        RiskEventType.DATA_LEAK_RISK.value,
    }:
        return "CRITICAL"
    if category_upper in {
        RiskEventType.VALIDATION_REMOVED.value,
        RiskEventType.CRITICAL_DEPENDENCY_CHANGED.value,
        RiskEventType.FINANCIAL_LOGIC_CHANGE.value,
        RiskEventType.FINANCIAL_DATA_MODEL_CHANGE.value,
    }:
        return "HIGH"
    if category_upper in {
        RiskEventType.TAX_CALCULATION_CHANGE.value,
        RiskEventType.SCHEMA_MIGRATION.value,
        RiskEventType.DATA_BACKFILL.value,
        RiskEventType.STATE_INCONSISTENCY.value,
        RiskEventType.PERMISSION_REMOVED.value,
    }:
        return "MEDIUM"
    return "MEDIUM"

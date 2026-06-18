"""
Layer 4 — Constraint Compressor

Compresses system constraints into minimal boolean/string format.
No explanations, no text, no metadata.
"""
from __future__ import annotations

from typing import Any


def compress_constraints(
    constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compress system constraints for LLM payload.

    Args:
        constraints: Raw constraints dict from constraint_extractor.

    Returns:
        Minimal constraints dict with only essential fields.
    """
    if not constraints:
        return {
            "idempotency": "unknown",
            "transactions": "unknown",
            "retries": "unknown",
        }

    # Extract only the three core constraint types
    result = {
        "idempotency": "unknown",
        "transactions": "unknown",
        "retries": "unknown",
    }

    # Map constraint types to our three keys
    constraint_map = {
        "idempotency": "idempotency",
        "transaction": "transactions",
        "retry": "retries",
        "retries": "retries",
    }

    for key, value in constraints.items():
        key_lower = key.lower()
        for constraint_key, output_key in constraint_map.items():
            if constraint_key in key_lower:
                # Convert to simple boolean/string
                if isinstance(value, bool):
                    result[output_key] = value
                elif isinstance(value, str):
                    result[output_key] = value.lower() in ("true", "yes", "1", "enabled")
                elif isinstance(value, (int, float)):
                    result[output_key] = bool(value)
                else:
                    result[output_key] = "unknown"
                break

    return result
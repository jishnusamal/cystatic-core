"""Tests for Phase 4 — Constraint Layer (Constraint Extractor).

Verifies that extract_constraints produces structured constraints
from enriched files with:
  - Correct constraint types (idempotency, transaction, retry, etc.)
  - Proper severity classification
  - Accurate value detection (guaranteed, not_guaranteed, partial, unknown)
  - Financial operation detection (order/payment creation)
  - Transaction boundary detection
  - External dependency detection
  - Data consistency detection
  - Empty input handling
  - ConstraintSet serialization
"""
from __future__ import annotations

from core_engine.constraint_types import (
    Constraint,
    ConstraintSet,
    ConstraintSeverity,
    ConstraintType,
    ConstraintValue,
)
from core_engine.constraint_extractor import (
    ConstraintExtractor,
    extract_constraints,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_enriched_file(
    file_path: str = "services/checkout.py",
    added_lines: list[str] | None = None,
    removed_lines: list[str] | None = None,
    changed_functions: list[str] | None = None,
) -> dict:
    """Build a minimal enriched file dict with added/removed lines in hunks."""
    lines = []
    for line in (added_lines or []):
        lines.append({"line_type": "added", "content": line})
    for line in (removed_lines or []):
        lines.append({"line_type": "removed", "content": line})

    hunks = [{"lines": lines}] if lines else []

    functions = []
    for fn in (changed_functions or []):
        functions.append({"name": fn})

    return {
        "file_path": file_path,
        "lines_changed": len(added_lines or []) + len(removed_lines or []),
        "hunks": hunks,
        "changed_functions": functions,
        "total_functions_changed": len(functions),
        "total_endpoints": 0,
        "total_keyword_signals": 0,
        "endpoints": [],
        "keyword_signals": [],
        "flows": [],
        "risk_score": 0.0,
        "risk_level": "LOW",
    }


# ---------------------------------------------------------------------------
# 1. Empty input
# ---------------------------------------------------------------------------

def test_extract_constraints_empty_files() -> None:
    """Empty enriched_files returns empty ConstraintSet."""
    result = extract_constraints(enriched_files=[])
    assert isinstance(result, ConstraintSet)
    assert len(result.constraints) == 0


def test_extract_constraints_no_added_lines() -> None:
    """Enriched file with no added lines returns empty constraints."""
    file_data = _make_enriched_file(added_lines=[], changed_functions=["my_func"])
    result = extract_constraints(enriched_files=[file_data])
    assert len(result.constraints) == 0


# ---------------------------------------------------------------------------
# 2. ConstraintSet serialization
# ---------------------------------------------------------------------------

def test_constraint_set_to_dict() -> None:
    """ConstraintSet.to_dict() produces valid structure."""
    cs = ConstraintSet()
    cs.add(Constraint(
        constraint="test",
        type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.NOT_GUARANTEED,
        severity=ConstraintSeverity.HIGH,
        source="my_func",
        evidence="test evidence",
        file_path="test.py",
    ))
    d = cs.to_dict()
    assert "constraints" in d
    assert "total" in d
    assert "by_type" in d
    assert "critical_count" in d
    assert d["total"] == 1
    assert "idempotency" in d["by_type"]


def test_constraint_to_dict() -> None:
    """Constraint.to_dict() produces valid structure."""
    c = Constraint(
        constraint="order_creation",
        type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.NOT_GUARANTEED,
        severity=ConstraintSeverity.CRITICAL,
        source="_create_order_from_checkout",
        evidence="DB write without dedup",
        file_path="services/checkout.py",
    )
    d = c.to_dict()
    assert d["constraint"] == "order_creation"
    assert d["type"] == "idempotency"
    assert d["value"] == "not_guaranteed"
    assert d["severity"] == "critical"
    assert d["source"] == "_create_order_from_checkout"


# ---------------------------------------------------------------------------
# 3. Idempotency constraints — DB writes without dedup
# ---------------------------------------------------------------------------

def test_idempotency_gap_on_db_write_without_dedup() -> None:
    """DB write (save()) without dedup check → NOT_GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=["order.save()", "db.commit()"],
        changed_functions=["create_order"],
    )
    result = extract_constraints(enriched_files=[file_data])
    idemp_constraints = result.get_by_type(ConstraintType.IDEMPOTENCY)
    assert len(idemp_constraints) >= 1
    assert any(
        c.value == ConstraintValue.NOT_GUARANTEED
        for c in idemp_constraints
    )


def test_idempotency_partial_with_dedup() -> None:
    """DB write with get_or_create → PARTIAL guarantee."""
    file_data = _make_enriched_file(
        added_lines=["Order.objects.get_or_create(user_id=user.id)", "order.save()"],
        changed_functions=["create_order"],
    )
    result = extract_constraints(enriched_files=[file_data])
    idemp_constraints = result.get_by_type(ConstraintType.IDEMPOTENCY)
    assert any(
        c.value == ConstraintValue.PARTIAL
        for c in idemp_constraints
    )


def test_financial_operation_critical_idempotency() -> None:
    """Order/payment creation → CRITICAL idempotency constraint."""
    file_data = _make_enriched_file(
        added_lines=["order = Order.objects.create(total=amount)"],
        changed_functions=["_create_order_from_checkout"],
    )
    result = extract_constraints(enriched_files=[file_data])
    idemp_constraints = result.get_by_type(ConstraintType.IDEMPOTENCY)
    critical = [c for c in idemp_constraints if c.severity == ConstraintSeverity.CRITICAL]
    assert len(critical) >= 1
    assert critical[0].source == "_create_order_from_checkout"


def test_financial_operation_payment_critical() -> None:
    """Payment save() → CRITICAL idempotency constraint."""
    file_data = _make_enriched_file(
        added_lines=["payment = Payment.save(amount=100)"],
        changed_functions=["process_payment"],
    )
    result = extract_constraints(enriched_files=[file_data])
    idemp_constraints = result.get_by_type(ConstraintType.IDEMPOTENCY)
    critical = [c for c in idemp_constraints if c.severity == ConstraintSeverity.CRITICAL]
    assert len(critical) >= 1


# ---------------------------------------------------------------------------
# 4. Transaction boundary constraints
# ---------------------------------------------------------------------------

def test_multi_write_without_transaction() -> None:
    """Multiple DB writes without transaction → NOT_GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=[
            "order.save()",
            "payment.save()",
        ],
        changed_functions=["checkout"],
    )
    result = extract_constraints(enriched_files=[file_data])
    tx_constraints = result.get_by_type(ConstraintType.TRANSACTION_BOUNDARY)
    assert len(tx_constraints) >= 1
    assert any(
        c.value == ConstraintValue.NOT_GUARANTEED
        for c in tx_constraints
    )


def test_transaction_partial_without_rollback() -> None:
    """Transaction with atomic() but no explicit rollback → PARTIAL."""
    file_data = _make_enriched_file(
        added_lines=[
            "with transaction.atomic():",
            "order.save()",
            "payment.save()",
        ],
        changed_functions=["checkout"],
    )
    result = extract_constraints(enriched_files=[file_data])
    tx_constraints = result.get_by_type(ConstraintType.TRANSACTION_BOUNDARY)
    assert any(
        c.value == ConstraintValue.PARTIAL
        for c in tx_constraints
    )


def test_transaction_with_rollback() -> None:
    """Transaction with explicit rollback handling → GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=[
            "with transaction.atomic():",
            "order.save()",
            "transaction.rollback()",
        ],
        changed_functions=["checkout"],
    )
    result = extract_constraints(enriched_files=[file_data])
    tx_constraints = result.get_by_type(ConstraintType.TRANSACTION_BOUNDARY)
    assert any(
        c.value == ConstraintValue.GUARANTEED
        for c in tx_constraints
    )


def test_removed_transaction_boundary_critical() -> None:
    """Removing a transaction boundary → CRITICAL."""
    file_data = _make_enriched_file(
        added_lines=["order.save()"],
        removed_lines=["with transaction.atomic():", "order.save()"],
        changed_functions=["checkout"],
    )
    result = extract_constraints(enriched_files=[file_data])
    tx_constraints = result.get_by_type(ConstraintType.TRANSACTION_BOUNDARY)
    critical = [c for c in tx_constraints if c.severity == ConstraintSeverity.CRITICAL]
    assert len(critical) >= 1


# ---------------------------------------------------------------------------
# 5. Retry semantics constraints
# ---------------------------------------------------------------------------

def test_external_call_without_retry() -> None:
    """External API call without retry → NOT_GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=["response = requests.post('https://api.example.com/pay', json=data)"],
        changed_functions=["call_external_api"],
    )
    result = extract_constraints(enriched_files=[file_data])
    retry_constraints = result.get_by_type(ConstraintType.RETRY_SEMANTICS)
    assert len(retry_constraints) >= 1
    assert any(
        c.constraint == "external_call_retry"
        for c in retry_constraints
    )


def test_retry_with_side_effects_critical() -> None:
    """Retry logic with DB writes → CRITICAL."""
    file_data = _make_enriched_file(
        added_lines=[
            "@retry(max_retries=3)",
            "order.save()",
            "db.commit()",
        ],
        changed_functions=["create_order_with_retry"],
    )
    result = extract_constraints(enriched_files=[file_data])
    retry_constraints = result.get_by_type(ConstraintType.RETRY_SEMANTICS)
    critical = [c for c in retry_constraints if c.severity == ConstraintSeverity.CRITICAL]
    assert len(critical) >= 1


# ---------------------------------------------------------------------------
# 6. External dependency constraints
# ---------------------------------------------------------------------------

def test_payment_gateway_dependency() -> None:
    """Stripe call → CRITICAL external_dependency."""
    file_data = _make_enriched_file(
        added_lines=["stripe.Charge.create(amount=1000, currency='usd')"],
        changed_functions=["process_payment"],
    )
    result = extract_constraints(enriched_files=[file_data])
    ext_constraints = result.get_by_type(ConstraintType.EXTERNAL_DEPENDENCY)
    assert len(ext_constraints) >= 1
    assert ext_constraints[0].severity == ConstraintSeverity.CRITICAL


def test_external_api_dependency() -> None:
    """HTTP call → LOW external_dependency."""
    file_data = _make_enriched_file(
        added_lines=["response = requests.get('https://api.example.com/data')"],
        changed_functions=["fetch_data"],
    )
    result = extract_constraints(enriched_files=[file_data])
    ext_constraints = result.get_by_type(ConstraintType.EXTERNAL_DEPENDENCY)
    assert len(ext_constraints) >= 1
    assert ext_constraints[0].severity == ConstraintSeverity.LOW


def test_email_provider_dependency() -> None:
    """SendGrid call → MEDIUM external_dependency."""
    file_data = _make_enriched_file(
        added_lines=["sendgrid.send(email)"],
        changed_functions=["send_notification"],
    )
    result = extract_constraints(enriched_files=[file_data])
    ext_constraints = result.get_by_type(ConstraintType.EXTERNAL_DEPENDENCY)
    assert len(ext_constraints) >= 1
    assert ext_constraints[0].severity == ConstraintSeverity.MEDIUM


# ---------------------------------------------------------------------------
# 7. Schema version constraints
# ---------------------------------------------------------------------------

def test_migration_file_detected() -> None:
    """Migration file → schema_constraint."""
    file_data = _make_enriched_file(
        file_path="migrations/0003_add_tax_fields.py",
        added_lines=["def forward():", "add_column('orders', 'tax_total')"],
        changed_functions=["forward"],
    )
    result = extract_constraints(enriched_files=[file_data])
    schema_constraints = result.get_by_type(ConstraintType.SCHEMA_VERSION)
    assert len(schema_constraints) >= 1


def test_ddl_change_detected() -> None:
    """ALTER TABLE → schema_constraint."""
    file_data = _make_enriched_file(
        added_lines=["ALTER TABLE orders ADD COLUMN tax_total DECIMAL(10,2)"],
        changed_functions=["migration_forward"],
    )
    result = extract_constraints(enriched_files=[file_data])
    schema_constraints = result.get_by_type(ConstraintType.SCHEMA_VERSION)
    assert len(schema_constraints) >= 1


# ---------------------------------------------------------------------------
# 8. Data consistency constraints
# ---------------------------------------------------------------------------

def test_cache_write_without_invalidation() -> None:
    """Cache write without invalidation → NOT_GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=["cache.set('user_data', data)", "order.save()"],
        changed_functions=["update_user_data"],
    )
    result = extract_constraints(enriched_files=[file_data])
    dc_constraints = result.get_by_type(ConstraintType.DATA_CONSISTENCY)
    assert len(dc_constraints) >= 1


def test_db_and_cache_without_coordination() -> None:
    """Both DB and cache writes without invalidation → HIGH severity."""
    file_data = _make_enriched_file(
        added_lines=[
            "order.save()",
            "cache.set('order_' + str(order.id), order_data)",
        ],
        changed_functions=["create_order"],
    )
    result = extract_constraints(enriched_files=[file_data])
    dc_constraints = result.get_by_type(ConstraintType.DATA_CONSISTENCY)
    high = [c for c in dc_constraints if c.severity == ConstraintSeverity.HIGH]
    assert len(high) >= 1


# ---------------------------------------------------------------------------
# 9. State management constraints
# ---------------------------------------------------------------------------

def test_shared_state_mutation() -> None:
    """Cache write → shared_state_mutation constraint."""
    file_data = _make_enriched_file(
        added_lines=["cache.set('session_data', value)"],
        changed_functions=["update_session"],
    )
    result = extract_constraints(enriched_files=[file_data])
    state_constraints = result.get_by_type(ConstraintType.STATE_MANAGEMENT)
    assert len(state_constraints) >= 1


# ---------------------------------------------------------------------------
# 10. Ordering constraints
# ---------------------------------------------------------------------------

def test_queue_publish_without_ordering_key() -> None:
    """Queue publish without ordering key → NOT_GUARANTEED."""
    file_data = _make_enriched_file(
        added_lines=["queue.publish('order_created', data)"],
        changed_functions=["dispatch_event"],
    )
    result = extract_constraints(enriched_files=[file_data])
    ordering_constraints = result.get_by_type(ConstraintType.ORDERING_GUARANTEE)
    assert len(ordering_constraints) >= 1
    assert ordering_constraints[0].value == ConstraintValue.NOT_GUARANTEED


# ---------------------------------------------------------------------------
# 11. ConstraintSet helpers
# ---------------------------------------------------------------------------

def test_has_idempotency_gap_true() -> None:
    """has_idempotency_gap returns True when critical write lacks idempotency."""
    cs = ConstraintSet()
    cs.add(Constraint(
        constraint="order_creation",
        type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.NOT_GUARANTEED,
        severity=ConstraintSeverity.CRITICAL,
        source="_create_order",
    ))
    assert cs.has_idempotency_gap() is True


def test_has_idempotency_gap_false() -> None:
    """has_idempotency_gap returns False when no critical gaps."""
    cs = ConstraintSet()
    cs.add(Constraint(
        constraint="order_creation",
        type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.GUARANTEED,
        severity=ConstraintSeverity.LOW,
        source="_create_order",
    ))
    assert cs.has_idempotency_gap() is False


def test_get_critical() -> None:
    """get_critical returns only critical constraints."""
    cs = ConstraintSet()
    cs.add(Constraint(
        constraint="a", type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.NOT_GUARANTEED,
        severity=ConstraintSeverity.CRITICAL, source="x",
    ))
    cs.add(Constraint(
        constraint="b", type=ConstraintType.IDEMPOTENCY,
        value=ConstraintValue.UNKNOWN,
        severity=ConstraintSeverity.LOW, source="y",
    ))
    critical = cs.get_critical()
    assert len(critical) == 1
    assert critical[0].constraint == "a"


# ---------------------------------------------------------------------------
# 12. Realistic scenario — checkout with order creation
# ---------------------------------------------------------------------------

def test_realistic_checkout_scenario() -> None:
    """Full checkout flow: DB writes + payment + no dedup → multiple constraints."""
    file_data = _make_enriched_file(
        file_path="services/checkout.py",
        added_lines=[
            "order = Order.objects.create(total=total, user=user)",
            "payment = Payment.objects.create(order=order, amount=total)",
            "stripe.Charge.create(amount=total, currency='usd')",
            "cache.set(f'order_{order.id}', order_data)",
            "order.save()",
            "payment.save()",
        ],
        changed_functions=[
            "_create_order_from_checkout",
            "_process_payment",
        ],
    )
    result = extract_constraints(enriched_files=[file_data])

    # Should detect multiple constraint types
    constraint_types = {c.type for c in result.constraints}
    assert ConstraintType.IDEMPOTENCY in constraint_types
    assert ConstraintType.EXTERNAL_DEPENDENCY in constraint_types

    # Should have critical constraints for financial operations
    critical = result.get_critical()
    assert len(critical) >= 1

    # Should detect idempotency gap
    assert result.has_idempotency_gap() is True

    # Serialization should work
    d = result.to_dict()
    assert "constraints" in d
    assert d["total"] > 0
    assert d["critical_count"] >= 1

"""
Constraint Extractor — Phase 4

Extracts system constraints from static analysis + heuristics.
These constraints ground LLM reasoning in observable system properties
so it doesn't hallucinate about idempotency, transactions, retries, etc.

Input: enriched_files, risk_patterns, behavior_diffs (from the existing pipeline)
Output: ConstraintSet (serialized and fed to the LLM)

Heuristic detectors:
  - Idempotency: DB writes without dedup, order/payment creation without idemp keys
  - Transaction boundaries: commit/rollback patterns, nested transactions
  - Retry semantics: retry decorators, exponential backoff, safe-to-retry detection
  - External dependencies: HTTP clients, payment gateways, email providers
  - Schema versioning: migration files, schema version fields
  - Data consistency: cache invalidation patterns, shared state mutations
  - Ordering guarantees: queue publish ordering, sequential processing
  - State management: session/cache/shared mutable state
"""
from __future__ import annotations

import re
from typing import Any

from core_engine.constraint_types import (
    Constraint,
    ConstraintSet,
    ConstraintSeverity,
    ConstraintType,
    ConstraintValue,
)


class ConstraintExtractor:
    """
    Extracts system constraints from enriched files, risk patterns,
    and behavior diffs using static analysis heuristics.
    """

    # -----------------------------------------------------------------------
    # DB write patterns (for idempotency detection)
    # -----------------------------------------------------------------------
    _DB_WRITE_PATTERNS = (
        "save(", "insert(", "create(", "update(", "upsert(",
        "bulk_create(", "bulk_update(", ".save(", ".create(",
        "session.add(", "session.commit(", "db.commit(",
        ".objects.create(", ".objects.bulk_create(",
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "write(", "put(",
    )

    _DB_DEDUP_PATTERNS = (
        "get_or_create", "update_or_create", "upsert",
        "ON CONFLICT", "INSERT OR REPLACE", "MERGE INTO",
        "idempotency_key", "idempotent", "dedup",
        "already_exists", "duplicate", "conflict",
    )

    # -----------------------------------------------------------------------
    # Transaction patterns
    # -----------------------------------------------------------------------
    _TRANSACTION_BEGIN_PATTERNS = (
        "transaction.atomic", "transaction.begin", "BEGIN TRANSACTION",
        "db.transaction", "@transaction", "with transaction",
        "atomic(", "begin_nested", "savepoint",
    )

    _TRANSACTION_END_PATTERNS = (
        "transaction.commit", "commit()", "session.commit(",
        "db.commit(", ".commit(", "COMMIT",
    )

    _TRANSACTION_ROLLBACK_PATTERNS = (
        "transaction.rollback", "rollback()", "session.rollback(",
        "db.rollback(", ".rollback(", "ROLLBACK",
    )

    # -----------------------------------------------------------------------
    # Retry patterns
    # -----------------------------------------------------------------------
    _RETRY_PATTERNS = (
        "@retry", "retry(", "retries", "max_retries",
        "backoff", "exponential", "retry_count",
        "tenacity", "backoff_factor", "Retry-After",
        "should_retry", "is_retryable", "attempt(",
    )

    _RETRY_SAFE_PATTERNS = (
        "idempotency_key", "idempotent", "GET ", "HEAD ", "OPTIONS ",
        "read_only", "SELECT ",
    )

    # -----------------------------------------------------------------------
    # External dependency patterns
    # -----------------------------------------------------------------------
    _EXTERNAL_SERVICE_PATTERNS: dict[str, tuple[str, ...]] = {
        "payment_gateway": (
            "stripe.", "braintree.", "paypal.", "adyen.",
            "square.", "checkout.com", "worldpay",
        ),
        "email_provider": (
            "sendgrid.", "mailgun.", "ses.", "smtp",
            "email.send", "send_mail", "send_email",
        ),
        "sms_provider": (
            "twilio.", "sns.", "nexmo.", "vonage.",
        ),
        "cloud_storage": (
            "s3.", "gcs.", "azure.blob", "boto3.",
            "minio.", "storage.put", "upload_file",
        ),
        "queue_service": (
            "sqs.", "rabbitmq", "kafka.", "pubsub.",
            "celery.", "rq.", "huey.",
        ),
        "external_api": (
            "requests.get", "requests.post", "requests.put",
            "requests.delete", "httpx.", "aiohttp.",
            "urllib.request", "http.client",
        ),
    }

    # -----------------------------------------------------------------------
    # Schema version patterns
    # -----------------------------------------------------------------------
    _SCHEMA_VERSION_PATTERNS = (
        "schema_version", "db_version", "migration",
        "alembic", "flyway", "liquibase",
        "ALTER TABLE", "CREATE TABLE", "DROP COLUMN",
        "add_column", "remove_column", "rename_column",
        "version_field", "api_version", "v1", "v2",
    )

    # -----------------------------------------------------------------------
    # State management patterns
    # -----------------------------------------------------------------------
    _SHARED_STATE_PATTERNS = (
        "cache.", "redis.", "session[", "global ",
        "shared_state", "app.state", "config[",
        "memcache.", "shared_data", "SINGLETON",
    )

    _ORDERING_PATTERNS = (
        "queue.put", "publish(", "send_message",
        "dispatch(", "enqueue(", "produce(",
        "celery.send_task", "apply_async",
        "order_by", "sort(", "sorted(",
        "sequence", "sequential", "ordered",
    )

    def extract(
        self,
        enriched_files: list[dict],
        risk_patterns: list[Any] | None = None,
        behavior_diffs: list[Any] | None = None,
        causal_graph: Any | None = None,
    ) -> ConstraintSet:
        """
        Main entry point. Extracts all constraint types from the analysis data.

        Returns a ConstraintSet ready for LLM consumption.
        """
        constraint_set = ConstraintSet(
            extraction_metadata={
                "files_analyzed": len(enriched_files),
                "risk_patterns_count": len(risk_patterns or []),
                "behavior_diffs_count": len(behavior_diffs or []),
            }
        )

        # Collect all hunk lines and function names for pattern matching
        all_hunk_lines, all_functions, all_file_contexts = self._collect_analysis_data(
            enriched_files
        )

        # Extract each constraint type
        self._extract_idempotency_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_transaction_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_retry_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_external_dependency_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_schema_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_ordering_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_data_consistency_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )
        self._extract_state_management_constraints(
            constraint_set, enriched_files, all_hunk_lines, all_file_contexts,
        )

        return constraint_set

    # -----------------------------------------------------------------------
    # Data collection helpers
    # -----------------------------------------------------------------------

    def _collect_analysis_data(
        self, enriched_files: list[dict],
    ) -> tuple[list[str], list[str], list[dict[str, str]]]:
        """Collect hunk lines, function names, and file contexts from enriched files."""
        all_hunk_lines: list[str] = []
        all_functions: list[str] = []
        all_file_contexts: list[dict[str, str]] = []

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            hunks = file_data.get("hunks", []) or []
            changed_functions = file_data.get("changed_functions", []) or []

            for hunk in hunks:
                hunk_data = self._as_dict(hunk)
                for raw_line in hunk_data.get("lines", []) or []:
                    line_data = self._as_dict(raw_line)
                    content = str(line_data.get("content", "")).strip()
                    line_type = str(line_data.get("line_type", ""))
                    if content:
                        all_hunk_lines.append(content)
                        all_file_contexts.append({
                            "content": content,
                            "file_path": file_path,
                            "line_type": line_type,
                        })

            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    all_functions.append(name)

        return all_hunk_lines, all_functions, all_file_contexts

    def _get_added_lines(self, enriched_files: list[dict]) -> list[tuple[str, str]]:
        """Get only added lines with their file paths."""
        added: list[tuple[str, str]] = []
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            for hunk in file_data.get("hunks", []) or []:
                hunk_data = self._as_dict(hunk)
                for raw_line in hunk_data.get("lines", []) or []:
                    line_data = self._as_dict(raw_line)
                    if line_data.get("line_type") == "added":
                        content = str(line_data.get("content", "")).strip()
                        if content:
                            added.append((content, file_path))
        return added

    def _get_removed_lines(self, enriched_files: list[dict]) -> list[tuple[str, str]]:
        """Get only removed lines with their file paths."""
        removed: list[tuple[str, str]] = []
        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            for hunk in file_data.get("hunks", []) or []:
                hunk_data = self._as_dict(hunk)
                for raw_line in hunk_data.get("lines", []) or []:
                    line_data = self._as_dict(raw_line)
                    if line_data.get("line_type") == "removed":
                        content = str(line_data.get("content", "")).strip()
                        if content:
                            removed.append((content, file_path))
        return removed

    def _extract_function_from_context(self, file_path: str, content: str, enriched_files: list[dict]) -> str:
        """Try to extract the function name from file context."""
        for file_data in enriched_files:
            if str(file_data.get("file_path", "")) != file_path:
                continue
            for fn in file_data.get("changed_functions", []) or []:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                if name:
                    return name
        return file_path.split("/")[-1] if file_path else "unknown"

    # -----------------------------------------------------------------------
    # 4.1 Idempotency Constraints
    # -----------------------------------------------------------------------

    def _extract_idempotency_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect operations that write data without idempotency guarantees.

        Signals:
          - DB writes (save/insert/create) without dedup check
          - Order/payment creation without idempotency key
          - External calls without request dedup
        """
        added_lines = self._get_added_lines(enriched_files)
        has_dedup = False
        has_write = False
        write_locations: list[tuple[str, str]] = []

        # Check if any line contains dedup patterns
        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._DB_DEDUP_PATTERNS):
                has_dedup = True

        # Check for DB writes
        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._DB_WRITE_PATTERNS):
                has_write = True
                write_locations.append((content.strip(), file_path))

        # If there are writes but no dedup, flag idempotency gap
        if has_write and not has_dedup:
            for content, file_path in write_locations[:3]:  # cap at 3
                source = self._extract_function_from_context(file_path, content, enriched_files)
                constraint_set.add(Constraint(
                    constraint="write_operation",
                    type=ConstraintType.IDEMPOTENCY,
                    value=ConstraintValue.NOT_GUARANTEED,
                    severity=ConstraintSeverity.HIGH,
                    source=source,
                    evidence=f"DB write without dedup check: {content[:120]}",
                    file_path=file_path,
                ))
        elif has_write and has_dedup:
            # Writes exist with some dedup — partial guarantee
            for content, file_path in write_locations[:2]:
                source = self._extract_function_from_context(file_path, content, enriched_files)
                constraint_set.add(Constraint(
                    constraint="write_operation",
                    type=ConstraintType.IDEMPOTENCY,
                    value=ConstraintValue.PARTIAL,
                    severity=ConstraintSeverity.MEDIUM,
                    source=source,
                    evidence=f"DB write with partial dedup: {content[:120]}",
                    file_path=file_path,
                ))

        # Check for order/payment creation patterns specifically
        order_payment_keywords = (
            "order", "payment", "charge", "invoice", "checkout",
            "subscription", "billing", "payout",
        )
        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(kw in content_lower for kw in ("create", "save", "insert", "submit")):
                if any(kw in content_lower for kw in order_payment_keywords):
                    source = self._extract_function_from_context(file_path, content, enriched_files)
                    constraint_set.add(Constraint(
                        constraint="order_creation" if "order" in content_lower else "payment_operation",
                        type=ConstraintType.IDEMPOTENCY,
                        value=ConstraintValue.NOT_GUARANTEED,
                        severity=ConstraintSeverity.CRITICAL,
                        source=source,
                        evidence=f"Financial operation without idempotency: {content[:120]}",
                        file_path=file_path,
                    ))

    # -----------------------------------------------------------------------
    # 4.2 Transaction Boundary Constraints
    # -----------------------------------------------------------------------

    def _extract_transaction_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect transaction boundaries and their properties.

        Signals:
          - atomic() blocks, transaction.begin/commit/rollback
          - Nested transactions, savepoints
          - Multiple writes without explicit transaction
        """
        added_lines = self._get_added_lines(enriched_files)
        has_transaction = False
        has_rollback = False
        multi_write_without_transaction = False
        write_count = 0

        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._TRANSACTION_BEGIN_PATTERNS):
                has_transaction = True
            if any(p in content_lower for p in self._TRANSACTION_ROLLBACK_PATTERNS):
                has_rollback = True
            if any(p in content_lower for p in self._DB_WRITE_PATTERNS):
                write_count += 1

        # Multiple writes without explicit transaction
        if write_count >= 2 and not has_transaction:
            multi_write_without_transaction = True

        if multi_write_without_transaction:
            constraint_set.add(Constraint(
                constraint="multi_write_transaction",
                type=ConstraintType.TRANSACTION_BOUNDARY,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.HIGH,
                source="changed_code",
                evidence=f"{write_count} DB writes detected without explicit transaction boundary",
                file_path="",
            ))

        if has_transaction:
            severity = ConstraintSeverity.MEDIUM if has_rollback else ConstraintSeverity.LOW
            constraint_set.add(Constraint(
                constraint="transaction_boundary",
                type=ConstraintType.TRANSACTION_BOUNDARY,
                value=ConstraintValue.GUARANTEED if has_rollback else ConstraintValue.PARTIAL,
                severity=severity,
                source="changed_code",
                evidence="Transaction boundary detected" + (
                    " with rollback handling" if has_rollback else " without explicit rollback"
                ),
                file_path="",
            ))

        # Check for removed transaction boundaries
        removed_lines = self._get_removed_lines(enriched_files)
        for content, file_path in removed_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._TRANSACTION_BEGIN_PATTERNS):
                constraint_set.add(Constraint(
                    constraint="transaction_boundary_removed",
                    type=ConstraintType.TRANSACTION_BOUNDARY,
                    value=ConstraintValue.NOT_GUARANTEED,
                    severity=ConstraintSeverity.CRITICAL,
                    source=self._extract_function_from_context(file_path, content, enriched_files),
                    evidence=f"Transaction boundary removed: {content[:120]}",
                    file_path=file_path,
                ))

    # -----------------------------------------------------------------------
    # 4.3 Retry Semantics Constraints
    # -----------------------------------------------------------------------

    def _extract_retry_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect retry semantics and whether operations are safe to retry.

        Signals:
          - @retry decorators, retry() calls
          - Side effects that are NOT safe to retry (DB writes, payments)
          - Missing retry handling on external calls
        """
        added_lines = self._get_added_lines(enriched_files)
        has_retry = False
        has_non_retryable_write = False
        has_external_call = False

        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._RETRY_PATTERNS):
                has_retry = True
            if any(p in content_lower for p in self._DB_WRITE_PATTERNS):
                has_non_retryable_write = True
            if any(p in content_lower for p in (
                "requests.", "httpx.", "aiohttp.", "urllib.",
                "http.client", "stripe.", "boto3.",
            )):
                has_external_call = True

        # External calls without retry handling
        if has_external_call and not has_retry:
            constraint_set.add(Constraint(
                constraint="external_call_retry",
                type=ConstraintType.RETRY_SEMANTICS,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.MEDIUM,
                source="changed_code",
                evidence="External API call without retry handling",
                file_path="",
            ))

        # Side effects with retry but no idempotency = dangerous
        if has_retry and has_non_retryable_write:
            constraint_set.add(Constraint(
                constraint="retry_with_side_effects",
                type=ConstraintType.RETRY_SEMANTICS,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.CRITICAL,
                source="changed_code",
                evidence="Retry logic on code with DB writes — may cause duplicate operations",
                file_path="",
            ))

    # -----------------------------------------------------------------------
    # 4.4 External Dependency Constraints
    # -----------------------------------------------------------------------

    def _extract_external_dependency_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect external system calls and their failure modes.

        Signals:
          - Payment gateway calls (Stripe, Braintree)
          - Email/SMS providers
          - Cloud storage (S3, GCS)
          - Queue services
          - Generic HTTP clients
        """
        added_lines = self._get_added_lines(enriched_files)

        for dep_category, patterns in self._EXTERNAL_SERVICE_PATTERNS.items():
            for content, file_path in added_lines:
                content_lower = content.lower()
                if any(p in content_lower for p in patterns):
                    source = self._extract_function_from_context(file_path, content, enriched_files)

                    # Determine severity based on category
                    if dep_category == "payment_gateway":
                        severity = ConstraintSeverity.CRITICAL
                    elif dep_category in ("email_provider", "sms_provider"):
                        severity = ConstraintSeverity.MEDIUM
                    else:
                        severity = ConstraintSeverity.LOW

                    constraint_set.add(Constraint(
                        constraint=f"external_{dep_category}",
                        type=ConstraintType.EXTERNAL_DEPENDENCY,
                        value=ConstraintValue.UNKNOWN,  # We can't know SLA from code
                        severity=severity,
                        source=source,
                        evidence=f"External dependency ({dep_category}): {content[:120]}",
                        file_path=file_path,
                    ))
                    break  # One constraint per category

    # -----------------------------------------------------------------------
    # 4.5 Schema Version Constraints
    # -----------------------------------------------------------------------

    def _extract_schema_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect schema versioning usage and migration patterns.

        Signals:
          - Schema version fields in models
          - Migration files (alembic, flyway)
          - ALTER TABLE / CREATE TABLE statements
          - API version routing
        """
        added_lines = self._get_added_lines(enriched_files)
        has_migration = False
        has_schema_version = False

        for content, file_path in added_lines:
            content_lower = content.lower()
            file_lower = file_path.lower()

            # Check for migration files
            if "migration" in file_lower or "alembic" in file_lower:
                has_migration = True
                constraint_set.add(Constraint(
                    constraint="schema_migration",
                    type=ConstraintType.SCHEMA_VERSION,
                    value=ConstraintValue.UNKNOWN,
                    severity=ConstraintSeverity.HIGH,
                    source=self._extract_function_from_context(file_path, content, enriched_files),
                    evidence=f"Schema migration: {content[:120]}",
                    file_path=file_path,
                ))

            # Check for schema version fields
            if any(p in content_lower for p in ("schema_version", "db_version", "version_field")):
                has_schema_version = True

            # Check for DDL statements
            if any(p in content for p in ("ALTER TABLE", "CREATE TABLE", "DROP COLUMN", "add_column")):
                constraint_set.add(Constraint(
                    constraint="ddl_change",
                    type=ConstraintType.SCHEMA_VERSION,
                    value=ConstraintValue.UNKNOWN,
                    severity=ConstraintSeverity.HIGH,
                    source=self._extract_function_from_context(file_path, content, enriched_files),
                    evidence=f"DDL change: {content[:120]}",
                    file_path=file_path,
                ))

        if has_migration and not has_schema_version:
            constraint_set.add(Constraint(
                constraint="migration_without_version_field",
                type=ConstraintType.SCHEMA_VERSION,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.MEDIUM,
                source="changed_code",
                evidence="Schema migration without explicit version tracking",
                file_path="",
            ))

    # -----------------------------------------------------------------------
    # 4.6 Ordering Guarantee Constraints
    # -----------------------------------------------------------------------

    def _extract_ordering_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect ordering guarantees (or lack thereof) in async/queue operations.

        Signals:
          - Queue publish without ordering key
          - Async dispatch without sequence tracking
          - Event emission without ordering guarantees
        """
        added_lines = self._get_added_lines(enriched_files)
        has_queue_publish = False
        has_ordering_key = False

        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._ORDERING_PATTERNS):
                if any(p in content_lower for p in ("queue", "publish", "dispatch", "enqueue", "produce", "celery", "send_task")):
                    has_queue_publish = True
                    # Check for ordering key
                    if any(p in content_lower for p in ("key=", "order_key", "sequence", "partition_key", "routing_key")):
                        has_ordering_key = True

        if has_queue_publish and not has_ordering_key:
            constraint_set.add(Constraint(
                constraint="queue_ordering",
                type=ConstraintType.ORDERING_GUARANTEE,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.MEDIUM,
                source="changed_code",
                evidence="Queue publish without explicit ordering key",
                file_path="",
            ))

    # -----------------------------------------------------------------------
    # 4.7 Data Consistency Constraints
    # -----------------------------------------------------------------------

    def _extract_data_consistency_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect data consistency patterns — cache invalidation, shared state.

        Signals:
          - Cache writes without invalidation strategy
          - Multiple data stores written without coordination
          - Read-after-write on potentially stale data
        """
        added_lines = self._get_added_lines(enriched_files)
        has_cache_write = False
        has_cache_invalidation = False
        has_db_write = False

        invalidation_patterns = (
            "cache.delete", "cache.invalidate", "cache.clear",
            "evict", "invalidate", "expire", "cache.flush",
        )

        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._SHARED_STATE_PATTERNS):
                has_cache_write = True
            if any(p in content_lower for p in invalidation_patterns):
                has_cache_invalidation = True
            if any(p in content_lower for p in self._DB_WRITE_PATTERNS):
                has_db_write = True

        # Cache write without invalidation
        if has_cache_write and not has_cache_invalidation:
            constraint_set.add(Constraint(
                constraint="cache_invalidation",
                type=ConstraintType.DATA_CONSISTENCY,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.MEDIUM,
                source="changed_code",
                evidence="Cache/state write without explicit invalidation strategy",
                file_path="",
            ))

        # Both DB write and cache write without coordination
        if has_db_write and has_cache_write and not has_cache_invalidation:
            constraint_set.add(Constraint(
                constraint="db_cache_consistency",
                type=ConstraintType.DATA_CONSISTENCY,
                value=ConstraintValue.NOT_GUARANTEED,
                severity=ConstraintSeverity.HIGH,
                source="changed_code",
                evidence="Both DB and cache writes without coordinated invalidation",
                file_path="",
            ))

    # -----------------------------------------------------------------------
    # 4.8 State Management Constraints
    # -----------------------------------------------------------------------

    def _extract_state_management_constraints(
        self,
        constraint_set: ConstraintSet,
        enriched_files: list[dict],
        all_hunk_lines: list[str],
        all_file_contexts: list[dict[str, str]],
    ) -> None:
        """
        Detect shared mutable state patterns.

        Signals:
          - Global variables, singletons
          - Session state mutations
          - Class-level mutable state
        """
        added_lines = self._get_added_lines(enriched_files)
        has_shared_state = False

        for content, file_path in added_lines:
            content_lower = content.lower()
            if any(p in content_lower for p in self._SHARED_STATE_PATTERNS):
                has_shared_state = True
                # Check if it's a write to shared state
                if any(p in content_lower for p in ("=", "set(", "update(", "append(")):
                    source = self._extract_function_from_context(file_path, content, enriched_files)
                    constraint_set.add(Constraint(
                        constraint="shared_state_mutation",
                        type=ConstraintType.STATE_MANAGEMENT,
                        value=ConstraintValue.NOT_GUARANTEED,
                        severity=ConstraintSeverity.MEDIUM,
                        source=source,
                        evidence=f"Shared state mutation: {content[:120]}",
                        file_path=file_path,
                    ))
                    break  # One constraint for shared state mutations

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}


def extract_constraints(
    enriched_files: list[dict],
    risk_patterns: list[Any] | None = None,
    behavior_diffs: list[Any] | None = None,
    causal_graph: Any | None = None,
) -> ConstraintSet:
    """Convenience function for constraint extraction."""
    extractor = ConstraintExtractor()
    return extractor.extract(
        enriched_files=enriched_files,
        risk_patterns=risk_patterns,
        behavior_diffs=behavior_diffs,
        causal_graph=causal_graph,
    )

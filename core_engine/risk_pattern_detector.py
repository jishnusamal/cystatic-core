from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional
import re
from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]

from core_engine.risk_flags import FlowType, RiskEventType, SignalType

FLOW_SIGNAL_MAP: dict[FlowType, set[SignalType]] = {
    FlowType.AUTHENTICATION_FLOW: {
        SignalType.AUTH_SURFACE,
        SignalType.LOGIN_LOGOUT,
    },
    FlowType.PAYMENT_PROCESSING: {
        SignalType.PAYMENT_SURFACE,
    },
    FlowType.USER_MANAGEMENT: {
        SignalType.USER_INPUT,
    },
    FlowType.SESSION_HANDLING: {
        SignalType.SESSION_FLOW,
    },
}


class RiskEvent(BaseModel):
    type: RiskEventType
    file_path: Optional[str] = None
    function: Optional[str] = None
    flows: list[FlowType] = Field(default_factory=list)
    trigger: str
    reason: str
    confidence: float = 0.9


def detect_flows(file_data: dict) -> list[FlowType]:
    raw_signals = file_data.get("keyword_signals", []) or []
    signal_set: set[SignalType] = set()

    for signal in raw_signals:
        if isinstance(signal, dict):
            category = signal.get("category")
        elif hasattr(signal, "model_dump"):
            category = signal.model_dump().get("category")
        else:
            category = getattr(signal, "category", None)

        if isinstance(category, SignalType):
            signal_set.add(category)
            continue

        if isinstance(category, str):
            try:
                signal_set.add(SignalType(category))
            except ValueError:
                continue

    flows: list[FlowType] = []
    for flow, mapped_signals in FLOW_SIGNAL_MAP.items():
        if signal_set.intersection(mapped_signals):
            flows.append(flow)

    path = str(file_data.get("file_path", "")).lower()
    lines = _extract_changed_line_contents(file_data)
    joined = "\n".join(lines).lower()
    changed_functions = file_data.get("changed_functions", []) or []
    function_names = _extract_changed_function_names(changed_functions)

    # user_management heuristics:
    # - user-focused module paths
    # - explicit plan updates (e.g. "plan": "pro" -> "free")
    # - USERS map/table mutations
    if (
        "/users" in path
        or "user" in path
        or '"plan"' in joined
        or "users[" in joined
        or "users." in joined
        or "users =" in joined
    ):
        if FlowType.USER_MANAGEMENT not in flows:
            flows.append(FlowType.USER_MANAGEMENT)

    # auth file mutating identity state should map to both user and auth flows.
    auth_user_credential_literal = _has_user_credential_literal(lines)
    identity_mutation_tokens = (
        "users[",
        "users.",
        "users =",
        "credential",
        "credentials",
        "password",
        "role",
        "roles",
        "permission",
        "permissions",
    )
    if "auth" in path and (
        any(token in joined for token in identity_mutation_tokens)
        or auth_user_credential_literal
    ):
        if FlowType.AUTHENTICATION_FLOW not in flows:
            flows.append(FlowType.AUTHENTICATION_FLOW)
        if FlowType.USER_MANAGEMENT not in flows:
            flows.append(FlowType.USER_MANAGEMENT)

    # Payment flow should still resolve even when keyword signals are absent.
    payment_fn_markers = ("pay", "payment", "checkout", "charge")
    if (
        any(marker in path for marker in ("payment", "checkout", "billing", "invoice"))
        or any(any(marker in name for marker in payment_fn_markers) for name in function_names)
    ):
        if FlowType.PAYMENT_PROCESSING not in flows:
            flows.append(FlowType.PAYMENT_PROCESSING)

    # session_handling heuristics:
    # session["user_id"], cookie/cookies, JWT, access_token/refresh_token.
    session_tokens = (
        'session["user_id"]',
        "session.get(",
        "cookie",
        "cookies",
        "jwt",
        "access_token",
        "refresh_token",
    )
    if any(token in joined for token in session_tokens):
        if FlowType.SESSION_HANDLING not in flows:
            flows.append(FlowType.SESSION_HANDLING)

    return flows


def _extract_changed_line_contents(file_data: dict) -> list[str]:
    contents: list[str] = []
    for raw_hunk in file_data.get("hunks", []) or []:
        hunk = raw_hunk if isinstance(raw_hunk, dict) else (
            raw_hunk.model_dump() if hasattr(raw_hunk, "model_dump") else {}
        )
        for raw_line in hunk.get("lines", []) or []:
            line = raw_line if isinstance(raw_line, dict) else (
                raw_line.model_dump() if hasattr(raw_line, "model_dump") else {}
            )
            contents.append(str(line.get("content", "")))
    return contents


def _extract_changed_function_names(raw_functions: list[Any]) -> set[str]:
    names: set[str] = set()
    for raw_fn in raw_functions:
        if isinstance(raw_fn, dict):
            name = raw_fn.get("name")
        elif hasattr(raw_fn, "model_dump"):
            name = raw_fn.model_dump().get("name")
        else:
            name = getattr(raw_fn, "name", None)
        if isinstance(name, str) and name:
            names.add(name.lower())
    return names


def _has_user_credential_literal(lines: list[str]) -> bool:
    # Example: "malicious_user": "hackme"
    return any(
        re.search(r"""["'][^"']*user[^"']*["']\s*:\s*["'][^"']+["']""", line, re.IGNORECASE)
        is not None
        for line in lines
    )


class RiskPatternDetector:
    def detect(self, enriched_files: list[dict]) -> list[RiskEvent]:
        events: list[RiskEvent] = []

        for file_data in enriched_files:
            events.extend(self._detect_file(file_data))

        return self._dedupe(events)

    def _detect_file(self, file_data: dict) -> list[RiskEvent]:
        events: list[RiskEvent] = []

        file_path = str(file_data.get("file_path", ""))
        flows = detect_flows(file_data)
        keyword_signals = [self._as_dict(s) for s in file_data.get("keyword_signals", [])]
        signal_categories = {str(s.get("category")) for s in keyword_signals}

        changed_functions = [self._as_dict(f) for f in file_data.get("changed_functions", [])]
        function_names = {str(f.get("name")) for f in changed_functions if f.get("name")}

        login_required_fn = next(
            (f for f in changed_functions if str(f.get("name")) == "login_required"),
            None,
        )

        if SignalType.PAYMENT_SURFACE.value in signal_categories:
            if any(fn in {"pay", "checkout", "charge", "process_payment"} for fn in function_names):
                events.append(
                    RiskEvent(
                        type=RiskEventType.FINANCIAL_LOGIC_CHANGE,
                        file_path=file_path,
                        flows=flows,
                        trigger="payment surface signal matched changed payment function names",
                        reason="Payment-related function modified",
                        confidence=0.7,
                    )
                )

        removed_validation = any(
            (
                str(kw.get("category")) == SignalType.VALIDATION_LOGIC.value
                and str(kw.get("keyword")) == "validation_removal"
            )
            for kw in keyword_signals
        )
        if removed_validation:
            events.append(
                RiskEvent(
                    type=RiskEventType.VALIDATION_REMOVED,
                    file_path=file_path,
                    flows=flows,
                    trigger="validation_removal signal emitted from removed validation lines",
                    reason="Validation logic removed",
                    confidence=0.8,
                )
            )

        suspicious = any(
            str(kw.get("keyword", "")).lower() in {"hardcoded_admin", "hardcoded_password", "hardcoded_token"}
            for kw in keyword_signals
        )
        if suspicious:
            events.append(
                RiskEvent(
                    type=RiskEventType.BACKDOOR_INTRODUCED,
                    file_path=file_path,
                    flows=flows,
                    trigger="hardcoded credential keyword signal detected",
                    reason="Potential hardcoded credential detected",
                    confidence=0.8,
                )
            )

        hunks = [self._as_dict(h) for h in file_data.get("hunks", [])]
        lines = self._flatten_hunk_lines(hunks)
        removed_lines = [
            str(line.get("content", ""))
            for line in lines
            if line.get("line_type") == "removed"
        ]
        content_lines = [str(line.get("content", "")) for line in lines]

        if self._is_schema_migration_file(file_path) and self._has_schema_migration_indicators(content_lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.SCHEMA_MIGRATION,
                    file_path=file_path,
                    flows=flows,
                    trigger="migration file includes schema-altering operations",
                    reason="Database schema migration detected in changed file",
                    confidence=0.8,
                )
            )

        if self._is_schema_migration_file(file_path) and self._has_backfill_indicators(content_lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.DATA_BACKFILL,
                    file_path=file_path,
                    flows=flows,
                    trigger="migration contains update/execute backfill-style data rewrite",
                    reason="Migration appears to rewrite existing persisted data",
                    confidence=0.8,
                )
            )

        if self._has_tax_calculation_change(file_path, content_lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.TAX_CALCULATION_CHANGE,
                    file_path=file_path,
                    flows=flows,
                    trigger="tax-related calculation tokens changed in file or path context",
                    reason="Tax calculation or tax breakdown logic changed",
                    confidence=0.75,
                )
            )

        if self._has_invoice_rendering_change(file_path, content_lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.INVOICE_RENDERING_CHANGE,
                    file_path=file_path,
                    flows=flows,
                    trigger="invoice rendering/template tax presentation markers changed",
                    reason="Invoice rendering/tax presentation logic changed",
                    confidence=0.75,
                )
            )

        if self._has_financial_data_model_change(file_path, content_lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.FINANCIAL_DATA_MODEL_CHANGE,
                    file_path=file_path,
                    flows=flows,
                    trigger="financial model/schema tokens changed in modelish file",
                    reason="Financial data model fields changed",
                    confidence=0.7,
                )
            )

        if login_required_fn:
            change_type = str(login_required_fn.get("change_type", "modified"))
            if change_type == "deleted":
                events.append(
                    RiskEvent(
                        type=RiskEventType.AUTH_BYPASS,
                        file_path=file_path,
                        function="login_required",
                        flows=flows,
                        trigger="login_required function was deleted",
                        reason="Authorization guard was removed",
                        confidence=0.9,
                    )
                )
            elif change_type == "modified" and self._has_login_required_guard_weakening(removed_lines):
                events.append(
                    RiskEvent(
                        type=RiskEventType.PERMISSION_REMOVED,
                        file_path=file_path,
                        function="login_required",
                        flows=flows,
                        trigger="login_required modified and guard lines removed (session/redirect/if/return)",
                        reason="Authorization guard logic weakened",
                        confidence=0.75,
                    )
                )

        if self._has_auth_removal(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.AUTH_BYPASS,
                    file_path=file_path,
                    flows=flows,
                    trigger="removed auth guard/authenticate/Unauthorized lines in changed hunks",
                    reason="Authentication checks removed from protected flow",
                    confidence=0.95,
                )
            )

        if self._has_static_credential_addition(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.BACKDOOR_INTRODUCED,
                    file_path=file_path,
                    flows=flows,
                    trigger="added static user credential mapping pattern in diff line",
                    reason="Static credential-like user mapping added",
                    confidence=0.85,
                )
            )

        if self._is_payment_context(file_path, function_names) and self._has_return_status_flip(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.FINANCIAL_LOGIC_CHANGE,
                    file_path=file_path,
                    flows=flows,
                    trigger="payment-context return status lines changed between removed/added",
                    reason="Return status behavior changed",
                    confidence=0.8,
                )
            )

        if self._has_plan_downgrade(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.STATE_INCONSISTENCY,
                    file_path=file_path,
                    flows=flows,
                    trigger='removed `"plan":"pro"` with added `"plan":"free"` in changed lines',
                    reason="User plan downgraded in changed logic",
                    confidence=0.8,
                )
            )

        if self._has_validation_guard_removal(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.VALIDATION_REMOVED,
                    file_path=file_path,
                    flows=flows,
                    trigger="removed validation guard markers (`if not`, `raise`, or `authenticate`)",
                    reason="Validation/guard checks removed",
                    confidence=0.85,
                )
            )

        return events

    def _dedupe(self, events: list[RiskEvent]) -> list[RiskEvent]:
        seen: set[tuple[RiskEventType, Optional[str], Optional[str]]] = set()
        unique: list[RiskEvent] = []

        for event in events:
            key = (event.type, event.file_path, event.function)
            if key in seen:
                continue
            seen.add(key)
            unique.append(event)

        return unique

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if is_dataclass(value):
            return asdict(value) # pyright: ignore[reportArgumentType]
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

    def _flatten_hunk_lines(self, hunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for hunk in hunks:
            for line in hunk.get("lines", []) or []:
                flattened.append(self._as_dict(line))
        return flattened

    def _has_auth_removal(self, lines: list[dict[str, Any]]) -> bool:
        for line in lines:
            content = str(line.get("content", ""))
            if line.get("line_type") == "removed" and (
                "authenticate(" in content
                or "verify_api_key" in content
                or "login_required" in content
                or "Unauthorized" in content
            ):
                return True
        return False

    def _has_static_credential_addition(self, lines: list[dict[str, Any]]) -> bool:
        # Example: "malicious_user": "hackme"
        pattern = re.compile(
            r"""["'](?:[a-zA-Z0-9_]*user[a-zA-Z0-9_]*)["']\s*:\s*["'][^"']+["']"""
        )
        for line in lines:
            if line.get("line_type") != "added":
                continue
            content = str(line.get("content", ""))
            if pattern.search(content):
                return True
        return False

    def _has_return_status_flip(self, lines: list[dict[str, Any]]) -> bool:
        removed_status = {
            str(line.get("content", "")).strip()
            for line in lines
            if line.get("line_type") == "removed"
            and "return" in str(line.get("content", ""))
            and "status" in str(line.get("content", ""))
        }
        added_status = {
            str(line.get("content", "")).strip()
            for line in lines
            if line.get("line_type") == "added"
            and "return" in str(line.get("content", ""))
            and "status" in str(line.get("content", ""))
        }
        if not removed_status or not added_status:
            return False
        return removed_status != added_status

    def _has_plan_downgrade(self, lines: list[dict[str, Any]]) -> bool:
        removed_pro = any(
            line.get("line_type") == "removed" and '"plan"' in str(line.get("content", "")) and '"pro"' in str(line.get("content", ""))
            for line in lines
        )
        added_free = any(
            line.get("line_type") == "added" and '"plan"' in str(line.get("content", "")) and '"free"' in str(line.get("content", ""))
            for line in lines
        )
        return removed_pro and added_free

    def _has_validation_guard_removal(self, lines: list[dict[str, Any]]) -> bool:
        for line in lines:
            if line.get("line_type") != "removed":
                continue
            content = str(line.get("content", ""))
            if (
                "if not" in content
                or "raise " in content
                or "authenticate(" in content
            ):
                return True
        return False

    def _has_login_required_guard_weakening(self, removed_lines: list[str]) -> bool:
        joined_removed = "\n".join(removed_lines)
        markers = ("session.get", "redirect", "return", "if")
        return all(marker in joined_removed for marker in markers)

    def _is_payment_context(self, file_path: str, function_names: set[str]) -> bool:
        lowered_path = file_path.lower()
        path_markers = ("payment", "checkout", "billing", "invoice")
        if any(marker in lowered_path for marker in path_markers):
            return True

        fn_markers = ("pay", "payment", "checkout", "charge")
        lowered_fn_names = {name.lower() for name in function_names}
        return any(any(marker in fn for marker in fn_markers) for fn in lowered_fn_names)

    def _is_schema_migration_file(self, file_path: str) -> bool:
        lowered = file_path.lower()
        return "migration" in lowered or "/versions/" in lowered

    def _has_schema_migration_indicators(self, content_lines: list[str]) -> bool:
        joined = "\n".join(content_lines).lower()
        indicators = (
            "op.add_column",
            "op.alter_column",
            "op.create_table",
            "jsonb",
            "tax_breakdown",
        )
        return any(ind in joined for ind in indicators)

    def _has_backfill_indicators(self, content_lines: list[str]) -> bool:
        joined = "\n".join(content_lines).lower()
        indicators = (
            "update(",
            ".update(",
            "execute(",
            "backfill",
            "for row in",
        )
        financial_terms = ("tax", "checkout", "order", "wallet", "invoice")
        return any(ind in joined for ind in indicators) and any(term in joined for term in financial_terms)

    def _has_tax_calculation_change(self, file_path: str, content_lines: list[str]) -> bool:
        lowered_path = file_path.lower()
        joined = "\n".join(content_lines).lower()
        if "tax" not in joined and "tax" not in lowered_path:
            return False
        return any(
            term in joined
            for term in (
                "tax_breakdown",
                "tax_rate",
                "calculate_tax",
                "tax_amount",
                "vat",
            )
        )

    def _has_invoice_rendering_change(self, file_path: str, content_lines: list[str]) -> bool:
        lowered_path = file_path.lower()
        joined = "\n".join(content_lines).lower()
        invoice_path_hit = "invoice" in lowered_path and any(
            token in lowered_path for token in ("generator", "render", "template")
        )
        invoice_content_hit = "invoice" in joined and any(
            token in joined for token in ("render", "template", "line item", "tax_breakdown")
        )
        return invoice_path_hit or invoice_content_hit

    def _has_financial_data_model_change(self, file_path: str, content_lines: list[str]) -> bool:
        lowered_path = file_path.lower()
        joined = "\n".join(content_lines).lower()
        modelish_path = any(token in lowered_path for token in ("model", "schema", "entity", "migration"))
        model_tokens = ("tax_breakdown", "tax_amount", "checkout", "invoice", "wallet", "order")
        return modelish_path and any(token in joined for token in model_tokens)

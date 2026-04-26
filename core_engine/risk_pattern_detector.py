from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional
import re
from pydantic import BaseModel  # pyright: ignore[reportMissingImports]

from core_engine.risk_flags import RiskEventType, SignalType


class RiskEvent(BaseModel):
    type: RiskEventType
    file_path: Optional[str] = None
    function: Optional[str] = None
    reason: str
    confidence: float = 0.9


class RiskPatternDetector:
    def detect(self, enriched_files: list[dict]) -> list[RiskEvent]:
        events: list[RiskEvent] = []

        for file_data in enriched_files:
            events.extend(self._detect_file(file_data))

        return self._dedupe(events)

    def _detect_file(self, file_data: dict) -> list[RiskEvent]:
        events: list[RiskEvent] = []

        file_path = file_data.get("file_path")
        keyword_signals = [self._as_dict(s) for s in file_data.get("keyword_signals", [])]
        signal_categories = {str(s.get("category")) for s in keyword_signals}

        changed_functions = [self._as_dict(f) for f in file_data.get("changed_functions", [])]
        function_names = {str(f.get("name")) for f in changed_functions if f.get("name")}

        endpoints = [self._as_dict(e) for e in file_data.get("endpoints", [])]

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

        if login_required_fn:
            change_type = str(login_required_fn.get("change_type", "modified"))
            if change_type == "deleted":
                events.append(
                    RiskEvent(
                        type=RiskEventType.AUTH_BYPASS,
                        file_path=file_path,
                        function="login_required",
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
                        reason="Authorization guard logic weakened",
                        confidence=0.75,
                    )
                )

        if self._has_auth_removal(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.AUTH_BYPASS,
                    file_path=file_path,
                    reason="Authentication checks removed from protected flow",
                    confidence=0.95,
                )
            )

        if self._has_static_credential_addition(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.BACKDOOR_INTRODUCED,
                    file_path=file_path,
                    reason="Static credential-like user mapping added",
                    confidence=0.85,
                )
            )

        if self._has_return_status_flip(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.FINANCIAL_LOGIC_CHANGE,
                    file_path=file_path,
                    reason="Return status behavior changed",
                    confidence=0.8,
                )
            )

        if self._has_plan_downgrade(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.STATE_INCONSISTENCY,
                    file_path=file_path,
                    reason="User plan downgraded in changed logic",
                    confidence=0.8,
                )
            )

        if self._has_validation_guard_removal(lines):
            events.append(
                RiskEvent(
                    type=RiskEventType.VALIDATION_REMOVED,
                    file_path=file_path,
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
            return asdict(value)
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

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import re
from typing import Any, Optional

from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]

from core_engine.risk_flags import RiskEventType


class EntryPointImpact(BaseModel):
    route: str
    method: str | None = None
    file_path: str
    function: str | None = None
    reason: str
    risk_events: list[RiskEventType] = Field(default_factory=list)


class SystemImpactItem(BaseModel):
    area: str
    file_path: str
    reason: str


class EntryPointResolver:
    def resolve(self, enriched_files: list[dict], risk_patterns: list[Any]) -> list[EntryPointImpact]:
        risk_events_by_file = self._risk_events_by_file(risk_patterns)
        payment_fn_names = self._payment_function_names(enriched_files)

        impacts: list[EntryPointImpact] = []
        seen: set[tuple[str, str, str, str]] = set()

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", ""))
            file_risks = risk_events_by_file.get(file_path, set())
            changed_fn_names = self._changed_function_names(file_data)

            endpoint_candidates = self._collect_endpoint_candidates(file_data)

            for endpoint in endpoint_candidates:
                risk_events: set[RiskEventType] = set()
                reasons: list[str] = []

                endpoint_fn = endpoint.get("function")
                endpoint_method = endpoint.get("method")
                endpoint_route = endpoint.get("route")
                endpoint_calls = endpoint.get("called_functions", set())
                auth_removed_in_context = bool(endpoint.get("auth_removed"))
                validation_removed_in_context = bool(endpoint.get("validation_removed"))

                if endpoint_fn and endpoint_fn in changed_fn_names:
                    reasons.append("Endpoint handler function changed")

                if RiskEventType.AUTH_BYPASS in file_risks and auth_removed_in_context:
                    risk_events.add(RiskEventType.AUTH_BYPASS)
                    if endpoint_route and "pay" in endpoint_route:
                        reasons.append("Authentication guard removed from payment endpoint")
                    else:
                        reasons.append("Authentication guard removed from protected endpoint")

                if RiskEventType.VALIDATION_REMOVED in file_risks and validation_removed_in_context:
                    risk_events.add(RiskEventType.VALIDATION_REMOVED)
                    reasons.append("Validation guard removed near endpoint")

                if payment_fn_names.intersection(endpoint_calls):
                    risk_events.add(RiskEventType.FINANCIAL_LOGIC_CHANGE)
                    reasons.append("Endpoint calls modified payment processing function")
                elif RiskEventType.FINANCIAL_LOGIC_CHANGE in file_risks and endpoint_route and "pay" in endpoint_route:
                    risk_events.add(RiskEventType.FINANCIAL_LOGIC_CHANGE)
                    reasons.append("Payment endpoint behavior changed in touched file")

                # Only emit entry-point impacts when a real route is known.
                if not endpoint_route:
                    continue

                if not risk_events and not reasons:
                    continue

                reason = self._compose_reason(reasons)
                method = endpoint_method or "UNKNOWN"
                route = endpoint_route
                function_name = endpoint_fn or None
                key = (file_path, route, method, function_name or "")
                if key in seen:
                    continue
                seen.add(key)

                impacts.append(
                    EntryPointImpact(
                        route=route,
                        method=method,
                        file_path=file_path,
                        function=function_name,
                        reason=reason,
                        risk_events=sorted(risk_events, key=lambda x: x.value),
                    )
                )

        return impacts

    def resolve_system_impact(
        self,
        risk_patterns: list[Any],
        entry_points_affected: list[EntryPointImpact] | None = None,
    ) -> list[SystemImpactItem]:
        entry_points_affected = entry_points_affected or []
        entrypoint_files = {ep.file_path for ep in entry_points_affected}

        items: list[SystemImpactItem] = []
        seen: set[tuple[str, str, str]] = set()

        for risk in risk_patterns or []:
            risk_data = self._as_dict(risk)
            file_path = str(risk_data.get("file_path", "")).strip()
            if not file_path:
                continue

            # Route-less files should surface as system impact items.
            if file_path in entrypoint_files:
                continue

            reason = str(risk_data.get("reason", "")).strip() or "High-risk change detected"
            system_areas = risk_data.get("system_areas", []) or []
            if not system_areas:
                system_areas = ["unknown_area"]

            for area in system_areas:
                area_str = str(area).strip() or "unknown_area"
                key = (area_str, file_path, reason)
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    SystemImpactItem(
                        area=area_str,
                        file_path=file_path,
                        reason=reason,
                    )
                )

        return items

    def _compose_reason(self, reasons: list[str]) -> str:
        unique = []
        for reason in reasons:
            if reason not in unique:
                unique.append(reason)
        if not unique:
            return "Endpoint impacted by nearby high-risk changes"
        if len(unique) == 1:
            return unique[0]
        return "; ".join(unique)

    def _risk_events_by_file(self, risk_patterns: list[Any]) -> dict[str, set[RiskEventType]]:
        by_file: dict[str, set[RiskEventType]] = {}
        for risk in risk_patterns or []:
            data = self._as_dict(risk)
            file_path = str(data.get("file_path", ""))
            event_type = data.get("type")
            if not file_path:
                continue
            parsed = self._to_risk_event_type(event_type)
            if parsed is None:
                continue
            by_file.setdefault(file_path, set()).add(parsed)
        return by_file

    def _payment_function_names(self, enriched_files: list[dict]) -> set[str]:
        markers = ("pay", "payment", "checkout", "charge")
        names: set[str] = set()
        for file_data in enriched_files:
            for fn in file_data.get("changed_functions", []) or []:
                data = self._as_dict(fn)
                name = str(data.get("name", "")).strip()
                if not name:
                    continue
                base_name = name.split(".")[-1]
                lowered = base_name.lower()
                if any(marker in lowered for marker in markers):
                    names.add(base_name)
        return names

    def _changed_function_names(self, file_data: dict) -> set[str]:
        names: set[str] = set()
        for fn in file_data.get("changed_functions", []) or []:
            data = self._as_dict(fn)
            name = str(data.get("name", "")).strip()
            if not name:
                continue
            names.add(name)
            names.add(name.split(".")[-1])
        return names

    def _collect_endpoint_candidates(self, file_data: dict) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for ep in file_data.get("endpoints", []) or []:
            ep_data = self._as_dict(ep)
            candidates.append(
                {
                    "route": ep_data.get("route"),
                    "method": ep_data.get("method"),
                    "function": ep_data.get("function"),
                    "auth_removed": False,
                    "validation_removed": False,
                    "called_functions": set(),
                }
            )

        candidates.extend(self._extract_endpoints_from_hunk_context(file_data))
        return candidates

    def _extract_endpoints_from_hunk_context(self, file_data: dict) -> list[dict[str, Any]]:
        endpoint_pattern = re.compile(
            r"""^@[a-zA-Z_][a-zA-Z0-9_\.]*\.(get|post|put|delete|patch|options|head)\(\s*["']([^"']+)["']"""
        )
        def_pattern = re.compile(r"^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
        call_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

        endpoints: list[dict[str, Any]] = []

        for raw_hunk in file_data.get("hunks", []) or []:
            hunk = self._as_dict(raw_hunk)
            pending_method: Optional[str] = None
            pending_route: Optional[str] = None
            current_endpoint: Optional[dict[str, Any]] = None

            for raw_line in hunk.get("lines", []) or []:
                line = self._as_dict(raw_line)
                line_type = str(line.get("line_type", ""))
                content = str(line.get("content", "")).strip()

                ep_match = endpoint_pattern.match(content)
                if ep_match:
                    pending_method = ep_match.group(1).upper()
                    pending_route = ep_match.group(2)
                    continue

                def_match = def_pattern.match(content)
                if def_match:
                    if current_endpoint:
                        endpoints.append(current_endpoint)
                    fn_name = def_match.group(1)
                    current_endpoint = {
                        "route": pending_route,
                        "method": pending_method,
                        "function": fn_name,
                        "auth_removed": False,
                        "validation_removed": False,
                        "called_functions": set(),
                    }
                    pending_method = None
                    pending_route = None
                    continue

                if not current_endpoint:
                    continue

                if line_type == "removed":
                    if any(token in content for token in ("authenticate(", "verify_api_key", "login_required", "Unauthorized")):
                        current_endpoint["auth_removed"] = True
                    if any(token in content for token in ("if not", "raise ", "authenticate(")):
                        current_endpoint["validation_removed"] = True

                for call in call_pattern.findall(content):
                    if call not in {"if", "for", "while", "return", "raise"}:
                        current_endpoint["called_functions"].add(call)

            if current_endpoint:
                endpoints.append(current_endpoint)

        return endpoints

    def _to_risk_event_type(self, value: Any) -> RiskEventType | None:
        if isinstance(value, RiskEventType):
            return value
        if isinstance(value, str):
            try:
                return RiskEventType(value)
            except ValueError:
                return None
        return None

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if is_dataclass(value):
            return asdict(value) # pyright: ignore[reportArgumentType]
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}

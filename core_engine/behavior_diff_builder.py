from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class BehaviorDiff:
    symbol: str
    before: str
    after: str


class BehaviorDiffBuilder:
    """Build before/after behavior diffs from hunk-level code changes."""

    VALIDATION_MARKERS = (
        "raise ",
        "if not ",
        "assert ",
        "validate",
        "valueerror",
        "permission",
        "authenticate(",
        "authorize(",
    )
    AUTH_MARKERS = ("authenticate(", "authorize(", "login_required", "permission", "auth.")
    DOMAIN_REGIONS = (
        "checkout",
        "discount",
        "payment",
        "billing",
        "invoice",
        "auth",
        "authentication",
        "subscription",
        "order",
        "tax",
    )

    def build(self, enriched_files: list[dict]) -> list[BehaviorDiff]:
        diffs: list[BehaviorDiff] = []
        seen: set[str] = set()

        for file_data in enriched_files:
            file_path = str(file_data.get("file_path", "")).strip()
            if not file_path or self._is_test_file(file_path):
                continue

            changed_functions = file_data.get("changed_functions", []) or []
            hunk_lines = self._collect_hunk_lines(file_data)

            if not changed_functions:
                file_diff = self._build_file_level_diff(file_path, hunk_lines)
                if file_diff and file_diff.symbol not in seen:
                    seen.add(file_diff.symbol)
                    diffs.append(file_diff)
                continue

            for fn in changed_functions:
                fn_data = self._as_dict(fn)
                name = str(fn_data.get("name", "")).strip()
                change_type = str(fn_data.get("change_type", "modified")).strip()
                if not name:
                    continue

                symbol = name.split(".")[-1] if "." in name else name
                if symbol in seen:
                    continue

                removed, added = self._lines_for_function(
                    hunk_lines=hunk_lines,
                    fn_data=fn_data,
                )
                diff = self._build_symbol_diff(
                    symbol=symbol,
                    change_type=change_type,
                    removed=removed,
                    added=added,
                    file_path=file_path,
                )
                if diff:
                    seen.add(symbol)
                    diffs.append(diff)

        return diffs[:15]

    def _build_symbol_diff(
        self,
        symbol: str,
        change_type: str,
        removed: list[str],
        added: list[str],
        file_path: str,
    ) -> BehaviorDiff | None:
        if change_type == "added":
            after = self._summarize_lines(added) or f"new {symbol} logic introduced"
            return BehaviorDiff(
                symbol=symbol,
                before="(did not exist)",
                after=after,
            )

        if change_type == "deleted":
            before = self._summarize_lines(removed) or f"{symbol} implementation removed"
            return BehaviorDiff(
                symbol=symbol,
                before=before,
                after="(removed)",
            )

        if not removed and not added:
            return None

        before, after = self._infer_before_after(removed, added)
        if before == after:
            return None

        return BehaviorDiff(symbol=symbol, before=before, after=after)

    def _build_file_level_diff(self, file_path: str, hunk_lines: list[dict[str, Any]]) -> BehaviorDiff | None:
        removed = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "removed"]
        added = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "added"]
        if not removed and not added:
            return None

        region = self._region_from_path(file_path) or file_path.split("/")[-1]
        before, after = self._infer_before_after(removed, added)
        return BehaviorDiff(symbol=region, before=before, after=after)

    def _infer_before_after(self, removed: list[str], added: list[str]) -> tuple[str, str]:
        removed_text = "\n".join(removed).lower()
        added_text = "\n".join(added).lower()

        had_validation = any(marker in removed_text for marker in self.VALIDATION_MARKERS)
        has_validation = any(marker in added_text for marker in self.VALIDATION_MARKERS)
        if had_validation and not has_validation:
            return (
                self._summarize_lines(removed) or "validation guard present",
                self._summarize_lines(added) or "validation logic removed or bypassed",
            )

        had_auth = any(marker in removed_text for marker in self.AUTH_MARKERS)
        has_auth = any(marker in added_text for marker in self.AUTH_MARKERS)
        if had_auth and not has_auth:
            return (
                self._summarize_lines(removed) or "auth/permission check present",
                self._summarize_lines(added) or "auth/permission check removed or weakened",
            )

        removed_returns = self._extract_return_exprs(removed)
        added_returns = self._extract_return_exprs(added)
        if removed_returns and added_returns and removed_returns != added_returns:
            return (
                f"returned {removed_returns}",
                f"returned {added_returns}",
            )

        if removed and not added:
            return (
                self._summarize_lines(removed),
                "logic removed with no replacement in diff",
            )

        if added and not removed:
            return (
                "prior behavior not visible in diff",
                self._summarize_lines(added),
            )

        return self._summarize_lines(removed), self._summarize_lines(added)

    def _collect_hunk_lines(self, file_data: dict) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for hunk in file_data.get("hunks", []) or []:
            hunk_data = self._as_dict(hunk)
            for raw_line in hunk_data.get("lines", []) or []:
                line_data = self._as_dict(raw_line)
                content = str(line_data.get("content", "")).strip()
                if not content or content.startswith("#"):
                    continue
                lines.append(line_data)
        return lines

    def _lines_for_function(
        self,
        hunk_lines: list[dict[str, Any]],
        fn_data: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        start = fn_data.get("start_line")
        end = fn_data.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            removed = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "removed"]
            added = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "added"]
            return removed, added

        removed: list[str] = []
        added: list[str] = []
        for line in hunk_lines:
            line_no = line.get("source_line_no") or line.get("target_line_no")
            if isinstance(line_no, int):
                if line_no < start or line_no > end:
                    continue
            content = str(line.get("content", ""))
            if line.get("line_type") == "removed":
                removed.append(content)
            elif line.get("line_type") == "added":
                added.append(content)

        if not removed and not added:
            removed = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "removed"]
            added = [str(line.get("content", "")) for line in hunk_lines if line.get("line_type") == "added"]

        return removed, added

    def _summarize_lines(self, lines: list[str], max_lines: int = 3) -> str:
        meaningful = [line.strip() for line in lines if line.strip()]
        if not meaningful:
            return ""
        summary = "; ".join(meaningful[:max_lines])
        return summary[:220]

    def _extract_return_exprs(self, lines: list[str]) -> str:
        returns = []
        for line in lines:
            match = re.search(r"\breturn\b\s+(.+)$", line.strip())
            if match:
                returns.append(match.group(1).strip()[:80])
        return " / ".join(returns[:2])

    def _region_from_path(self, file_path: str) -> str:
        lowered = file_path.lower()
        for region in self.DOMAIN_REGIONS:
            if region in lowered:
                return region
        return ""

    def _is_test_file(self, file_path: str) -> bool:
        lowered = file_path.lower()
        return any(marker in lowered for marker in ("/tests/", "/test/", "/fixtures/", "/mocks/"))

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}


def build_behavior_diffs(enriched_files: list[dict]) -> list[BehaviorDiff]:
    return BehaviorDiffBuilder().build(enriched_files)

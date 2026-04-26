import ast
from typing import List, Tuple, Dict, Optional
from schemas import DiffIR, FunctionChanged, DiffHunk, DiffLine, KeywordDetected
import re
from enum import Enum
from core_engine.risk_flags import SignalType

class AnalysisMode(str, Enum):
    DIFF_ONLY = "diff_only"
    FULL_FILE = "full_file"


class PythonAdapter:
    """
    Lightweight semantic mapper.

    Modes:
    - DIFF_ONLY: no repo/file access required. Uses regex over DiffIR hunks.
    - FULL_FILE: repo/file access required. Uses AST over full file content.
    """

    def __init__(self):
        self.fastapi_endpoint_parser = FastAPIEndpointParser()
        self.flask_endpoint_parser = FlaskEndpointParser()
        self.keyword_signal_detector = PythonKeywordSignalDetector()

    # -----------------------------
    # File-level extraction
    # -----------------------------
    def extract_changed_files(
        self,
        unidiff: DiffIR
    ) -> List[Dict[str, object]]:

        return [
            {
                "file_path": f.file_path,
                "added_lines": f.added_lines,
                "removed_lines": f.removed_lines,
                "hunks": f.hunks,
                "has_additions": len(f.added_lines) > 0,
                "has_deletions": len(f.removed_lines) > 0,
                "lines_changed": len(f.added_lines) + len(f.removed_lines),
                "is_python": f.file_path.endswith(".py"),
            }
            for f in unidiff.files
            if f.file_path and f.file_path.endswith(".py")
        ]

    # -----------------------------
    # Hunk extraction
    # -----------------------------
    def extract_hunks(
        self,
        file: dict
    ) -> List[DiffHunk]:

        return file.get("hunks", [])

    # -----------------------------
    # Public function mapper
    # -----------------------------
    def extract_changed_functions(
        self,
        file: dict,
        mode: AnalysisMode = AnalysisMode.DIFF_ONLY,
        content: Optional[str] = None,
    ) -> List[FunctionChanged]:

        if mode == AnalysisMode.DIFF_ONLY:
            return self.extract_changed_functions_diff_only(file)

        if mode == AnalysisMode.FULL_FILE:
            if not content:
                raise ValueError("content is required when mode=AnalysisMode.FULL_FILE")

            return self.extract_changed_functions_full_file(
                file=file,
                content=content,
            )

        raise ValueError(f"Unsupported analysis mode: {mode}")

    # -----------------------------
    # DIFF_ONLY mode
    # Regex over hunks
    # -----------------------------
    def extract_changed_functions_diff_only(
        self,
        file: dict,
    ) -> List[FunctionChanged]:
        """
        Demo-safe mode.
        Uses only DiffIR hunks.
        Extracts top-level functions visible in the diff.
        """

        changed_functions: List[FunctionChanged] = []
        seen: set[tuple[str, str, str]] = set()

        for hunk in file.get("hunks", []):
            functions = self._get_top_level_functions_from_hunk_regex(hunk)

            for name, start, end, change_type in functions:
                key = (file["file_path"], name, change_type)

                if key in seen:
                    continue

                seen.add(key)

                changed_functions.append(
                    FunctionChanged(
                        name=name,
                        file_path=file["file_path"],
                        change_type=change_type, # pyright: ignore[reportArgumentType]
                        start_line=start,
                        end_line=end,
                    )
                )

        return changed_functions

    def _get_functions_from_hunk_regex(
        self,
        hunk: DiffHunk,
    ) -> List[Tuple[str, int, int]]:
        """
        Finds function definitions directly visible inside a diff hunk.

        Works well for:
        - added functions
        - deleted functions
        - modified functions where diff contains function context

        Limitation:
        - if hunk only contains inner body lines and no `def`, this may return nothing.
        """

        pattern = re.compile(
            r"^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        )

        functions: List[Tuple[str, int, int]] = []

        current_name: Optional[str] = None
        current_start: Optional[int] = None
        current_end: Optional[int] = None

        for line in hunk.lines:
            match = pattern.match(line.content)

            effective_line_no = (
                line.target_line_no
                if line.target_line_no and line.target_line_no != -1
                else line.source_line_no
            )

            if match:
                if current_name is not None and current_start is not None:
                    functions.append(
                        (
                            current_name,
                            current_start,
                            current_end or current_start,
                        )
                    )

                current_name = match.group(1)
                current_start = effective_line_no
                current_end = effective_line_no

            elif current_name is not None and effective_line_no and effective_line_no != -1:
                current_end = effective_line_no

        if current_name is not None and current_start is not None:
            functions.append(
                (
                    current_name,
                    current_start,
                    current_end or current_start,
                )
            )

        return functions

    # -----------------------------
    # FULL_FILE mode
    # AST over full file content
    # -----------------------------
    def extract_changed_functions_full_file(
        self,
        file: dict,
        content: str,
    ) -> List[FunctionChanged]:
        """
        Accurate mode.
        Requires full file content from PR head SHA.
        Uses AST to map changed target lines to function ranges.
        """

        changed_lines = self._get_changed_target_lines(file)

        functions = self._get_functions_ast(content)
        matched = self._map_changed_lines_to_functions(
            changed_lines=changed_lines,
            functions=functions,
        )

        return [
            FunctionChanged(
                name=name,
                file_path=file["file_path"],
                change_type="modified",
                start_line=start,
                end_line=end,
            )
            for name, start, end in matched
        ]
        
    def _get_top_level_functions_from_hunk_regex(
        self,
        hunk: DiffHunk,
    ) -> List[Tuple[str, int, int, str]]:
        """
        Diff-only function extraction.

        Rules:
        - only top-level functions: `def name(` or `async def name(`
        - excludes nested functions by requiring zero indentation
        - handles added, removed, and context function defs
        - prevents impossible ranges like 152–7
        """

        pattern = re.compile(
            r"^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        )

        functions: List[Tuple[str, int, int, str]] = []

        current_name: Optional[str] = None
        current_start: Optional[int] = None
        current_end: Optional[int] = None
        current_change_type: str = "modified"

        def flush_current():
            nonlocal current_name, current_start, current_end, current_change_type

            if current_name is None or current_start is None:
                return

            safe_end = current_end or current_start

            if safe_end < current_start:
                safe_end = current_start

            functions.append(
                (
                    current_name,
                    current_start,
                    safe_end,
                    current_change_type,
                )
            )

            current_name = None
            current_start = None
            current_end = None
            current_change_type = "modified"

        for line in hunk.lines:
            content = line.content

            # Skip diff metadata / no-newline messages
            if content.startswith(" No newline at end of file"):
                continue

            match = pattern.match(content)

            effective_line_no = self._effective_line_no_for_diff_line(line)

            if match:
                flush_current()

                current_name = match.group(1)
                current_start = effective_line_no
                current_end = effective_line_no

                if line.line_type == "added":
                    current_change_type = "added"
                elif line.line_type == "removed":
                    current_change_type = "deleted"
                else:
                    current_change_type = "modified"

                continue

            if current_name is not None:
                # Only extend range with same-side valid line numbers.
                next_line_no = self._effective_line_no_for_diff_line(
                    line,
                    preferred_change_type=current_change_type,
                )

                if next_line_no is not None and next_line_no >= current_start:
                    current_end = next_line_no

        flush_current()

        return functions
    
    def _effective_line_no_for_diff_line(
        self,
        line,
        preferred_change_type: str | None = None,
    ) -> Optional[int]:
        """
        Selects the right line number for diff-only mapping.

        - added functions use target_line_no
        - deleted functions use source_line_no
        - modified/context prefers target_line_no, then source_line_no
        """

        source = getattr(line, "source_line_no", None)
        target = getattr(line, "target_line_no", None)

        if source == -1:
            source = None

        if target == -1:
            target = None

        if preferred_change_type == "added":
            return target

        if preferred_change_type == "deleted":
            return source

        return target or source

    def _get_changed_target_lines(
        self,
        file: dict,
    ) -> set[int]:
        """
        For FULL_FILE mode, only target/new-file line numbers can be mapped
        against the fetched PR-head file content.

        Removed source lines do not exist in the new file, so we do not map them
        directly here.
        """

        added = file.get("added_lines", [])

        return {
            line
            for line in added
            if isinstance(line, int) and line > 0
        }

    def _get_functions_ast(
        self,
        content: str,
    ) -> List[Tuple[str, int, int]]:

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        functions: List[Tuple[str, int, int]] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", node.lineno)
                functions.append((node.name, start, end))

        return functions

    def _map_changed_lines_to_functions(
        self,
        changed_lines: set[int],
        functions: List[Tuple[str, int, int]],
    ) -> List[Tuple[str, int, int]]:

        matched: List[Tuple[str, int, int]] = []

        for name, start, end in functions:
            if any(start <= line <= end for line in changed_lines):
                matched.append((name, start, end))

        return matched

    # -----------------------------
    # Endpoint extraction
    # -----------------------------
    def extract_endpoints(
        self,
        file_path: str,
        content: str
    ) -> List[Dict]:
        fastapi_endpoints = self.fastapi_endpoint_parser.extract_endpoints(
            file_path=file_path,
            content=content
        )
        flask_endpoints = self.flask_endpoint_parser.extract_endpoints(
            file_path=file_path,
            content=content
        )

        return fastapi_endpoints + flask_endpoints

    def extract_endpoints_from_diff_only(
        self,
        file: dict,
    ) -> List[Dict]:
        fastapi_endpoints = self.fastapi_endpoint_parser.extract_endpoints_from_diff_only(
            file=file
        )
        flask_endpoints = self.flask_endpoint_parser.extract_endpoints_from_diff_only(
            file=file
        )

        return fastapi_endpoints + flask_endpoints

    def extract_keyword_signals_from_diff(
        self,
        file: dict,
    ) -> List[KeywordDetected]:
        return self.keyword_signal_detector.extract_keyword_signals_from_diff(file=file)

##-----------------------------
# Endpoint extraction logic (bonus)
##-----------------------------

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

AUTH_PATTERN = re.compile(
    r"\b(auth|authenticate|authorization|permission|acl|rbac|jwt|token)\b",
    re.IGNORECASE,
)
PAYMENT_PATTERN = re.compile(
    r"\b(payment|pay|billing|invoice|charge|stripe|refund|checkout)\b",
    re.IGNORECASE,
)
LOGIN_LOGOUT_PATTERN = re.compile(
    r"\b(login|logout|sign[_\-\s]?in|sign[_\-\s]?out)\b",
    re.IGNORECASE,
)
SESSION_PATTERN = re.compile(
    r"\b(session|user_id|cookie|csrf|access_token|refresh_token)\b",
    re.IGNORECASE,
)
VALIDATION_REMOVAL_PATTERN = re.compile(
    r"\b(validate|validation|validator|schema|assert|is_valid|clean)\b"
    r"|raise\s+(ValueError|TypeError|HTTPException)\b",
    re.IGNORECASE,
)


class FastAPIEndpointParser:
    def extract_endpoints(self, file_path: str, content: str) -> List[Dict]:
        if not self._is_fastapi_file(content):
            return []

        tree = ast.parse(content)

        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                endpoint = self._parse_function(node, file_path)
                if endpoint:
                    endpoints.append(endpoint)

        return endpoints

    # -----------------------------
    # FastAPI detection
    # -----------------------------
    def _is_fastapi_file(self, content: str) -> bool:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False

        for node in ast.walk(tree):

            # import fastapi
            if isinstance(node, ast.ImportFrom):
                if node.module == "fastapi":
                    return True

            # decorator-based heuristic
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr in HTTP_METHODS:
                            return True

        return False

    def _parse_function(self, node: ast.FunctionDef, file_path: str) -> Optional[Dict]:
        for decorator in node.decorator_list:
            method, route = self._extract_route(decorator)

            if method and route:
                return {
                    "file": file_path,
                    "function": node.name,
                    "method": method.upper(),
                    "route": route,
                }

        return None

    def _extract_route(self, decorator: ast.expr) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            method = decorator.func.attr

            if method in HTTP_METHODS:
                route = self._get_route_from_args(decorator)
                return method, route

        return None, None

    def _get_route_from_args(self, decorator: ast.Call) -> Optional[str]:
        if not decorator.args:
            return None

        arg = decorator.args[0]

        if isinstance(arg, ast.Constant):
            if isinstance(arg.value, str):
                return arg.value
            return None


        return None

    def extract_endpoints_from_diff_only(
        self,
        file: dict,
    ) -> List[Dict]:
        """
        Extract FastAPI-style routes from diff hunks without full file access.

        Example:
        @router.get("/users")
        async def list_users():
        """
        endpoints: List[Dict] = []
        seen: set[tuple[str, str, str]] = set()

        decorator_pattern = re.compile(
            r"""^@[a-zA-Z_][a-zA-Z0-9_\.]*\.(get|post|put|delete|patch|options|head)\(\s*["']([^"']+)["']"""
        )
        def_pattern = re.compile(
            r"^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        )

        for hunk in file.get("hunks", []):
            pending_method: Optional[str] = None
            pending_route: Optional[str] = None

            for line in hunk.lines:
                if line.line_type not in {"added", "context"}:
                    continue

                content = line.content.strip()

                decorator_match = decorator_pattern.match(content)
                if decorator_match:
                    pending_method = decorator_match.group(1).upper()
                    pending_route = decorator_match.group(2)
                    continue

                def_match = def_pattern.match(content)
                if def_match and pending_method and pending_route:
                    function_name = def_match.group(1)
                    key = (function_name, pending_method, pending_route)

                    if key not in seen:
                        seen.add(key)
                        endpoints.append(
                            {
                                "file": file["file_path"],
                                "function": function_name,
                                "method": pending_method,
                                "route": pending_route,
                            }
                        )

                    pending_method = None
                    pending_route = None

        return endpoints


class FlaskEndpointParser:
    def extract_endpoints(self, file_path: str, content: str) -> List[Dict]:
        if not self._is_flask_file(content):
            return []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                endpoint = self._parse_function(node, file_path)
                if endpoint:
                    endpoints.append(endpoint)

        return endpoints

    def _is_flask_file(self, content: str) -> bool:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "flask":
                    return True

            if isinstance(node, ast.Import):
                if any(alias.name == "flask" for alias in node.names):
                    return True

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr == "route":
                            return True

        return False

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str
    ) -> Optional[Dict]:
        for decorator in node.decorator_list:
            route, methods = self._extract_route_and_methods(decorator)

            if route:
                return {
                    "file": file_path,
                    "function": node.name,
                    "method": ",".join(methods),
                    "route": route,
                }

        return None

    def _extract_route_and_methods(
        self,
        decorator: ast.expr
    ) -> Tuple[Optional[str], List[str]]:
        if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
            return None, []

        if decorator.func.attr != "route":
            return None, []

        route = self._get_route_from_args(decorator)
        methods = self._get_methods_from_keywords(decorator)

        return route, methods

    def _get_route_from_args(self, decorator: ast.Call) -> Optional[str]:
        if not decorator.args:
            return None

        arg = decorator.args[0]

        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value

        return None

    def _get_methods_from_keywords(self, decorator: ast.Call) -> List[str]:
        for kw in decorator.keywords:
            if kw.arg != "methods":
                continue

            if isinstance(kw.value, (ast.List, ast.Tuple)):
                methods: List[str] = []
                for elt in kw.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        method = elt.value.lower()
                        if method in HTTP_METHODS:
                            methods.append(method.upper())

                if methods:
                    return methods

        return ["GET"]
    
    def extract_endpoints_from_diff_only(
        self,
        file: dict,
    ) -> List[Dict]:
        """
        Extract Flask-style routes from diff hunks without full file access.

        Example:
        @app.route("/login", methods=["GET", "POST"])
        def login():
        """

        endpoints: List[Dict] = []
        seen: set[tuple[str, str]] = set()

        route_pattern = re.compile(
            r"""^@app\.route\(\s*["']([^"']+)["'](?:,\s*methods=\[([^\]]+)\])?"""
        )

        def_pattern = re.compile(
            r"^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        )

        for hunk in file.get("hunks", []):
            pending_route: Optional[str] = None
            pending_methods: str = "GET"

            for line in hunk.lines:
                if line.line_type not in {"added", "context"}:
                    continue

                content = line.content.strip()

                route_match = route_pattern.match(content)
                if route_match:
                    pending_route = route_match.group(1)

                    raw_methods = route_match.group(2)
                    if raw_methods:
                        methods = re.findall(r"""["']([A-Z]+)["']""", raw_methods)
                        pending_methods = ",".join(methods) if methods else "GET"
                    else:
                        pending_methods = "GET"

                    continue

                def_match = def_pattern.match(content)
                if def_match and pending_route:
                    function_name = def_match.group(1)

                    key = (function_name, pending_route)
                    if key not in seen:
                        seen.add(key)
                        endpoints.append(
                            {
                                "file": file["file_path"],
                                "function": function_name,
                                "method": pending_methods,
                                "route": pending_route,
                            }
                        )

                    pending_route = None
                    pending_methods = "GET"

        return endpoints


class PythonKeywordSignalDetector:
    def __init__(self):
        self._auth_pattern = AUTH_PATTERN
        self._payment_pattern = PAYMENT_PATTERN
        self._login_logout_pattern = LOGIN_LOGOUT_PATTERN
        self._validation_removal_pattern = VALIDATION_REMOVAL_PATTERN

    def extract_keyword_signals_from_diff(
        self,
        file: dict,
    ) -> List[KeywordDetected]:
        signals: List[KeywordDetected] = []
        seen: set[tuple[str, str, int | None, str]] = set()

        for hunk in file.get("hunks", []):
            for line in hunk.lines:
                content = line.content
                line_type = line.line_type
                line_number = self._line_number(line)

                matches = self._extract_risk_matches(content=content, line_type=line_type)

                for keyword, signal_type, confidence in matches:
                    key = (file["file_path"], keyword, line_number, line_type)
                    if key in seen:
                        continue

                    seen.add(key)
                    signals.append(
                        KeywordDetected(
                            keyword=keyword,
                            category=signal_type,
                            file_path=file["file_path"],
                            line_number=line_number,
                            confidence=confidence,
                        )
                    )

        return signals

    def _line_number(self, line: DiffLine) -> int | None:
        if line.target_line_no and line.target_line_no > 0:
            return line.target_line_no
        if line.source_line_no and line.source_line_no > 0:
            return line.source_line_no
        return None

    def _extract_risk_matches(
        self,
        content: str,
        line_type: str,
    ) -> List[tuple[str, SignalType, float]]:
        matches: List[tuple[str, SignalType, float]] = []

        if self._auth_pattern.search(content):
            matches.append(("auth", SignalType.AUTH_SURFACE, 0.9))

        if self._payment_pattern.search(content):
            matches.append(
                ("payment", SignalType.PAYMENT_SURFACE, 0.9)
            )

        if self._login_logout_pattern.search(content):
            matches.append(
                ("login_logout", SignalType.LOGIN_LOGOUT, 0.9)
            )

        # Keep removal-specific behavior while standardizing category to SignalType.
        if line_type == "removed" and self._validation_removal_pattern.search(content):
            matches.append(
                ("validation_removal", SignalType.VALIDATION_LOGIC, 0.98)
            )

        return matches
import ast
from typing import List, Tuple, Dict, Optional
from source_adapters.github_adapter import DiffIR


class PythonAdapter:
    """
    Lightweight semantic mapper:
    - Takes full file content
    - Maps changed lines → function names
    """
    def __init__(self):
        self.endpoint_parser = FastAPIEndpointParser()
        
    def extract_changed_files(
        self,
        unidiff: DiffIR
    ) -> List[Dict[str, object]]:
        """
        Returns enriched file descriptors for downstream use.
        """

        files = unidiff.files

        return [
            {
                "file_path": f.file_path,
                "added_lines": f.added_lines,
                "removed_lines": f.removed_lines,
                "has_additions": len(f.added_lines) > 0,
                "has_deletions": len(f.removed_lines) > 0,
                "change_intensity": len(f.added_lines) + len(f.removed_lines),
                "is_python": f.file_path.endswith(".py"),
            }
            for f in files
            if f.file_path and f.file_path.endswith(".py")
        ]
    
    def extract_changed_functions(
        self,
        file: dict,         
        content: str
    ) -> List[str]:

        added = file.get("added_lines", [])
        removed = file.get("removed_lines", [])

        changed_lines = set(added + removed)

        functions = self._get_functions(content)

        return self._map(changed_lines, functions)

    # -----------------------------
    # AST extraction
    # -----------------------------
    def _get_functions(self, content: str) -> List[Tuple[str, int, int]]:
        tree = ast.parse(content)

        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                start = node.lineno
                end = getattr(node, "end_lineno", node.lineno)

                functions.append((node.name, start, end))

        return functions
    
    # -----------------------------
    # Extract FASTAPI endpoints if applicable
    # -----------------------------
    def extract_endpoints_if_fastapi(
        self,
        file_path: str,
        content: str
    ) -> List[Dict]:

        return self.endpoint_parser.extract_endpoints(
            file_path=file_path,
            content=content
        )
        
    # -----------------------------
    # Mapping logic
    # -----------------------------
    def _map(
        self,
        changed_lines: set,
        functions: List[Tuple[str, int, int]],
    ) -> List[str]:

        matched = []

        for name, start, end in functions:
            if any(start <= line <= end for line in changed_lines):
                matched.append(name)

        return list(set(matched))
    
    

##-----------------------------
# Endpoint extraction logic (bonus)
##-----------------------------

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


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
            if isinstance(node, ast.FunctionDef):
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
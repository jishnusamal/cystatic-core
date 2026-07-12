"""Python language adapter — graph builder pipeline.

Produces a single SemanticGraph from a git diff.

Pipeline:
    Git Diff
    ↓
    AST Loader (old + new content)
    ↓
    AST Diff
    ↓
    Parsers (each mutates the graph)
    ↓
    Semantic Graph
    ↓
    return graph

The core engine never knows what an AST is.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from schemas import DiffIR
from schemas.ir import FileDiff

from language_adapters.ir import SemanticGraph
from language_adapters.interfaces.adapter import LanguageAdapter
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.diff_utils import DiffUtils

from language_adapters.languages.python.ast.ast_loader import ASTLoader
from language_adapters.languages.python.ast.ast_diff import ASTDiff, ASTChange
from language_adapters.languages.python.ast.symbol_index import SymbolIndex

from language_adapters.languages.python.parsers import (
    SymbolParser,
    CallGraphParser,
    ReadWriteParser,
    QueryParser,
    TransactionParser,
    ValidationParser,
    NormalizationParser,
    ControlFlowParser,
    SideEffectParser,
    MigrationParser,
    TestParser,
    PersistenceParser,
)
from language_adapters.languages.python.frameworks import FastAPIParser, FlaskParser


_PARSE_ORDER: List[type[GraphBuilder]] = [
    SymbolParser,           # Stage 1: Symbols first (functions, classes, modules)
    CallGraphParser,        # Stage 2: Call relationships
    ReadWriteParser,        # Stage 3: Read/write operations
    QueryParser,            # Stage 4: Database queries
    PersistenceParser,      # Stage 5: ORM models/fields
    TransactionParser,      # Stage 6: Transaction boundaries
    ValidationParser,       # Stage 7: Validation logic
    NormalizationParser,    # Stage 8: Data normalization
    ControlFlowParser,      # Stage 9: Control flow analysis
    SideEffectParser,       # Stage 10: Side effects
    MigrationParser,        # Stage 11: Database migrations
    TestParser,             # Stage 12: Test cases
    FastAPIParser,          # Stage 13: FastAPI endpoints
    FlaskParser,            # Stage 13: Flask endpoints
]


class PythonAdapter(LanguageAdapter):
    """Python language adapter.

    Takes a DiffIR and produces a single SemanticGraph.
    The core engine never knows what an AST is.
    """

    def __init__(self) -> None:
        self._parsers: Dict[str, GraphBuilder] = {
            cls.__name__: cls() for cls in _PARSE_ORDER
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        diff: DiffIR,
        file_contents: Optional[Dict[str, str]] = None,
    ) -> SemanticGraph:
        """Analyze a diff and produce a semantic graph.

        Pipeline:
            1. Filter to Python files
            2. Load ASTs (old + new) for each changed file
            3. Compute AST diff (changed AST, not just line-level)
            4. Run all parsers against each file's context
            5. Return aggregated SemanticGraph

        Args:
            diff: The diff IR to analyze.
            file_contents: Optional mapping of file_path -> content for AST parsing.
                          If provided, old content is derived from diff hunks.

        Returns:
            A single language-agnostic SemanticGraph.
        """
        graph = SemanticGraph()
        python_files = DiffUtils.get_python_files(diff)

        for file_diff in python_files:
            file_graph = self._analyze_file(file_diff, file_contents or {})
            graph.merge(file_graph)

        graph.deduplicate()
        
        # Print the SemanticGraph for debugging
        print("=" * 80)
        print("SEMANTIC GRAPH BUILT BY LANGUAGE ADAPTER")
        print("=" * 80)
        graph_dict = graph.to_dict()
        print(f"Total nodes: {len(graph_dict['nodes'])}")
        print(f"Total edges: {len(graph_dict['edges'])}")
        print(f"Files analyzed: {len(graph_dict['file_paths'])}")
        # print("\nNodes:")
        # for node in graph_dict['nodes']:
        #     print(f"  [{node['type']}] {node['name']} in {node['file_path']} ({node['change_type']})")
        # print("\nEdges:")
        # for edge in graph_dict['edges']:
        #     print(f"  [{edge['type']}] {edge['source']} -> {edge['target']} ({edge['change_type']})")
        # print("=" * 80)
        
        return graph

    # ------------------------------------------------------------------
    # Per-file analysis
    # ------------------------------------------------------------------

    def _analyze_file(
        self,
        file_diff: FileDiff,
        file_contents: Dict[str, str],
    ) -> SemanticGraph:
        """Analyze a single file's diff and produce a sub-graph.

        This is the core pipeline for one file:
            1. Load file content (new AST for the PR head)
            2. Compute AST diffs from hunks
            3. Build symbol index (shared by all parsers)
            4. Run parsers in order, each mutating the graph
        """
        graph = SemanticGraph()
        file_path = file_diff.file_path

        # --- 1. Load AST for the new (post-change) file content ---
        new_content = file_contents.get(file_path)
        new_tree = ASTLoader.load(new_content) if new_content else None

        # --- 2. Compute AST-level changes ---
        # Provide old-content derivation from diff hunks when available
        old_content = self._reconstruct_old_content(new_content, file_diff) if new_content else None
        ast_changes: List[ASTChange] = []
        if old_content and new_content:
            ast_changes = ASTDiff.diff(old_content, new_content)

        # --- 3. Build shared context ---
        context: Dict[str, Any] = {
            "file_path": file_path,
            "file_diff": file_diff,
            "tree": new_tree,
            "old_tree": ASTLoader.load(old_content) if old_content else None,
            "ast_changes": ast_changes,
            "changed_lines": DiffUtils.get_changed_lines(file_diff),
            "added_lines": DiffUtils.get_added_lines(file_diff),
            "removed_lines": DiffUtils.get_removed_lines(file_diff),
        }

        # Build symbol index once, share with all parsers
        if new_tree is not None:
            context["symbol_index"] = SymbolIndex().build(new_tree)

        # --- 4. Run parsers in order (each mutates the graph) ---
        for _parser_name, parser in self._parsers.items():
            try:
                parser.build(graph, context)
            except Exception:
                # Parser failure shouldn't crash the whole pipeline
                continue

        return graph

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reconstruct_old_content(new_content: str, file_diff: FileDiff) -> Optional[str]:
        """Reconstruct the old (pre-change) file content from new content and diff hunks.

        This is a best-effort reconstruction. For each removed line in the diff,
        we insert it back into the new content at the appropriate position.
        For each added line, we remove it.
        """
        if not new_content or not file_diff:
            return None

        lines = new_content.splitlines(keepends=True)

        # Build a list of (line_number, content) for old additions and removals
        # Reverse-sort so we can apply from bottom to top without offset issues
        modifications: List[tuple] = []
        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.line_type == "removed" and line.source_line_no is not None:
                    modifications.append((line.source_line_no - 1, line.content, "insert"))
                elif line.line_type == "added" and line.target_line_no is not None:
                    modifications.append((line.target_line_no - 1, line.content, "delete"))

        modifications.sort(reverse=True)

        try:
            for line_no, content, action in modifications:
                if action == "delete" and line_no < len(lines):
                    lines.pop(line_no)
                elif action == "insert":
                    # Ensure content ends with newline for consistency
                    line_content = content if content.endswith("\n") else content + "\n"
                    lines.insert(line_no, line_content)

            return "".join(lines)
        except (IndexError, ValueError):
            return None
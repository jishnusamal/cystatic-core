"""Change compiler - orchestrates local fact comparison."""

from typing import Any

from engine.change.compiler.passes import (
    ChangeClassificationPass,
    ChangedSymbolsPass,
    FileClassificationPass,
)
from engine.change.model import (
    ChangedSymbol,
    ChangeFacts,
    ContractChange,
)
from engine.change.model.repository_comparison import RepositoryComparison
from engine.change.passes.file_classification import (
    DEFAULT_ANALYSIS_POLICY,
    AnalysisPolicy,
    FileClassification,
    FileClassifier,
    detect_language,
)
from engine.repository.facts import Call, FileId, Import, Reference, SymbolId
from engine.repository.query import QueryResult, RepositoryQuery


class RepositoryModelQuery(RepositoryQuery):
    """Query interface wrapper for the old RepositoryModel to support backward compatibility."""

    def __init__(self, model):
        self.model = model
        self._symbols = {s.id: s for s in model.symbols}

    def get_symbol(self, symbol_id):
        return self._symbols.get(symbol_id)

    def get_file(self, file_id):
        return None

    def get_callers(self, symbol_id):
        return QueryResult(
            tuple(
                Call(caller_id=SymbolId(e.caller_id), callee_id=SymbolId(e.callee_id))
                for e in self.model.call_graph.edges
                if e.callee_id == symbol_id
            ),
            complete=True,
        )

    def get_callees(self, symbol_id):
        return QueryResult(
            tuple(
                Call(caller_id=SymbolId(e.caller_id), callee_id=SymbolId(e.callee_id))
                for e in self.model.call_graph.edges
                if e.caller_id == symbol_id
            ),
            complete=True,
        )

    def get_references_from(self, symbol_id):
        return QueryResult(
            tuple(
                Reference(source_id=SymbolId(e.source_id), target_id=SymbolId(e.target_id))
                for e in self.model.reference_graph.edges
                if e.source_id == symbol_id
            ),
            complete=True,
        )

    def get_references_to(self, symbol_id):
        return QueryResult(
            tuple(
                Reference(source_id=SymbolId(e.source_id), target_id=SymbolId(e.target_id))
                for e in self.model.reference_graph.edges
                if e.target_id == symbol_id
            ),
            complete=True,
        )

    def get_imports(self, file_id):
        return QueryResult(
            tuple(
                Import(
                    source_file_id=FileId(s.file),
                    target_file_id=None,
                    module=s.properties.get("module", ""),
                    imported_name=s.name,
                )
                for s in self.model.symbols
                if s.kind == "import" and s.file == file_id
            ),
            complete=True,
        )

    def get_importers(self, file_id):
        return QueryResult((), complete=True)

    def get_type_relationships(self, symbol_id):
        return QueryResult((), complete=True)

    def get_type_dependents(self, symbol_id):
        return QueryResult((), complete=True)

    def get_endpoints(self, symbol_id):
        symbol = self.get_symbol(symbol_id)
        if symbol and (
            "endpoint" in symbol.properties or "http_method" in symbol.properties
        ):
            from engine.repository.facts import Endpoint, EndpointId, EndpointMethod

            method_str = symbol.properties.get("http_method", "GET")
            try:
                method = EndpointMethod(method_str)
            except ValueError:
                method = EndpointMethod.ANY
            return QueryResult(
                (
                    Endpoint(
                        id=EndpointId(hash(symbol_id) & 0xFFFFFFFF),
                        symbol_id=SymbolId(symbol_id),
                        method=method,
                        path=symbol.properties.get("endpoint", ""),
                        framework="",
                    ),
                ),
                complete=True,
            )
        return QueryResult((), complete=True)

    def get_database_relationships(self, symbol_id):
        return QueryResult((), complete=True)

    def get_published_events(self, symbol_id):
        return QueryResult((), complete=True)

    def get_event_consumers(self, event_id):
        return QueryResult((), complete=True)

    def get_tests(self, symbol_id):
        return QueryResult((), complete=True)

    def get_entry_points(self):
        return QueryResult(tuple(getattr(self.model, "entry_points", ())), complete=True)

    def get_symbols_in_file(self, file_id):
        return QueryResult(tuple(s for s in self.model.symbols if s.file == file_id), complete=True)


class ChangeCompiler:
    """
    Rebuilt ChangeCompiler.

    Processes the diff (local files modified) and compares facts locally
    using RepositoryQuery instead of repository-wide full model comparisons.

    Pass chain::

        ChangeCompiler
         ├── FileClassificationPass   (role classification + analysis eligibility)
         ├── ChangedSymbolsPass       (semantic symbol diff)
         └── ChangeClassificationPass (structural change classification)
    """

    def __init__(
        self,
        classifier: FileClassifier | None = None,
        policy: AnalysisPolicy | None = None,
    ) -> None:
        self.classifier = classifier or FileClassifier()
        self.policy = policy or DEFAULT_ANALYSIS_POLICY

        # Canonical pass order; FileClassificationPass must run first so that
        # excluded files never reach semantic change analysis.
        self.passes = (
            FileClassificationPass(self.classifier, self.policy),
            ChangedSymbolsPass(),
            ChangeClassificationPass(),
        )

        # Diagnostics from the most recent compile() run.
        self.last_file_classifications: dict[str, FileClassification] = {}
        self.last_excluded_files: frozenset[str] = frozenset()

    def compile(
        self,
        diff: Any = None,
        repository: Any = None,  # BASE query interface
        head_repository: Any = None,  # HEAD query interface
        comparison: RepositoryComparison | None = None,  # legacy support
    ) -> ChangeFacts:
        """
        Compile changes between base and head states.
        """
        # 1. Unpack comparison input if provided for legacy tests/pipeline
        if isinstance(diff, RepositoryComparison):
            comparison = diff
            diff = None

        if comparison is not None:
            base_query = RepositoryModelQuery(comparison.base_model)
            head_query = RepositoryModelQuery(comparison.head_model)
            diff_data = comparison.diff
        else:
            base_query = repository
            head_query = head_repository
            diff_data = diff or {}

        # Ensure we have queries to compare
        if base_query is None or head_query is None:
            return ChangeFacts()

        # 2. Localize set of changed files to prevent repository-wide comparison
        changed_files = set()
        # Handle DiffSnapshot objects (new architecture) and plain dicts (legacy)
        if hasattr(diff_data, "files"):
            # DiffSnapshot: .files is a tuple of DiffFile objects
            for f in diff_data.files:
                fp = getattr(f, "file_path", None) or getattr(f, "path", None)
                if fp:
                    changed_files.add(fp)
        elif isinstance(diff_data, dict) and "files" in diff_data:
            for f in diff_data["files"]:
                changed_files.add(f.get("file_path"))

        # If no explicit diff files, find them from symbols
        if not changed_files:
            if hasattr(base_query, "model") and hasattr(head_query, "model"):
                changed_files = {s.file for s in base_query.model.symbols} | {
                    s.file for s in head_query.model.symbols
                }
            elif hasattr(base_query, "_facts") and hasattr(head_query, "_facts"):
                changed_files = {f.path for f in base_query._facts.files} | {
                    f.path for f in head_query._facts.files
                }

        # 2.5 File role classification — analysis eligibility gate.
        #     Frontend TS/TSX and generated files are excluded before any
        #     semantic change analysis is performed.
        file_classifications: dict[str, FileClassification] = {
            file_path: self.classifier.classify(file_path)
            for file_path in sorted(changed_files)
        }
        excluded_files = frozenset(
            file_path
            for file_path, classification in file_classifications.items()
            if not self.policy.is_analyzable(
                classification, detect_language(file_path)
            )
        )
        changed_files -= set(excluded_files)
        self.last_file_classifications = file_classifications
        self.last_excluded_files = excluded_files

        changed_symbols = []
        added_calls = []
        removed_calls = []
        added_references = []
        removed_references = []
        added_imports = []
        removed_imports = []
        contract_changes = []

        # Helper to extract all symbol IDs for changed files
        base_symbols_by_file: dict[str, list[Any]] = {}
        head_symbols_by_file: dict[str, list[Any]] = {}

        # 3. Retrieve symbols scoped only to changed files
        if hasattr(base_query, "model"):
            for s in base_query.model.symbols:
                if s.file in changed_files:
                    base_symbols_by_file.setdefault(s.file, []).append(s)
        elif hasattr(base_query, "_facts"):
            for s in base_query._facts.symbols:
                file_fact = base_query.get_file(s.file_id)
                if file_fact and file_fact.path in changed_files:
                    base_symbols_by_file.setdefault(file_fact.path, []).append(s)
        else:
            for file_path in changed_files:
                file_fact = base_query.get_file(file_path)
                if file_fact:
                    syms = base_query.get_symbols_in_file(file_fact.id)
                    base_symbols_by_file.setdefault(file_path, []).extend(syms)

        if hasattr(head_query, "model"):
            for s in head_query.model.symbols:
                if s.file in changed_files:
                    head_symbols_by_file.setdefault(s.file, []).append(s)
        elif hasattr(head_query, "_facts"):
            for s in head_query._facts.symbols:
                file_fact = head_query.get_file(s.file_id)
                if file_fact and file_fact.path in changed_files:
                    head_symbols_by_file.setdefault(file_fact.path, []).append(s)
        else:
            for file_path in changed_files:
                file_fact = head_query.get_file(file_path)
                if file_fact:
                    syms = head_query.get_symbols_in_file(file_fact.id)
                    head_symbols_by_file.setdefault(file_path, []).extend(syms)

        # 4. Compare symbols and facts file-by-file locally
        for file_path in changed_files:
            base_syms = {s.id: s for s in base_symbols_by_file.get(file_path, [])}
            head_syms = {s.id: s for s in head_symbols_by_file.get(file_path, [])}

            # Added symbols
            for sid, h_sym in head_syms.items():
                if sid not in base_syms:
                    changed_symbols.append(
                        ChangedSymbol(
                            symbol_id=sid, change_type="ADDED", file_id=file_path
                        )
                    )

                    # Inspect added calls, references, and contracts
                    added_calls.extend(head_query.get_callees(sid))
                    added_references.extend(head_query.get_references_from(sid))

                    for ep in head_query.get_endpoints(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="api",
                                change_kind="added",
                                details={
                                    "new_endpoint": ep.path,
                                    "new_method": ep.method.value
                                    if hasattr(ep.method, "value")
                                    else str(ep.method),
                                },
                            )
                        )
                    for db in head_query.get_database_relationships(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="database",
                                change_kind="added",
                                details={"resource_id": str(db.resource_id)},
                            )
                        )
                    for epub in head_query.get_published_events(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="event_publish",
                                change_kind="added",
                                details={"event_id": str(epub.event_id)},
                            )
                        )

            # Removed symbols
            for sid, b_sym in base_syms.items():
                if sid not in head_syms:
                    changed_symbols.append(
                        ChangedSymbol(
                            symbol_id=sid, change_type="REMOVED", file_id=file_path
                        )
                    )

                    # Inspect removed calls, references, and contracts
                    removed_calls.extend(base_query.get_callees(sid))
                    removed_references.extend(base_query.get_references_from(sid))

                    for ep in base_query.get_endpoints(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="api",
                                change_kind="removed",
                                details={
                                    "old_endpoint": ep.path,
                                    "old_method": ep.method.value
                                    if hasattr(ep.method, "value")
                                    else str(ep.method),
                                },
                            )
                        )
                    for db in base_query.get_database_relationships(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="database",
                                change_kind="removed",
                                details={"resource_id": str(db.resource_id)},
                            )
                        )
                    for epub in base_query.get_published_events(sid):
                        contract_changes.append(
                            ContractChange(
                                symbol_id=sid,
                                contract_type="event_publish",
                                change_kind="removed",
                                details={"event_id": str(epub.event_id)},
                            )
                        )

            # Modified symbols
            for sid, h_sym in head_syms.items():
                if sid in base_syms:
                    b_sym = base_syms[sid]

                    # Detect structural symbol modifications
                    modified = False
                    b_range = getattr(
                        b_sym,
                        "range",
                        (
                            getattr(b_sym, "start_line", 0),
                            getattr(b_sym, "end_line", 0),
                        ),
                    )
                    h_range = getattr(
                        h_sym,
                        "range",
                        (
                            getattr(h_sym, "start_line", 0),
                            getattr(h_sym, "end_line", 0),
                        ),
                    )
                    b_vis = getattr(b_sym, "visibility", None)
                    h_vis = getattr(h_sym, "visibility", None)
                    b_props = getattr(b_sym, "properties", {})
                    h_props = getattr(h_sym, "properties", {})

                    if b_range != h_range or b_vis != h_vis or b_props != h_props:
                        modified = True

                    if modified:
                        changed_symbols.append(
                            ChangedSymbol(
                                symbol_id=sid, change_type="MODIFIED", file_id=file_path
                            )
                        )

                        # Compare range (body)
                        if b_range != h_range:
                            contract_changes.append(
                                ContractChange(
                                    symbol_id=sid,
                                    contract_type="body",
                                    change_kind="modified",
                                    details={
                                        "old_body_hash": b_props.get("body_hash", "")
                                        if b_props
                                        else "",
                                        "new_body_hash": h_props.get("body_hash", "")
                                        if h_props
                                        else "",
                                    },
                                )
                            )

                        # Compare visibility
                        if b_vis != h_vis:
                            contract_changes.append(
                                ContractChange(
                                    symbol_id=sid,
                                    contract_type="visibility",
                                    change_kind="modified",
                                    details={
                                        "old_visibility": b_vis.value
                                        if b_vis is not None and hasattr(b_vis, "value")
                                        else str(b_vis),
                                        "new_visibility": h_vis.value
                                        if h_vis is not None and hasattr(h_vis, "value")
                                        else str(h_vis),
                                    },
                                )
                            )

                        # Compare decorators
                        b_decs = b_props.get("decorators", [])
                        h_decs = h_props.get("decorators", [])
                        if b_decs != h_decs:
                            contract_changes.append(
                                ContractChange(
                                    symbol_id=sid,
                                    contract_type="decorators",
                                    change_kind="modified",
                                    details={
                                        "old_decorators": tuple(b_decs),
                                        "new_decorators": tuple(h_decs),
                                    },
                                )
                            )

                        # Compare signature
                        if b_props.get("signature") != h_props.get(
                            "signature"
                        ):
                            contract_changes.append(
                                ContractChange(
                                    symbol_id=sid,
                                    contract_type="signature",
                                    change_kind="modified",
                                    details={
                                        "old_signature": b_props.get(
                                            "signature"
                                        ),
                                        "new_signature": h_props.get(
                                            "signature"
                                        ),
                                    },
                                )
                            )

                        # Compare endpoints
                        b_eps = {ep.id: ep for ep in base_query.get_endpoints(sid)}
                        h_eps = {ep.id: ep for ep in head_query.get_endpoints(sid)}
                        for eid, hep in h_eps.items():
                            if eid not in b_eps:
                                contract_changes.append(
                                    ContractChange(
                                        symbol_id=sid,
                                        contract_type="api",
                                        change_kind="added",
                                        details={
                                            "new_endpoint": hep.path,
                                            "new_method": hep.method.value
                                            if hasattr(hep.method, "value")
                                            else str(hep.method),
                                        },
                                    )
                                )
                            elif (
                                b_eps[eid].path != hep.path
                                or b_eps[eid].method != hep.method
                            ):
                                contract_changes.append(
                                    ContractChange(
                                        symbol_id=sid,
                                        contract_type="api",
                                        change_kind="modified",
                                        details={
                                            "old_endpoint": b_eps[eid].path,
                                            "new_endpoint": hep.path,
                                            "old_method": b_eps[eid].method.value
                                            if hasattr(b_eps[eid].method, "value")
                                            else str(b_eps[eid].method),
                                            "new_method": hep.method.value
                                            if hasattr(hep.method, "value")
                                            else str(hep.method),
                                        },
                                    )
                                )
                        for eid, bep in b_eps.items():
                            if eid not in h_eps:
                                contract_changes.append(
                                    ContractChange(
                                        symbol_id=sid,
                                        contract_type="api",
                                        change_kind="removed",
                                        details={
                                            "old_endpoint": bep.path,
                                            "old_method": bep.method.value
                                            if hasattr(bep.method, "value")
                                            else str(bep.method),
                                        },
                                    )
                                )

                        # Compare calls
                        b_calls = {
                            (c.caller_id, c.callee_id): c
                            for c in base_query.get_callees(sid)
                        }
                        h_calls = {
                            (c.caller_id, c.callee_id): c
                            for c in head_query.get_callees(sid)
                        }
                        for key, hc in h_calls.items():
                            if key not in b_calls:
                                added_calls.append(hc)
                        for key, bc in b_calls.items():
                            if key not in h_calls:
                                removed_calls.append(bc)

                        # Compare references
                        b_refs = {
                            (r.source_id, r.target_id): r
                            for r in base_query.get_references_from(sid)
                        }
                        h_refs = {
                            (r.source_id, r.target_id): r
                            for r in head_query.get_references_from(sid)
                        }
                        for key, hr in h_refs.items():
                            if key not in b_refs:
                                added_references.append(hr)
                        for key, br in b_refs.items():
                            if key not in h_refs:
                                removed_references.append(br)

            # Compare imports for the file
            file_id_b = None
            if hasattr(base_query, "_facts"):
                for f in base_query._facts.files:
                    if f.path == file_path:
                        file_id_b = f.id
                        break
            if file_id_b is None:
                file_id_b = file_path

            file_id_h = None
            if hasattr(head_query, "_facts"):
                for f in head_query._facts.files:
                    if f.path == file_path:
                        file_id_h = f.id
                        break
            if file_id_h is None:
                file_id_h = file_path

            b_imports = {imp.module: imp for imp in base_query.get_imports(file_id_b)}
            h_imports = {imp.module: imp for imp in head_query.get_imports(file_id_h)}

            for mod, imp in h_imports.items():
                if mod not in b_imports:
                    added_imports.append(imp)
            for mod, imp in b_imports.items():
                if mod not in h_imports:
                    removed_imports.append(imp)

        return ChangeFacts(
            changed_symbols=tuple(changed_symbols),
            added_calls=tuple(added_calls),
            removed_calls=tuple(removed_calls),
            added_references=tuple(added_references),
            removed_references=tuple(removed_references),
            added_imports=tuple(added_imports),
            removed_imports=tuple(removed_imports),
            contract_changes=tuple(contract_changes),
            files_changed=len(changed_files),
        )

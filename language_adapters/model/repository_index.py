"""RepositoryIndex - immutable, language-independent intermediate representation.

The RepositoryIndex contains only structural facts extracted from source code.
No resolved relationships, no semantic inference, no execution analysis.

This is the output of indexing and the input to semantic compilation.
It is designed to be serializable, cacheable, and parallel-friendly.

Phase 10: Lazy Expansion API
------------------------------
The RepositoryIndex supports future selective semantic compilation:

    RepositoryIndex
        ↓
    Changed symbols
        ↓
    Reachable neighborhood
        ↓
    Semantic compilation
        ↓
    RepositoryModel slice

Currently, all symbols are compiled. The API is designed so that
future implementations can compile only a subset of symbols.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SymbolEntry:
    """A discovered symbol in the repository (language-agnostic).

    Attributes:
        name: Human-readable symbol name
        kind: Symbol kind (function, class, method, etc.)
        file: Source file path
        start_line: 0-based start line
        end_line: 0-based end line
        visibility: Access visibility string
        parent: Parent symbol name (e.g., class name for methods), empty if none
        properties: Additional metadata key-value pairs
    """
    name: str
    kind: str
    file: str
    start_line: int = 0
    end_line: int = 0
    visibility: str = "public"
    parent: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportEntry:
    """An import statement in the repository.

    Attributes:
        module: Module or package being imported
        names: List of imported names
        import_type: Type of import (import, import_from, etc.)
        file: Source file path
        line: 0-based line number
    """
    module: str
    names: tuple[str, ...] = field(default_factory=tuple)
    import_type: str = "import"
    file: str = ""
    line: int = 0


@dataclass(frozen=True)
class RawReference:
    """An unresolved reference to a symbol.

    References are stored as raw text — no resolution is attempted.

    Attributes:
        name: The raw reference text (e.g., "foo.bar")
        kind: Reference kind (call, attribute_access, etc.)
        file: Source file path
        line: 0-based line number
        parent_symbol: Name of the enclosing symbol, if any
    """
    name: str
    kind: str = "call"
    file: str = ""
    line: int = 0
    parent_symbol: str = ""


@dataclass(frozen=True)
class EntrypointEntry:
    """A discovered entry point in the repository.

    Attributes:
        route: Route or trigger identifier (e.g., "POST /checkout")
        handler: Handler function name
        kind: Entry point kind (rest_endpoint, cli_command, etc.)
        framework: Framework identifier
        file: Source file path
        line: 0-based line number
        metadata: Additional framework-specific key-value pairs
    """
    route: str
    handler: str
    kind: str = "rest_endpoint"
    framework: str = ""
    file: str = ""
    line: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistenceEntry:
    """A persistence model (ORM/ODM) discovery.

    Attributes:
        name: Model class/struct name
        kind: Model kind (table, document, etc.)
        table_name: Underlying table/collection name
        framework: ORM/ODM framework
        file: Source file path
        line: 0-based line number
        fields: List of field definitions
        relationships: List of relationship definitions
        metadata: Additional key-value pairs
    """
    name: str
    kind: str = "table"
    table_name: str = ""
    framework: str = ""
    file: str = ""
    line: int = 0
    fields: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    relationships: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventEntry:
    """An event operation (publish, emit, etc.).

    Attributes:
        symbol_name: Name of the symbol performing the operation
        operation_kind: Type of event operation (publish, emit, send, etc.)
        event_name: Name of the event being operated on
        framework: Event framework identifier
        file: Source file path
        line: 0-based line number
        metadata: Additional key-value pairs
    """
    symbol_name: str
    operation_kind: str = "publish"
    event_name: str = ""
    framework: str = ""
    file: str = ""
    line: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigEntry:
    """A configuration reference (environment variable, etc.).

    Attributes:
        symbol_name: Name of the symbol using the config
        config_key: Configuration key being referenced
        kind: Config reference kind (environment_variable, etc.)
        framework: Framework identifier
        file: Source file path
        line: 0-based line number
        default_value: Default value if any
        metadata: Additional key-value pairs
    """
    symbol_name: str
    config_key: str = ""
    kind: str = "environment_variable"
    framework: str = ""
    file: str = ""
    line: int = 0
    default_value: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestEntry:
    """A test definition.

    Attributes:
        name: Test name
        kind: Test kind (function, class, method)
        framework: Test framework identifier
        file: Source file path
        line: 0-based line number
        fixtures: List of fixture definitions
        assertions: List of assertion descriptions
        test_methods: Nested test methods (for test classes)
        metadata: Additional key-value pairs
    """
    name: str
    kind: str = "function"
    framework: str = "other"
    file: str = ""
    line: int = 0
    fixtures: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    assertions: tuple[str, ...] = field(default_factory=tuple)
    test_methods: tuple["TestEntry", ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TypeRelationshipEntry:
    """A type relationship (inheritance, implementation, etc.).

    Attributes:
        source: Source type name
        target: Target type name
        relation_type: Relationship type (extends, implements, composes, etc.)
        file: Source file path
        line: 0-based line number
        metadata: Additional key-value pairs
    """
    source: str
    target: str
    relation_type: str = "extends"
    file: str = ""
    line: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallEntry:
    """An unresolved function call.

    Attributes:
        caller: Name of the calling function/method
        callee: Raw name of the called function/method
        call_type: Type of call (direct, attribute, etc.)
        file: Source file path
        line: 0-based line number
    """
    caller: str
    callee: str
    call_type: str = "direct"
    file: str = ""
    line: int = 0


@dataclass(frozen=True)
class RepositoryMethodEntry:
    """A repository/data access method.

    Attributes:
        symbol_name: Name of the method
        kind: Method kind (custom, crud, etc.)
        model_name: Associated model/entity name
        framework: ORM/ODM framework
        query: Query string if applicable
        file: Source file path
        line: 0-based line number
        metadata: Additional key-value pairs
    """
    symbol_name: str
    kind: str = "custom"
    model_name: str = ""
    framework: str = ""
    query: str = ""
    file: str = ""
    line: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FileIndex:
    """Structural facts from a single file.

    This is the per-file indexing result fed into the RepositoryIndex.
    Each file is parsed exactly once and its facts are captured here.
    """
    path: str
    language: str
    symbols: tuple[SymbolEntry, ...] = field(default_factory=tuple)
    imports: tuple[ImportEntry, ...] = field(default_factory=tuple)
    references: tuple[RawReference, ...] = field(default_factory=tuple)
    calls: tuple[CallEntry, ...] = field(default_factory=tuple)
    entrypoints: tuple[EntrypointEntry, ...] = field(default_factory=tuple)
    type_relationships: tuple[TypeRelationshipEntry, ...] = field(default_factory=tuple)
    persistence_models: tuple[PersistenceEntry, ...] = field(default_factory=tuple)
    repository_methods: tuple[RepositoryMethodEntry, ...] = field(default_factory=tuple)
    events: tuple[EventEntry, ...] = field(default_factory=tuple)
    tests: tuple[TestEntry, ...] = field(default_factory=tuple)
    configurations: tuple[ConfigEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RepositoryIndex:
    """Immutable, language-independent repository index.

    Contains only structural facts extracted from source code.
    No resolved relationships, no semantic inference, no execution analysis.

    Designed to be:
    - Serializable (all entries are simple dataclasses)
    - Immutable (all fields are frozen)
    - Cacheable (by repository + commit SHA)
    - Parallel-friendly (per-file indexing is independent)

    The RepositoryIndex is the output of the indexing stage and the
    input to the semantic compilation stage.

    Lazy Expansion API (Phase 10)
    -----------------------------
    The RepositoryIndex supports future selective semantic compilation.
    Use the methods below to identify which symbols need compilation:

        index = adapter.build_index(files)
        
        # Get all symbols
        all_symbols = index.all_symbols
        
        # Get symbols in a specific file
        file_symbols = index.get_symbols_for_file("src/main.py")
        
        # Get symbols by kind
        functions = index.get_symbols_by_kind("function")
        
        # Future: compile only changed symbols
        changed = index.get_changed_symbols(base_index)
        neighborhood = index.get_reachable_neighborhood(changed)
        model = semantic_compiler.compile(neighborhood)
    """

    files: tuple[FileIndex, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure metadata is a plain dict."""
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
        if isinstance(self.files, list):
            object.__setattr__(self, 'files', tuple(self.files))

    # ------------------------------------------------------------------
    # Aggregation properties (convenience accessors)
    # ------------------------------------------------------------------

    @property
    def all_symbols(self) -> tuple[SymbolEntry, ...]:
        """Get all symbols across all files."""
        result: list[SymbolEntry] = []
        for f in self.files:
            result.extend(f.symbols)
        return tuple(result)

    @property
    def all_imports(self) -> tuple[ImportEntry, ...]:
        """Get all imports across all files."""
        result: list[ImportEntry] = []
        for f in self.files:
            result.extend(f.imports)
        return tuple(result)

    @property
    def all_references(self) -> tuple[RawReference, ...]:
        """Get all raw references across all files."""
        result: list[RawReference] = []
        for f in self.files:
            result.extend(f.references)
        return tuple(result)

    @property
    def all_calls(self) -> tuple[CallEntry, ...]:
        """Get all calls across all files."""
        result: list[CallEntry] = []
        for f in self.files:
            result.extend(f.calls)
        return tuple(result)

    @property
    def all_entrypoints(self) -> tuple[EntrypointEntry, ...]:
        """Get all entry points across all files."""
        result: list[EntrypointEntry] = []
        for f in self.files:
            result.extend(f.entrypoints)
        return tuple(result)

    @property
    def all_type_relationships(self) -> tuple[TypeRelationshipEntry, ...]:
        """Get all type relationships across all files."""
        result: list[TypeRelationshipEntry] = []
        for f in self.files:
            result.extend(f.type_relationships)
        return tuple(result)

    @property
    def all_persistence_models(self) -> tuple[PersistenceEntry, ...]:
        """Get all persistence models across all files."""
        result: list[PersistenceEntry] = []
        for f in self.files:
            result.extend(f.persistence_models)
        return tuple(result)

    @property
    def all_repository_methods(self) -> tuple[RepositoryMethodEntry, ...]:
        """Get all repository methods across all files."""
        result: list[RepositoryMethodEntry] = []
        for f in self.files:
            result.extend(f.repository_methods)
        return tuple(result)

    @property
    def all_events(self) -> tuple[EventEntry, ...]:
        """Get all event constructs across all files."""
        result: list[EventEntry] = []
        for f in self.files:
            result.extend(f.events)
        return tuple(result)

    @property
    def all_tests(self) -> tuple[TestEntry, ...]:
        """Get all test definitions across all files."""
        result: list[TestEntry] = []
        for f in self.files:
            result.extend(f.tests)
        return tuple(result)

    @property
    def all_configurations(self) -> tuple[ConfigEntry, ...]:
        """Get all configuration references across all files."""
        result: list[ConfigEntry] = []
        for f in self.files:
            result.extend(f.configurations)
        return tuple(result)

    # ------------------------------------------------------------------
    # Phase 10: Lazy Expansion API
    # ------------------------------------------------------------------

    def get_file_index(self, file_path: str) -> FileIndex | None:
        """Get the FileIndex for a specific file.

        Args:
            file_path: Path to the source file

        Returns:
            FileIndex if found, None otherwise
        """
        for f in self.files:
            if f.path == file_path:
                return f
        return None

    def get_symbols_for_file(self, file_path: str) -> tuple[SymbolEntry, ...]:
        """Get all symbols from a specific file.

        Args:
            file_path: Path to the source file

        Returns:
            Tuple of SymbolEntry objects from that file
        """
        file_index = self.get_file_index(file_path)
        return file_index.symbols if file_index else tuple()

    def get_symbols_by_kind(self, kind: str) -> tuple[SymbolEntry, ...]:
        """Get all symbols of a specific kind across all files.

        Args:
            kind: Symbol kind (function, class, method, etc.)

        Returns:
            Tuple of matching SymbolEntry objects
        """
        return tuple(s for s in self.all_symbols if s.kind == kind)

    def get_calls_for_symbol(self, symbol_name: str) -> tuple[CallEntry, ...]:
        """Get all call entries where this symbol is the caller.

        Args:
            symbol_name: Name of the calling symbol

        Returns:
            Tuple of CallEntry objects
        """
        return tuple(c for c in self.all_calls if c.caller == symbol_name)

    def get_calls_to_symbol(self, symbol_name: str) -> tuple[CallEntry, ...]:
        """Get all call entries where this symbol is the callee.

        Args:
            symbol_name: Name of the called symbol

        Returns:
            Tuple of CallEntry objects
        """
        return tuple(c for c in self.all_calls if c.callee == symbol_name)

    def get_entrypoints_for_symbol(self, symbol_name: str) -> tuple[EntrypointEntry, ...]:
        """Get all entry points that reference this symbol as handler.

        Args:
            symbol_name: Name of the handler symbol

        Returns:
            Tuple of matching EntrypointEntry objects
        """
        return tuple(ep for ep in self.all_entrypoints if ep.handler == symbol_name)

    def get_references_in_file(self, file_path: str) -> tuple[RawReference, ...]:
        """Get all raw references in a specific file.

        Args:
            file_path: Path to the source file

        Returns:
            Tuple of RawReference objects from that file
        """
        file_index = self.get_file_index(file_path)
        return file_index.references if file_index else tuple()

    def get_files_by_language(self, language: str) -> tuple[FileIndex, ...]:
        """Get all FileIndex entries for a specific language.

        Args:
            language: Language identifier (e.g., "python", "java")

        Returns:
            Tuple of matching FileIndex objects
        """
        return tuple(f for f in self.files if f.language == language)

    def filter_by_files(self, file_paths: set[str]) -> "RepositoryIndex":
        """Create a new RepositoryIndex containing only the specified files.

        This enables selective semantic compilation of a subset of files.

        Args:
            file_paths: Set of file paths to include

        Returns:
            New RepositoryIndex with only the specified files
        """
        filtered_files = tuple(f for f in self.files if f.path in file_paths)
        return RepositoryIndex(files=filtered_files, metadata=dict(self.metadata))

    def get_changed_symbols(self, base_index: "RepositoryIndex") -> tuple[SymbolEntry, ...]:
        """Compare with a base index and return symbols that changed.

        This is a structural comparison — it detects added, removed,
        or modified symbols between two RepositoryIndex instances.

        Args:
            base_index: Base RepositoryIndex to compare against

        Returns:
            Tuple of SymbolEntry objects that changed
        """
        base_symbols = {s.name: s for s in base_index.all_symbols}
        current_symbols = {s.name: s for s in self.all_symbols}

        changed: list[SymbolEntry] = []

        # Find new or modified symbols
        for name, symbol in current_symbols.items():
            if name not in base_symbols:
                changed.append(symbol)
            else:
                base_sym = base_symbols[name]
                if (symbol.start_line, symbol.end_line) != (base_sym.start_line, base_sym.end_line):
                    changed.append(symbol)

        return tuple(changed)

    def get_reachable_files(self, symbol_names: set[str]) -> tuple[str, ...]:
        """Get all files that reference the given symbols.

        This enables neighborhood-based semantic compilation:
        compile only the symbols that changed and the files that
        reference them.

        Args:
            symbol_names: Set of symbol names to find references to

        Returns:
            Tuple of file paths that reference these symbols
        """
        reachable: set[str] = set()

        for call in self.all_calls:
            if call.caller in symbol_names or call.callee in symbol_names:
                reachable.add(call.file)

        for ref in self.all_references:
            if ref.name in symbol_names or ref.parent_symbol in symbol_names:
                reachable.add(ref.file)

        for ep in self.all_entrypoints:
            if ep.handler in symbol_names:
                reachable.add(ep.file)

        return tuple(reachable)
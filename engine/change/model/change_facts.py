"""Lightweight change facts model representing the minimal set of facts needed for impact analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from engine.repository.facts import (
    Call,
    Import,
    Reference,
    SymbolKind,
    SymbolVisibility,
)


class ChangeKind(str, Enum):
    SYMBOL_ADDED = "SYMBOL_ADDED"
    SYMBOL_REMOVED = "SYMBOL_REMOVED"
    SYMBOL_MODIFIED = "SYMBOL_MODIFIED"
    SIGNATURE_CHANGED = "SIGNATURE_CHANGED"
    CALLS_CHANGED = "CALLS_CHANGED"
    REFERENCES_CHANGED = "REFERENCES_CHANGED"
    API_CHANGED = "API_CHANGED"
    DATABASE_CHANGED = "DATABASE_CHANGED"
    EVENT_CHANGED = "EVENT_CHANGED"


@dataclass(frozen=True, slots=True)
class ChangedSymbol:
    """Represents a change to a symbol identifier."""

    symbol_id: str
    change_type: str  # "ADDED", "REMOVED", "MODIFIED"
    file_id: str  # file path/id


@dataclass(frozen=True, slots=True)
class ContractChange:
    """Represents a change to a system contract boundary (API, DB, Events)."""

    symbol_id: str
    contract_type: str  # "api", "database", "event_publish", "event_subscribe", "signature", "visibility", "decorators", "body"
    change_kind: str  # "added", "removed", "modified"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeFacts:
    """
    Lightweight set of change facts driving Factor's impact analysis.

    Contains references to facts rather than copies of complete symbols.
    """

    changed_symbols: tuple[ChangedSymbol, ...] = field(default_factory=tuple)
    added_calls: tuple[Call, ...] = field(default_factory=tuple)
    removed_calls: tuple[Call, ...] = field(default_factory=tuple)
    added_references: tuple[Reference, ...] = field(default_factory=tuple)
    removed_references: tuple[Reference, ...] = field(default_factory=tuple)
    added_imports: tuple[Import, ...] = field(default_factory=tuple)
    removed_imports: tuple[Import, ...] = field(default_factory=tuple)
    contract_changes: tuple[ContractChange, ...] = field(default_factory=tuple)
    files_changed: int = 0

    # Temporary backward compatibility properties for downstream compilers
    @property
    def added_symbols(self) -> tuple[Any, ...]:
        class CompatSymbol:
            def __init__(self, symbol_id: str, file_id: str):
                self.id = str(symbol_id)
                self.file = file_id
                self.name = str(symbol_id).split("::")[-1].split("#")[-1]
                self.kind = SymbolKind.FUNCTION
                self.visibility = SymbolVisibility.PUBLIC
                self.language = "python"
                self.range = (1, 1)
                self.properties: dict[str, Any] = {}

            def __hash__(self):
                return hash(self.id)

            def __eq__(self, other):
                return isinstance(other, CompatSymbol) and self.id == other.id

        return tuple(
            CompatSymbol(cs.symbol_id, cs.file_id)
            for cs in self.changed_symbols
            if cs.change_type == "ADDED"
        )

    @property
    def removed_symbols(self) -> tuple[Any, ...]:
        class CompatSymbol:
            def __init__(self, symbol_id: str, file_id: str):
                self.id = str(symbol_id)
                self.file = file_id
                self.name = str(symbol_id).split("::")[-1].split("#")[-1]
                self.kind = SymbolKind.FUNCTION
                self.visibility = SymbolVisibility.PUBLIC
                self.language = "python"
                self.range = (1, 1)
                self.properties: dict[str, Any] = {}

            def __hash__(self):
                return hash(self.id)

            def __eq__(self, other):
                return isinstance(other, CompatSymbol) and self.id == other.id

        return tuple(
            CompatSymbol(cs.symbol_id, cs.file_id)
            for cs in self.changed_symbols
            if cs.change_type == "REMOVED"
        )

    @property
    def modified_symbols(self) -> tuple[Any, ...]:
        class CompatSymbol:
            def __init__(self, symbol_id: str, file_id: str):
                self.id = str(symbol_id)
                self.file = file_id
                self.name = str(symbol_id).split("::")[-1].split("#")[-1]
                self.kind = SymbolKind.FUNCTION
                self.visibility = SymbolVisibility.PUBLIC
                self.language = "python"
                self.range = (1, 1)
                self.properties: dict[str, Any] = {}

            def __hash__(self):
                return hash(self.id)

            def __eq__(self, other):
                return isinstance(other, CompatSymbol) and self.id == other.id

        class CompatModifiedSymbol:
            def __init__(self, symbol_id: str, file_id: str, changes: tuple[Any, ...]):
                self.symbol = CompatSymbol(symbol_id, file_id)
                self.changes = changes

            def __hash__(self):
                return hash(self.symbol.id)

            def __eq__(self, other):
                return (
                    isinstance(other, CompatModifiedSymbol)
                    and self.symbol.id == other.symbol.id
                )

        result = []
        for cs in self.changed_symbols:
            if cs.change_type == "MODIFIED":
                changes_list: list[Any] = []
                has_any_change = False
                for cc in self.contract_changes:
                    if cc.symbol_id == cs.symbol_id:
                        if cc.contract_type == "signature":
                            from engine.change.model.changes import SignatureChange

                            changes_list.append(
                                SignatureChange(
                                    old_signature=cc.details.get("old_signature", ""),
                                    new_signature=cc.details.get("new_signature", ""),
                                )
                            )
                            has_any_change = True
                        elif cc.contract_type == "api":
                            from engine.change.model.changes import (
                                EndpointAnnotationChange,
                            )

                            changes_list.append(
                                EndpointAnnotationChange(
                                    old_endpoint=cc.details.get("old_endpoint"),
                                    new_endpoint=cc.details.get("new_endpoint"),
                                    old_method=cc.details.get("old_method"),
                                    new_method=cc.details.get("new_method"),
                                )
                            )
                            has_any_change = True
                        elif cc.contract_type == "visibility":
                            from engine.change.model.changes import VisibilityChange

                            changes_list.append(
                                VisibilityChange(
                                    old_visibility=cc.details.get("old_visibility", ""),
                                    new_visibility=cc.details.get("new_visibility", ""),
                                )
                            )
                            has_any_change = True
                        elif cc.contract_type == "decorators":
                            from engine.change.model.changes import DecoratorChange

                            changes_list.append(
                                DecoratorChange(
                                    old_decorators=cc.details.get("old_decorators", ()),
                                    new_decorators=cc.details.get("new_decorators", ()),
                                )
                            )
                            has_any_change = True
                        elif cc.contract_type == "body":
                            from engine.change.model.changes import FunctionBodyChange

                            changes_list.append(
                                FunctionBodyChange(
                                    old_body_hash=cc.details.get("old_body_hash", ""),
                                    new_body_hash=cc.details.get("new_body_hash", ""),
                                )
                            )
                            has_any_change = True

                if not has_any_change:
                    from engine.change.model.changes import FunctionBodyChange

                    changes_list.append(
                        FunctionBodyChange(old_body_hash="", new_body_hash="")
                    )

                result.append(
                    CompatModifiedSymbol(cs.symbol_id, cs.file_id, tuple(changes_list))
                )
        return tuple(result)

    @property
    def changed_imports(self) -> tuple[Any, ...]:
        class CompatImportChange:
            def __init__(
                self,
                file: str,
                old_import: str | None,
                new_import: str | None,
                change_type: str,
            ):
                self.file = file
                self.old_import = old_import
                self.new_import = new_import
                self.change_type = change_type

        result = []
        for imp in self.added_imports:
            result.append(
                CompatImportChange(str(imp.source_file_id), None, imp.module, "added")
            )
        for imp in self.removed_imports:
            result.append(
                CompatImportChange(str(imp.source_file_id), imp.module, None, "removed")
            )
        return tuple(result)

    @property
    def changed_endpoints(self) -> tuple[Any, ...]:
        class CompatEndpointChange:
            def __init__(
                self,
                symbol_id: str,
                old_endpoint: str | None,
                new_endpoint: str | None,
                old_method: str | None,
                new_method: str | None,
                change_type: str,
            ):
                self.symbol_id = symbol_id
                self.old_endpoint = old_endpoint
                self.new_endpoint = new_endpoint
                self.old_method = old_method
                self.new_method = new_method
                self.change_type = change_type

        result = []
        for cc in self.contract_changes:
            if cc.contract_type == "api":
                result.append(
                    CompatEndpointChange(
                        cc.symbol_id,
                        cc.details.get("old_endpoint"),
                        cc.details.get("new_endpoint"),
                        cc.details.get("old_method"),
                        cc.details.get("new_method"),
                        cc.change_kind,
                    )
                )
        return tuple(result)

    def get_added_symbols_by_kind(self, kind: str) -> tuple[Any, ...]:
        """Get all added symbols of a specific kind (mock for compat)."""
        return tuple(
            s
            for s in self.added_symbols
            if s.kind == kind or kind == "class" and "Class" in s.name
        )

    def get_removed_symbols_by_kind(self, kind: str) -> tuple[Any, ...]:
        """Get all removed symbols of a specific kind (mock for compat)."""
        return tuple(s for s in self.removed_symbols if s.kind == kind)

    def get_modified_symbols_by_kind(self, kind: str) -> tuple[Any, ...]:
        """Get all modified symbols of a specific kind (mock for compat)."""
        return tuple(ms for ms in self.modified_symbols if ms.symbol.kind == kind)

    def get_changes_for_symbol(self, symbol_id: str) -> Any | None:
        """Get modification details for a specific symbol (mock for compat)."""
        for modified in self.modified_symbols:
            if modified.symbol.id == symbol_id:
                return modified
        return None

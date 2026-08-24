from dataclasses import dataclass

from engine.repository.query import EventId, FileId, SymbolId


@dataclass(frozen=True)
class ResolutionRequirement:
    """Base class for all repository resolution requirements."""

@dataclass(frozen=True)
class FileResolutionRequirement(ResolutionRequirement):
    file_id: FileId | str  # Can be integer ID or path string
    query_type: str = "file"  # "file", "importers", "symbols"

@dataclass(frozen=True)
class SymbolResolutionRequirement(ResolutionRequirement):
    symbol_id: SymbolId
    query_type: str  # "callers", "callees", "references_from", "references_to", etc.

@dataclass(frozen=True)
class EventResolutionRequirement(ResolutionRequirement):
    event_id: EventId

@dataclass(frozen=True)
class AllEntryPointsRequirement(ResolutionRequirement):
    pass

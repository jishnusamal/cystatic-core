from dataclasses import dataclass
from enum import Enum
from .ids import FileId


class ImportType(str, Enum):
    """The style of importing."""

    STANDARD = "standard"
    FROM = "from"
    STAR = "star"
    RELATIVE = "relative"
    DYNAMIC = "dynamic"


@dataclass(frozen=True, slots=True)
class Import:
    """Represents an import relationship fact between files."""

    source_file_id: FileId
    target_file_id: FileId | None
    module: str
    imported_name: str
    import_type: ImportType = ImportType.STANDARD

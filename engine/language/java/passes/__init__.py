"""Java indexing passes for the deterministic indexing pipeline.

Each pass has exactly one responsibility and emits only structural facts.
No semantic reasoning, no reference resolution, no graph construction.
"""

from .calls import JavaCallIndexPass
from .configuration import JavaConfigurationIndexPass
from .entrypoints import JavaEntrypointIndexPass
from .events import JavaEventIndexPass
from .imports import JavaImportIndexPass
from .persistence import JavaPersistenceIndexPass
from .symbols import JavaSymbolIndexPass
from .tests import JavaTestIndexPass
from .types import JavaTypeIndexPass

__all__ = [
    "JavaCallIndexPass",
    "JavaConfigurationIndexPass",
    "JavaEntrypointIndexPass",
    "JavaEventIndexPass",
    "JavaImportIndexPass",
    "JavaPersistenceIndexPass",
    "JavaSymbolIndexPass",
    "JavaTestIndexPass",
    "JavaTypeIndexPass",
]

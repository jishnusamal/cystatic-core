"""Java indexing passes for the deterministic indexing pipeline.

Each pass has exactly one responsibility and emits only structural facts.
No semantic reasoning, no reference resolution, no graph construction.
"""

from .symbols import JavaSymbolIndexPass
from .imports import JavaImportIndexPass
from .calls import JavaCallIndexPass
from .entrypoints import JavaEntrypointIndexPass
from .types import JavaTypeIndexPass
from .persistence import JavaPersistenceIndexPass
from .events import JavaEventIndexPass
from .tests import JavaTestIndexPass
from .configuration import JavaConfigurationIndexPass

__all__ = [
    "JavaSymbolIndexPass",
    "JavaImportIndexPass",
    "JavaCallIndexPass",
    "JavaEntrypointIndexPass",
    "JavaTypeIndexPass",
    "JavaPersistenceIndexPass",
    "JavaEventIndexPass",
    "JavaTestIndexPass",
    "JavaConfigurationIndexPass",
]

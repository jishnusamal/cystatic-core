"""Python indexing passes for the deterministic indexing pipeline.

Each pass has exactly one responsibility and emits only structural facts.
No semantic reasoning, no reference resolution, no graph construction.
"""

from .symbols import PythonSymbolIndexPass
from .imports import PythonImportIndexPass
from .calls import PythonCallIndexPass
from .entrypoints import PythonEntrypointIndexPass
from .types import PythonTypeIndexPass
from .persistence import PythonPersistenceIndexPass
from .events import PythonEventIndexPass
from .tests import PythonTestIndexPass
from .configuration import PythonConfigurationIndexPass

__all__ = [
    "PythonSymbolIndexPass",
    "PythonImportIndexPass",
    "PythonCallIndexPass",
    "PythonEntrypointIndexPass",
    "PythonTypeIndexPass",
    "PythonPersistenceIndexPass",
    "PythonEventIndexPass",
    "PythonTestIndexPass",
    "PythonConfigurationIndexPass",
]

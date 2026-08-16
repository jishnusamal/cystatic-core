"""Python indexing passes for the deterministic indexing pipeline.

Each pass has exactly one responsibility and emits only structural facts.
No semantic reasoning, no reference resolution, no graph construction.
"""

from .calls import PythonCallIndexPass
from .configuration import PythonConfigurationIndexPass
from .entrypoints import PythonEntrypointIndexPass
from .events import PythonEventIndexPass
from .imports import PythonImportIndexPass
from .persistence import PythonPersistenceIndexPass
from .symbols import PythonSymbolIndexPass
from .tests import PythonTestIndexPass
from .types import PythonTypeIndexPass

__all__ = [
    "PythonCallIndexPass",
    "PythonConfigurationIndexPass",
    "PythonEntrypointIndexPass",
    "PythonEventIndexPass",
    "PythonImportIndexPass",
    "PythonPersistenceIndexPass",
    "PythonSymbolIndexPass",
    "PythonTestIndexPass",
    "PythonTypeIndexPass",
]

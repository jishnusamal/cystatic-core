import sys
from typing import Any


def get_retained_size(obj: Any, seen: set[int] | None = None) -> int:
    """Recursively calculates the size of a Python object, including referenced objects.
    Avoids infinite loops by tracking seen object IDs.
    """
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0

    seen.add(obj_id)
    size = sys.getsizeof(obj)

    # Basic types that don't reference other custom objects in a way we need to traverse
    if isinstance(obj, (str, bytes, int, float, bool, type(None))):
        return size

    # Dictionaries
    if isinstance(obj, dict):
        size += sum(
            get_retained_size(k, seen) + get_retained_size(v, seen)
            for k, v in obj.items()
        )
        return size

    # Lists, Tuples, Sets, Frozensets
    if isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(get_retained_size(item, seen) for item in obj)
        return size

    # Dataclasses and user-defined objects with slots/dict
    if hasattr(obj, "__dict__"):
        size += get_retained_size(obj.__dict__, seen)
    if hasattr(obj, "__slots__"):
        for slot in obj.__slots__:
            if hasattr(obj, slot):
                size += get_retained_size(getattr(obj, slot), seen)

    return size

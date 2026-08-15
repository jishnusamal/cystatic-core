import dataclasses
import json

import pytest

from engine.repository.facts import (
    File,
    FileId,
    Symbol,
    SymbolId,
    SymbolKind,
    SymbolVisibility,
)


def test_fact_immutability_and_slots():
    """Verify all defined facts use slots, are frozen, and cannot be mutated."""
    file_fact = File(id=FileId(1), path="app.py", language="python")

    # Assert slots are used
    assert hasattr(file_fact, "__slots__")
    assert not hasattr(file_fact, "__dict__")

    # Assert immutability
    with pytest.raises(dataclasses.FrozenInstanceError):
        file_fact.path = "new_app.py"  # type: ignore


def test_hashing_and_equality():
    """Verify we can put facts in sets/dicts, and they evaluate equality properly."""
    f1 = File(id=FileId(1), path="app.py", language="python")
    f2 = File(id=FileId(1), path="app.py", language="python")
    f3 = File(id=FileId(2), path="app.py", language="python")

    assert f1 == f2
    assert f1 != f3

    fact_set = {f1, f3}
    assert len(fact_set) == 2
    assert f2 in fact_set


def test_serialization():
    """Verify dataclass asdict serialization produces a clean primitive dictionary."""
    symbol_fact = Symbol(
        id=SymbolId(101),
        name="process_payment",
        file_id=FileId(1),
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=10,
        end_line=20,
        visibility=SymbolVisibility.PUBLIC,
        parent_symbol_id=None,
    )

    data = dataclasses.asdict(symbol_fact)
    assert data["id"] == 101
    assert data["name"] == "process_payment"
    assert data["file_id"] == 1
    assert data["kind"] == "function"
    assert data["visibility"] == "public"

    serialized = json.dumps(data)
    assert "process_payment" in serialized

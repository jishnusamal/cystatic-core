import dataclasses
import pytest

from engine.language.base import LanguageSpec


def test_language_spec_basic_construction():
    """Verify basic construction of LanguageSpec."""
    spec = LanguageSpec(
        id="typescript",
        extensions=frozenset({".ts", ".tsx"}),
    )
    assert spec.id == "typescript"
    assert spec.extensions == frozenset({".ts", ".tsx"})
    assert spec.filenames == frozenset()


def test_language_spec_immutability():
    """Verify that LanguageSpec is immutable."""
    spec = LanguageSpec(
        id="typescript",
        extensions=frozenset({".ts", ".tsx"}),
    )

    # Reassigning fields should raise FrozenInstanceError
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.id = "python"  # type: ignore

    # Mutating extensions (frozenset) should fail
    with pytest.raises(AttributeError):
        spec.extensions.add(".js")  # type: ignore


def test_language_spec_hashability():
    """Verify that LanguageSpec is hashable and can be used in sets/dicts."""
    spec1 = LanguageSpec(
        id="typescript",
        extensions=frozenset({".ts", ".tsx"}),
    )
    spec2 = LanguageSpec(
        id="python",
        extensions=frozenset({".py"}),
    )
    
    # Hash check
    assert isinstance(hash(spec1), int)
    
    # Set usage
    specs_set = {spec1, spec2}
    assert spec1 in specs_set
    assert spec2 in specs_set


def test_language_spec_filenames():
    """Verify that filename metadata is correctly stored and queried."""
    spec = LanguageSpec(
        id="dockerfile",
        extensions=frozenset(),
        filenames=frozenset({"Dockerfile"}),
    )
    assert "Dockerfile" in spec.filenames
    assert spec.extensions == frozenset()


def test_language_spec_empty_id():
    """Verify that an empty language ID raises a ValueError."""
    with pytest.raises(ValueError) as exc_info:
        LanguageSpec(
            id="",
            extensions=frozenset({".py"}),
        )
    assert "LanguageSpec.id must not be empty" in str(exc_info.value)


def test_language_spec_type_validation():
    """Verify type validation for extensions and filenames fields."""
    with pytest.raises(TypeError) as exc_info:
        LanguageSpec(
            id="python",
            extensions={".py"},  # type: ignore
        )
    assert "extensions must be a frozenset" in str(exc_info.value)

    with pytest.raises(TypeError) as exc_info:
        LanguageSpec(
            id="python",
            extensions=frozenset({".py"}),
            filenames={"Dockerfile"},  # type: ignore
        )
    assert "filenames must be a frozenset" in str(exc_info.value)

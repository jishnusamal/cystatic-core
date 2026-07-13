"""Tests for the repository compiler."""

import pytest
from language_adapters.python.adapter import PythonLanguageAdapter
from language_adapters.model import SymbolKind, SymbolVisibility, EntryPointKind


@pytest.fixture
def sample_source_files():
    """
    Create a sample set of Python source files for testing.

    This represents the raw repository input the language adapter compiles.
    """
    service_py = '''
"""Checkout service."""

from payment.processor import charge_card


def confirm_checkout():
    """Confirm a checkout."""
    validate_coupon()
    charge_card()
    save_order()


def validate_coupon():
    pass


def charge_card():
    pass


class CheckoutService:
    def process_payment(self):
        pass
'''

    processor_py = '''
"""Payment processor."""


def charge_card():
    pass


def save_order():
    pass
'''
    return {
        "checkout/service.py": service_py,
        "payment/processor.py": processor_py,
    }


class TestPythonLanguageAdapter:
    """Test the repository compiler."""
    
    def test_compiler_initialization(self):
        """Test that compiler initializes correctly."""
        adapter = PythonLanguageAdapter()
        assert adapter is not None
        assert adapter.get_language() == "python"
    
    def test_compiler_pass_names(self):
        """Test that compiler has correct pass names."""
        adapter = PythonLanguageAdapter()
        pass_names = adapter.get_compiler_passes()
        assert pass_names == [
            "symbol_collection",
            "reference_resolution",
            "call_graph",
            "endpoint_discovery",
            "type_relationships",
            "async_entry_points",
            "persistence_models",
            "repository_methods",
            "event_constructs",
            "test_definitions",
            "configuration_references",
        ]
    
    def test_full_compilation(self, sample_source_files):
        """Test full compilation pipeline."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Verify model was created
        assert model is not None
        assert isinstance(model.symbols, frozenset)
        assert len(model.symbols) > 0

    def test_symbol_collection(self, sample_source_files):
        """Test that symbols are collected correctly."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Should have symbols from both files
        assert len(model.symbols) >= 5  # At least 3 functions + 1 class + 1 method

        # Check for specific symbols
        symbol_ids = [s.id for s in model.symbols]

        # Functions
        assert "python://checkout/service.py::confirm_checkout" in symbol_ids
        assert "python://checkout/service.py::validate_coupon" in symbol_ids
        assert "python://checkout/service.py::charge_card" in symbol_ids

        # Class
        assert "python://checkout/service.py#CheckoutService" in symbol_ids

        # Method
        assert "python://checkout/service.py#CheckoutService.process_payment" in symbol_ids

    def test_symbol_properties(self, sample_source_files):
        """Test that symbol properties are preserved."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Find confirm_checkout function
        confirm_checkout = model.get_symbol_by_id("python://checkout/service.py::confirm_checkout")

        assert confirm_checkout is not None
        assert confirm_checkout.name == "confirm_checkout"
        assert confirm_checkout.kind == SymbolKind.FUNCTION
        assert confirm_checkout.language == "python"
        assert confirm_checkout.file == "checkout/service.py"
        assert confirm_checkout.visibility == SymbolVisibility.PUBLIC
        assert confirm_checkout.properties["docstring"] == "Confirm a checkout."

    def test_call_graph(self, sample_source_files):
        """Test that call graph is built correctly."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Should have call edges
        assert len(model.call_graph.edges) > 0

        # Find edges from confirm_checkout
        confirm_checkout_id = "python://checkout/service.py::confirm_checkout"
        calls = model.get_calls_for(confirm_checkout_id)

        # Should call validate_coupon and charge_card
        callee_ids = [edge.callee_id for edge in calls]
        assert "python://checkout/service.py::validate_coupon" in callee_ids
        assert "python://checkout/service.py::charge_card" in callee_ids

    def test_get_symbols_by_kind(self, sample_source_files):
        """Test filtering symbols by kind."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Get all functions
        functions = model.get_symbols_by_kind("function")
        assert len(functions) == 5  # 3 in checkout + 2 in payment

        # Get all classes
        classes = model.get_symbols_by_kind("class")
        assert len(classes) == 1
        assert next(iter(classes)).name == "CheckoutService"

    def test_get_symbols_by_file(self, sample_source_files):
        """Test filtering symbols by file."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Get symbols from checkout/service.py
        checkout_symbols = model.get_symbols_by_file("checkout/service.py")
        assert len(checkout_symbols) == 6  # 3 functions + 1 class + 1 method + 1 import

        # Get symbols from payment/processor.py
        payment_symbols = model.get_symbols_by_file("payment/processor.py")
        assert len(payment_symbols) == 2  # 2 functions

    def test_get_called_by(self, sample_source_files):
        """Test finding who calls a specific symbol."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": sample_source_files})

        # Find who calls charge_card
        charge_card_id = "python://checkout/service.py::charge_card"
        called_by = model.get_called_by(charge_card_id)

        # confirm_checkout should call charge_card
        assert len(called_by) == 1
        assert called_by[0].caller_id == "python://checkout/service.py::confirm_checkout"

    def test_empty_source_files(self):
        """Test compilation with empty source files."""
        adapter = PythonLanguageAdapter()
        model = adapter.compile({"files": {}})

        assert model is not None
        assert len(model.symbols) == 0
        assert len(model.call_graph.edges) == 0
        assert len(model.entry_points) == 0
        assert len(model.reference_graph.edges) == 0

    def test_deterministic_output(self, sample_source_files):
        """Test that compilation is deterministic."""
        adapter = PythonLanguageAdapter()

        # Compile twice
        model1 = adapter.compile({"files": sample_source_files})
        model2 = adapter.compile({"files": sample_source_files})

        # Results should be identical
        assert model1.symbols == model2.symbols
        assert model1.call_graph.edges == model2.call_graph.edges
        assert model1.entry_points == model2.entry_points
        assert model1.reference_graph.edges == model2.reference_graph.edges

"""Tests for the TypeScript Language Adapter."""

import pytest

from engine.language.typescript.adapter import TypeScriptLanguageAdapter
from engine.language.typescript.plugin import TypeScriptPlugin


@pytest.fixture
def sample_ts_files():
    """Create a sample set of TypeScript source files for testing."""
    service_ts = """
import { chargeCard } from "./payment";
import * as fs from "fs";

app.get("/users", confirmCheckout);
router.post("/checkout-post", confirmCheckout);

export function confirmCheckout() {
    validateCoupon();
    chargeCard();
    saveOrder();
}

function validateCoupon() {
}

class CheckoutService extends BaseService {
    @Get("/checkout-get")
    processPayment() {
        this.confirmCheckout();
    }
}
"""
    payment_ts = """
export function chargeCard() {
}
"""
    return {
        "checkout/service.ts": service_ts,
        "payment.ts": payment_ts,
    }


class TestTypeScriptLanguageAdapter:
    """Test suite for TypeScriptLanguageAdapter."""

    def test_adapter_initialization(self):
        """Test that adapter initializes correctly."""
        adapter = TypeScriptLanguageAdapter()
        assert adapter is not None
        assert adapter.get_language() == "typescript"

    def test_plugin_capabilities(self):
        """Test that TypeScriptPlugin advertises correct spec and capabilities."""
        plugin = TypeScriptPlugin()
        assert plugin.spec.id == "typescript"
        assert plugin.spec.extensions == frozenset({".ts", ".tsx", ".mts", ".cts"})
        assert plugin.spec.capabilities.symbols is True
        assert plugin.spec.capabilities.imports is True
        assert plugin.spec.capabilities.calls is True
        assert plugin.spec.capabilities.types is True
        assert plugin.spec.capabilities.entrypoints is True

    def test_full_compilation(self, sample_ts_files):
        """Test compiling TS repository snapshots."""
        adapter = TypeScriptLanguageAdapter()
        model = adapter.compile({"files": sample_ts_files})
        assert model is not None
        assert isinstance(model.symbols, frozenset)
        assert len(model.symbols) > 0

    def test_symbol_collection(self, sample_ts_files):
        """Test that symbols are collected correctly."""
        adapter = TypeScriptLanguageAdapter()
        model = adapter.compile({"files": sample_ts_files})

        symbol_ids = [s.id for s in model.symbols]

        # Verify functions
        assert "typescript://checkout/service.ts::confirmCheckout" in symbol_ids
        assert "typescript://checkout/service.ts::validateCoupon" in symbol_ids
        assert "typescript://payment.ts::chargeCard" in symbol_ids

        # Verify class and method
        assert "typescript://checkout/service.ts#CheckoutService" in symbol_ids
        assert "typescript://checkout/service.ts#CheckoutService.processPayment" in symbol_ids

    def test_import_collection(self, sample_ts_files):
        """Test that imports are extracted correctly."""
        adapter = TypeScriptLanguageAdapter()
        index = adapter.build_index({"files": sample_ts_files})

        service_file_index = next(f for f in index.files if f.path == "checkout/service.ts")
        imports = service_file_index.imports

        modules = [imp.module for imp in imports]
        assert "./payment" in modules
        assert "fs" in modules

    def test_call_collection(self, sample_ts_files):
        """Test that function and method calls are extracted correctly."""
        adapter = TypeScriptLanguageAdapter()
        index = adapter.build_index({"files": sample_ts_files})

        service_file_index = next(f for f in index.files if f.path == "checkout/service.ts")
        calls = service_file_index.calls

        # Check calls inside confirmCheckout
        confirm_calls = [c for c in calls if c.caller == "confirmCheckout"]
        callees = [c.callee for c in confirm_calls]
        assert "validateCoupon" in callees
        assert "chargeCard" in callees
        assert "saveOrder" in callees

        # Check call inside processPayment
        method_calls = [c for c in calls if c.caller == "processPayment"]
        assert len(method_calls) == 1
        assert method_calls[0].callee == "confirmCheckout"
        assert method_calls[0].receiver == "this"
        assert method_calls[0].caller_parent == "CheckoutService"

    def test_type_relationships(self, sample_ts_files):
        """Test that type relationships are extracted correctly."""
        adapter = TypeScriptLanguageAdapter()
        index = adapter.build_index({"files": sample_ts_files})

        service_file_index = next(f for f in index.files if f.path == "checkout/service.ts")
        relations = service_file_index.type_relationships

        assert len(relations) == 1
        assert relations[0].source == "CheckoutService"
        assert relations[0].target == "BaseService"
        assert relations[0].relation_type == "extends"

    def test_entrypoint_collection(self, sample_ts_files):
        """Test that entrypoints are extracted correctly."""
        adapter = TypeScriptLanguageAdapter()
        index = adapter.build_index({"files": sample_ts_files})

        service_file_index = next(f for f in index.files if f.path == "checkout/service.ts")
        entrypoints = service_file_index.entrypoints

        routes = [ep.route for ep in entrypoints]
        assert "GET /users" in routes
        assert "POST /checkout-post" in routes
        assert "GET /checkout-get" in routes

        # Check handler names mapping
        user_ep = next(ep for ep in entrypoints if ep.route == "GET /users")
        assert user_ep.handler == "confirmCheckout"

        post_ep = next(ep for ep in entrypoints if ep.route == "POST /checkout-post")
        assert post_ep.handler == "confirmCheckout"

        get_ep = next(ep for ep in entrypoints if ep.route == "GET /checkout-get")
        assert get_ep.handler == "processPayment"

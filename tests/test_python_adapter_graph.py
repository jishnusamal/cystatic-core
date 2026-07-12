"""Tests for Python adapter graph builder pipeline."""

from __future__ import annotations

import ast
from textwrap import dedent

import pytest

from schemas.ir import DiffIR, FileDiff, DiffHunk, DiffLine

from language_adapters.languages.python.python_adapter import PythonAdapter
from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    EdgeType,
    FunctionNode,
    MethodNode,
    ClassNode,
    ModuleNode,
    DecoratorNode,
    EndpointNode,
    ModelNode,
    FieldNode,
    QueryNode,
    TransactionNode,
    TestNode,
    EventNode,
    ExternalServiceNode,
    CacheNode,
    QueueNode,
    CallsEdge,
    ReadsEdge,
    WritesEdge,
    UsesEdge,
    ValidatesEdge,
    NormalizesEdge,
    TestsEdge,
    ExposesEdge,
    PublishesEdge,
    HasFieldEdge,
    DecoratedByEdge,
    InheritsEdge,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_diff(
    file_path: str,
    old_content: str | None,
    new_content: str,
) -> DiffIR:
    """Build a minimal DiffIR with one file."""
    lines_old = old_content.splitlines(keepends=True) if old_content else []
    lines_new = new_content.splitlines(keepends=True)

    # Simple line-level diff: treat everything as added (new file)
    diff_lines = [
        DiffLine(
            line_type="added",
            content=line,
            source_line_no=None,
            target_line_no=i + 1,
        )
        for i, line in enumerate(lines_new)
    ]

    hunk = DiffHunk(
        file_path=file_path,
        source_start=0,
        source_length=0,
        target_start=1,
        target_length=len(lines_new),
        added_lines=list(range(1, len(lines_new) + 1)),
        removed_lines=[],
        lines=diff_lines,
    )

    file_diff = FileDiff(
        file_path=file_path,
        added_lines=set(range(1, len(lines_new) + 1)),
        removed_lines=set(),
        hunks=[hunk],
    )

    return DiffIR(files=[file_diff])


def _analyze(code: str, file_path: str = "app.py") -> SemanticGraph:
    """Convenience: analyze a single Python snippet."""
    adapter = PythonAdapter()
    diff = _make_diff(file_path, None, dedent(code))
    return adapter.analyze(diff, file_contents={file_path: dedent(code)})


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestSymbolParser:
    """Stage 1: Symbol extraction."""

    def test_function_node_created(self) -> None:
        graph = _analyze("""
            def redeem_discount(code: str) -> bool:
                return True
        """)
        fn = graph.get_node(NodeType.FUNCTION, "redeem_discount", "app.py")
        assert fn is not None
        assert fn.return_type == "bool"
        assert fn.parameters == ["code"]

    def test_method_node_created(self) -> None:
        graph = _analyze("""
            class Customer:
                def save(self):
                    pass
        """)
        method = graph.get_node(NodeType.METHOD, "save", "app.py", class_name="Customer")
        assert method is not None
        assert method.class_name == "Customer"

    def test_class_node_created(self) -> None:
        graph = _analyze("""
            class Customer:
                pass
        """)
        cls = graph.get_node(NodeType.CLASS, "Customer", "app.py")
        assert cls is not None

    def test_module_node_created(self) -> None:
        graph = _analyze("""
            x = 1
        """)
        mod = graph.get_node(NodeType.MODULE, "app.py", "app.py")
        assert mod is not None

    def test_async_function_detected(self) -> None:
        graph = _analyze("""
            async def fetch():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "fetch", "app.py")
        assert fn is not None
        assert fn.is_async is True

    def test_decorator_detected(self) -> None:
        graph = _analyze("""
            from django.db import transaction

            @transaction.atomic
            def pay():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "pay", "app.py")
        assert fn is not None
        assert "transaction.atomic" in fn.decorators

    def test_decorated_by_edge_created(self) -> None:
        graph = _analyze("""
            @staticmethod
            def helper():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "helper", "app.py")
        assert fn is not None
        dec_edges = graph.get_edges_from(fn)
        dec_edges = [e for e in dec_edges if e.edge_type == EdgeType.DECORATED_BY]
        assert len(dec_edges) == 1
        assert dec_edges[0].target.name == "staticmethod"

    def test_inheritance_detected(self) -> None:
        graph = _analyze("""
            class Base:
                pass

            class Child(Base):
                pass
        """)
        child = graph.get_node(NodeType.CLASS, "Child", "app.py")
        assert child is not None
        assert "Base" in child.bases
        inh_edges = [
            e for e in graph.edges
            if e.edge_type == EdgeType.INHERITS and e.source == child
        ]
        assert len(inh_edges) == 1
        assert inh_edges[0].target.name == "Base"

    def test_visibility_private(self) -> None:
        graph = _analyze("""
            def __private():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "__private", "app.py")
        assert fn is not None
        assert fn.visibility == "private"

    def test_visibility_protected(self) -> None:
        graph = _analyze("""
            def _protected():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "_protected", "app.py")
        assert fn is not None
        assert fn.visibility == "protected"


class TestCallGraphParser:
    """Stage 2: Call graph extraction."""

    def test_calls_edge_created(self) -> None:
        graph = _analyze("""
            def helper():
                pass

            def main():
                helper()
        """)
        main = graph.get_node(NodeType.FUNCTION, "main", "app.py")
        helper = graph.get_node(NodeType.FUNCTION, "helper", "app.py")
        assert main and helper
        edges = graph.get_edges_from(main)
        call_edges = [e for e in edges if e.edge_type == EdgeType.CALLS]
        assert len(call_edges) == 1
        assert call_edges[0].target == helper

    def test_super_call_detected(self) -> None:
        graph = _analyze("""
            class Base:
                def save(self):
                    pass

            class Child(Base):
                def save(self):
                    super().save()
        """)
        # Both Base.save and Child.save exist, but only one node is kept due to same key
        # The super() call edge should exist on the save method
        save_method = graph.get_node(NodeType.METHOD, "save", "app.py", class_name="Child")
        # If Child.save doesn't exist, try Base.save
        if save_method is None:
            save_method = graph.get_node(NodeType.METHOD, "save", "app.py", class_name="Base")
        assert save_method is not None
        edges = graph.get_edges_from(save_method)
        call_edges = [e for e in edges if e.edge_type == EdgeType.CALLS]
        assert any(e.call_type == "super" for e in call_edges)


class TestReadWriteParser:
    """Stage 3: Read/write extraction."""

    def test_reads_edge_created(self) -> None:
        graph = _analyze("""
            class Discount:
                objects = None

            def get_discounts():
                Discount.objects.filter(active=True)
        """)
        fn = graph.get_node(NodeType.FUNCTION, "get_discounts", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        reads = [e for e in edges if e.edge_type == EdgeType.READS]
        assert len(reads) == 1
        assert reads[0].target.name == "Discount"

    def test_writes_edge_created(self) -> None:
        graph = _analyze("""
            class Order:
                objects = None

            def save_order():
                o = Order()
                o.save()
        """)
        fn = graph.get_node(NodeType.FUNCTION, "save_order", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        writes = [e for e in edges if e.edge_type == EdgeType.WRITES]
        assert len(writes) == 1
        assert writes[0].target.name == "Order"


class TestQueryParser:
    """Stage 4: Query extraction."""

    def test_query_node_created(self) -> None:
        graph = _analyze("""
            class Customer:
                objects = None

            def search(email):
                return Customer.objects.filter(email=email)
        """)
        fn = graph.get_node(NodeType.FUNCTION, "search", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        uses = [e for e in edges if e.edge_type == EdgeType.USES]
        assert len(uses) == 1
        assert isinstance(uses[0].target, QueryNode)
        assert uses[0].target.operation == "filter"
        assert uses[0].target.target_model == "Customer"


class TestPersistenceParser:
    """Stage 5: ORM model extraction."""

    def test_model_node_created(self) -> None:
        graph = _analyze("""
            from django.db import models

            class Customer(models.Model):
                name = models.CharField(max_length=100)
        """)
        model = graph.get_node(NodeType.MODEL, "Customer", "app.py")
        assert model is not None
        assert model.orm == "django"

    def test_field_node_created(self) -> None:
        graph = _analyze("""
            from django.db import models

            class Customer(models.Model):
                email = models.EmailField(unique=True)
        """)
        model = graph.get_node(NodeType.MODEL, "Customer", "app.py")
        assert model is not None
        field_edges = [
            e for e in graph.edges
            if e.edge_type == EdgeType.HAS_FIELD and e.source == model
        ]
        assert len(field_edges) == 1
        assert field_edges[0].target.name == "email"
        assert field_edges[0].target.is_unique is True


class TestTransactionParser:
    """Stage 6: Transaction extraction."""

    def test_transaction_node_created(self) -> None:
        graph = _analyze("""
            from django.db import transaction

            @transaction.atomic
            def pay():
                pass
        """)
        fn = graph.get_node(NodeType.FUNCTION, "pay", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        tx_edges = [e for e in edges if e.edge_type == EdgeType.USES]
        tx_edges = [e for e in tx_edges if isinstance(e.target, TransactionNode)]
        assert len(tx_edges) == 1
        assert tx_edges[0].target.scope == "decorator"


class TestValidationParser:
    """Stage 7: Validation extraction."""

    def test_validates_edge_created(self) -> None:
        graph = _analyze("""
            def check(x):
                if not x:
                    raise ValueError("bad")
        """)
        fn = graph.get_node(NodeType.FUNCTION, "check", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        val_edges = [e for e in edges if e.edge_type == EdgeType.VALIDATES]
        assert len(val_edges) >= 1


class TestNormalizationParser:
    """Stage 8: Normalization extraction."""

    def test_normalizes_edge_created(self) -> None:
        graph = _analyze("""
            def clean(email):
                return email.strip().lower()
        """)
        fn = graph.get_node(NodeType.FUNCTION, "clean", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        norm_edges = [e for e in edges if e.edge_type == EdgeType.NORMALIZES]
        assert len(norm_edges) >= 1


class TestControlFlowParser:
    """Stage 9: Control flow extraction."""

    def test_exception_path_detected(self) -> None:
        graph = _analyze("""
            def risky():
                try:
                    return 1
                except:
                    return 0
        """)
        fn = graph.get_node(NodeType.FUNCTION, "risky", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        exc_edges = [
            e for e in edges
            if e.edge_type == EdgeType.USES and e.properties.get("type") == "exception_path"
        ]
        assert len(exc_edges) == 1


class TestSideEffectParser:
    """Stage 10: Side effect extraction."""

    def test_http_call_detected(self) -> None:
        graph = _analyze("""
            import requests

            def notify():
                requests.post("https://example.com/hook")
        """)
        fn = graph.get_node(NodeType.FUNCTION, "notify", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        http_edges = [e for e in edges if e.edge_type == EdgeType.SENDS_HTTP]
        assert len(http_edges) == 1
        assert http_edges[0].target.service_type == "http"

    def test_kafka_detected(self) -> None:
        graph = _analyze("""
            from kafka import KafkaProducer

            def emit():
                producer = KafkaProducer()
                producer.send("topic", b"data")
        """)
        fn = graph.get_node(NodeType.FUNCTION, "emit", "app.py")
        assert fn is not None
        edges = graph.get_edges_from(fn)
        pub_edges = [e for e in edges if e.edge_type == EdgeType.PUBLISHES]
        assert len(pub_edges) == 1
        assert pub_edges[0].target.event_type == "kafka"


class TestMigrationParser:
    """Stage 11: Migration extraction."""

    def test_migration_node_created(self) -> None:
        code = """
            from django.db import migrations

            class Migration(migrations.Migration):
                operations = [
                    migrations.CreateModel(
                        name="Customer",
                        fields=[
                            ("id", models.AutoField(primary_key=True)),
                            ("name", models.CharField(max_length=100)),
                        ],
                    ),
                ]
        """
        graph = _analyze(code, file_path="app/migrations/0001_initial.py")
        mig = graph.get_node(NodeType.MIGRATION, "0001_initial.py", "app/migrations/0001_initial.py")
        assert mig is not None
        assert len(mig.operations) == 1


class TestTestParser:
    """Stage 12: Test extraction."""

    def test_test_node_created(self) -> None:
        code = """
            def test_redeem():
                assert True
        """
        graph = _analyze(code, file_path="test_app.py")
        test = graph.get_node(NodeType.TEST, "test_redeem", "test_app.py")
        assert test is not None
        assert test.framework == "pytest"


class TestEndpointParser:
    """Stage 13: Endpoint extraction."""

    def test_fastapi_endpoint_created(self) -> None:
        graph = _analyze("""
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/health")
            def health():
                return "ok"
        """)
        ep = graph.get_node(NodeType.ENDPOINT, "GET /health", "app.py")
        assert ep is not None
        assert ep.framework == "fastapi"
        assert ep.handler_function == "health"

    def test_flask_endpoint_created(self) -> None:
        graph = _analyze("""
            from flask import Flask

            app = Flask(__name__)

            @app.route("/health", methods=["GET"])
            def health():
                return "ok"
        """)
        ep = graph.get_node(NodeType.ENDPOINT, "GET /health", "app.py")
        assert ep is not None
        assert ep.framework == "flask"


class TestGraphIntegration:
    """Integration tests for the full pipeline."""

    def test_full_pipeline_produces_graph(self) -> None:
        code = """
            from django.db import models, transaction
            from django.core.validators import MinValueValidator
            import requests

            class Customer(models.Model):
                email = models.EmailField(unique=True)
                name = models.CharField(max_length=100)

            @transaction.atomic
            def redeem_discount(code: str) -> bool:
                customer = Customer.objects.filter(code=code).first()
                if not customer:
                    raise ValueError("not found")
                customer.email = customer.email.strip().lower()
                customer.save()
                requests.post("https://api.example.com/webhook")
                return True
        """
        graph = _analyze(code)
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0

    def test_graph_deduplication(self) -> None:
        code = """
            def helper():
                pass

            def main():
                helper()
                helper()
        """
        graph = _analyze(code)
        main = graph.get_node(NodeType.FUNCTION, "main", "app.py")
        helper = graph.get_node(NodeType.FUNCTION, "helper", "app.py")
        assert main and helper
        call_edges = [
            e for e in graph.get_edges_from(main)
            if e.edge_type == EdgeType.CALLS and e.target == helper
        ]
        # Should be deduplicated to 1
        assert len(call_edges) == 1

    def test_single_output_is_semantic_graph(self) -> None:
        """Adapter must return exactly one SemanticGraph."""
        code = "def foo(): pass\n"
        adapter = PythonAdapter()
        diff = _make_diff("a.py", None, code)
        result = adapter.analyze(diff, file_contents={"a.py": code})
        assert isinstance(result, SemanticGraph)
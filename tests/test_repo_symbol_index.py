"""Tests for the RepositorySymbolIndex."""

from __future__ import annotations

from core_engine.repo_symbol_index import RepositorySymbolIndex


def test_repo_index_extracts_function_names() -> None:
    files = [
        (
            "src/billing/service.py",
            "def compute_total(items):\n    return sum(items)\n\n"
            "async def refund(order_id):\n    return order_id\n",
        ),
        (
            "src/orders/service.py",
            "def place_order(cart):\n    return None\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    assert "compute_total" in idx.known_symbols
    assert "refund" in idx.known_symbols
    assert "place_order" in idx.known_symbols
    assert "__init__" not in idx.known_symbols
    assert "src/billing/service.py" in idx.file_symbols
    assert "compute_total" in idx.file_symbols["src/billing/service.py"]


def test_repo_index_extracts_fastapi_endpoints() -> None:
    files = [
        (
            "src/api/users.py",
            "@router.get('/users/{id}')\n"
            "async def get_user(id: int):\n    return id\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    assert len(idx.all_endpoints) == 1
    ep = idx.all_endpoints[0]
    assert ep["route"] == "/users/{id}"
    assert ep["method"] == "GET"
    assert ep["function"] == "get_user"


def test_repo_index_extracts_flask_endpoints() -> None:
    files = [
        (
            "src/app.py",
            "@app.route('/health', methods=['GET', 'POST'])\n"
            "def health():\n    return 'ok'\n",
        ),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    assert len(idx.all_endpoints) == 1
    ep = idx.all_endpoints[0]
    assert ep["route"] == "/health"
    assert ep["method"] == "GET,POST"
    assert ep["function"] == "health"


def test_repo_index_skips_malformed_files() -> None:
    files = [
        ("broken.py", "def oops(\n"),
        ("good.py", "def fine():\n    pass\n"),
    ]
    idx = RepositorySymbolIndex.from_files(files)
    assert "fine" in idx.known_symbols
    assert "broken.py" in idx.file_symbols
    assert idx.file_symbols["broken.py"] == set()


def test_repo_index_merge() -> None:
    left = RepositorySymbolIndex.from_files([
        ("a.py", "def left_fn(): pass\n"),
    ])
    right = RepositorySymbolIndex.from_files([
        ("b.py", "def right_fn(): pass\n"),
    ])
    left.merge(right)
    assert "left_fn" in left.known_symbols
    assert "right_fn" in left.known_symbols


def test_repo_index_stats() -> None:
    idx = RepositorySymbolIndex.from_files([
        ("a.py", "def foo(): pass\n"),
        ("b.py", "@router.get('/x')\ndef bar(): pass\n"),
    ])
    s = idx.stats()
    assert s["known_symbol_count"] >= 2
    assert s["endpoint_count"] >= 1
    assert s["indexed_file_count"] == 2

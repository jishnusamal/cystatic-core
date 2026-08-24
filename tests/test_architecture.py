"""Architectural boundary tests.

Enforces dependency rules between language-specific frontends and the
language-independent analysis engine.
"""

import ast
import os
from pathlib import Path


def find_violations_in_file(
    file_path: Path,
    forbidden_prefixes: list[str],
    check_ast_import: bool = False,
) -> list[str]:
    """Scans a file for forbidden imports and returns a list of violation messages."""
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:  # noqa: BLE001 -- unparsable files are skipped in architecture scan
        return [f"Failed to parse {file_path}: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                # Check for standard forbidden prefixes/modules
                for prefix in forbidden_prefixes:
                    if name == prefix or name.startswith(prefix + "."):
                        violations.append(
                            f"{file_path}:{node.lineno}: Prohibited import of '{name}'"
                        )
                # Check for standard python ast module if requested
                if check_ast_import and (name == "ast" or name.startswith("ast.")):
                    violations.append(
                        f"{file_path}:{node.lineno}: Prohibited import of '{name}' (standard ast library)"
                    )

        elif isinstance(node, ast.ImportFrom) and node.module:
            # Resolve relative imports if needed, but in this engine imports are absolute
            module_name = node.module
            for prefix in forbidden_prefixes:
                if module_name == prefix or module_name.startswith(prefix + "."):
                    violations.append(
                        f"{file_path}:{node.lineno}: Prohibited import from '{module_name}'"
                    )
            if check_ast_import and (module_name == "ast" or module_name.startswith("ast.")):
                violations.append(
                    f"{file_path}:{node.lineno}: Prohibited import from '{module_name}' (standard ast library)"
                )

    return violations


def test_language_independent_layers_do_not_import_language_implementations():
    """Verify downstream compilers do not import language adapters, base classes, or parser libraries."""
    project_root = Path(__file__).parent.parent
    
    # Packages that must operate entirely on language-independent representations
    independent_packages = [
        "engine/change",
        "engine/behavior",
        "engine/operational",
        "engine/discovery",
        "engine/review_context",
        "engine/llm_context",
    ]

    # Prohibited modules / packages in downstream compilers
    forbidden_prefixes = [
        "engine.language",  # Prohibits python, java, typescript concrete adapters and base adapter/passes
        "tree_sitter",
        "tree_sitter_languages",
    ]

    all_violations = []

    for pkg in independent_packages:
        pkg_dir = project_root / pkg
        if not pkg_dir.exists():
            continue

        for root, _, files in os.walk(pkg_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    violations = find_violations_in_file(
                        file_path=file_path,
                        forbidden_prefixes=forbidden_prefixes,
                        check_ast_import=True,  # Check standard ast library too
                    )
                    all_violations.extend(violations)

    assert not all_violations, (
        f"Found {len(all_violations)} architectural boundary violation(s):\n"
        + "\n".join(all_violations)
    )


def test_repository_layer_does_not_import_concrete_languages():
    """Verify repository layer remains language-neutral and does not import concrete language packages."""
    project_root = Path(__file__).parent.parent
    
    # The repository layer
    repository_dir = project_root / "engine/repository"
    
    # Concrete language packages that must not leak into repository layer
    forbidden_concrete_languages = [
        "engine.language.python",
        "engine.language.java",
        "engine.language.typescript",
        "tree_sitter",
        "tree_sitter_languages",
    ]

    all_violations = []

    if repository_dir.exists():
        for root, _, files in os.walk(repository_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    violations = find_violations_in_file(
                        file_path=file_path,
                        forbidden_prefixes=forbidden_concrete_languages,
                        check_ast_import=False,  # Repository is allowed to use ast if needed, but not concrete languages
                    )
                    all_violations.extend(violations)

    assert not all_violations, (
        f"Found {len(all_violations)} repository layer architectural violation(s):\n"
        + "\n".join(all_violations)
    )

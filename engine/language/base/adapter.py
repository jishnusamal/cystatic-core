"""Base language adapter - abstract interface for all language adapters."""

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from engine.language.base.graph_patcher import GraphPatcher
from engine.repository.model import (
    FileContribution,
    RepositoryGraph,
    RepositoryModel,
    SymbolKind,
)


class BaseLanguageAdapter(ABC):
    """
    Abstract base class for language adapters.

    All language adapters must implement this interface to ensure
    they produce a deterministic RepositoryModel.
    """

    @abstractmethod
    def get_language(self) -> str:
        """
        Get the language name this adapter handles.

        Returns:
            Language identifier (e.g., "python", "java")
        """

    @abstractmethod
    def compile(self, repository_input: dict[str, Any]) -> RepositoryModel:
        """
        Compile a repository into a RepositoryModel.

        Args:
            repository_input: Repository snapshot containing:
                - root_directory: str
                - language: str
                - files: dict[file_path, file_content]

        Returns:
            RepositoryModel: Language-independent repository representation
        """

    @abstractmethod
    def get_compiler_passes(self) -> list[str]:
        """
        Get the names of compiler passes this adapter uses.

        Returns:
            List of pass names in execution order
        """

    _semantic_compiler: Any

    @abstractmethod
    def _index_single_file(self, file_path: str, content: str, language: str) -> Any:
        """Parse and run indexing passes on a single source file."""

    def _build_index(self, files: dict[str, str], language: str) -> Any:
        """Build repository index from files."""
        raise NotImplementedError

    def compile_graph(self, repository_input: dict[str, Any]) -> RepositoryGraph:
        """Compile a repository into a patchable RepositoryGraph.

        Args:
            repository_input: Repository snapshot containing 'files' key.

        Returns:
            RepositoryGraph representing the compiled repository state.
        """
        files = repository_input.get("files", {})
        language = repository_input.get("language", self.get_language())

        index = self._build_index(files, language)
        model = self._semantic_compiler.compile(index, language)

        file_contributions = {}
        for file_index in index.files:
            content = files.get(file_index.path, "")
            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            file_contributions[file_index.path] = FileContribution.from_file_index(
                file_index, source_hash=h
            )

        symbols_dict = {}
        imports_dict = {}
        for symbol in model.symbols:
            if symbol.kind == SymbolKind.IMPORT:
                imports_dict[symbol.id] = symbol
            else:
                symbols_dict[symbol.id] = symbol

        graph = RepositoryGraph(
            files=file_contributions,
            symbols=symbols_dict,
            imports=imports_dict,
            call_graph=model.call_graph,
            reference_graph=model.reference_graph,
            type_relationship_graph=model.type_relationship_graph,
            entry_points=model.entry_points,
            async_entry_points=model.async_entry_points,
            persistence_models=model.persistence_models,
            repository_methods=model.repository_methods,
            event_constructs=model.event_constructs,
            test_definitions=model.test_definitions,
            configuration_references=model.configuration_references,
            metadata=model.metadata,
        )
        graph.rebuild_reverse_indexes()
        return graph

    def compile_incremental(
        self, base_graph: RepositoryGraph, repository_input: dict[str, Any]
    ) -> RepositoryGraph:
        """Compile changed files and patch the base_graph.

        Args:
            base_graph: The RepositoryGraph from the base revision.
            repository_input: Head repository snapshot containing 'files' key.

        Returns:
            RepositoryGraph: The patched, updated RepositoryGraph.
        """
        import os
        import time

        from core.logging import pipeline_logger, timer

        start_compile = time.perf_counter()
        pipeline_logger.log_pipeline(
            f"[incremental] Loading base RepositoryGraph ({len(base_graph.files)} base files, {len(base_graph.symbols)} symbols)",
            to_terminal=True,
        )

        repo_prefix = ""
        head_files_raw = repository_input.get("files", {})
        for cf in head_files_raw.keys():
            if cf is not None and os.path.isabs(cf):
                for gf in base_graph.files.keys():
                    cf_norm = cf.replace("\\", "/")
                    gf_norm = gf.replace("\\", "/")
                    if (
                        cf_norm.lower().endswith("/" + gf_norm.lower())
                        or cf_norm.lower() == gf_norm.lower()
                    ):
                        if cf_norm.lower() == gf_norm.lower():
                            repo_prefix = ""
                        else:
                            repo_prefix = cf[: -len(gf)]
                        break
                if repo_prefix:
                    break

        head_files_content = {}
        for k, v in head_files_raw.items():
            norm_k = k
            if repo_prefix and k.startswith(repo_prefix):
                norm_k = k[len(repo_prefix) :]
            norm_k = norm_k.replace("\\", "/")
            norm_k = norm_k.removeprefix("/")
            head_files_content[norm_k] = v

        base_files = set(base_graph.files.keys())
        language = repository_input.get("language", self.get_language())

        is_changed_only = repository_input.get("changed_only", False)

        if is_changed_only:
            added_files = {
                f
                for f, content in head_files_content.items()
                if content is not None and f not in base_graph.files
            }
            deleted_files = {
                f for f, content in head_files_content.items() if content is None
            }
            modified_files = {
                f
                for f, content in head_files_content.items()
                if content is not None and f in base_graph.files
            }
        else:
            head_files = set(head_files_content.keys())
            added_files = head_files - base_files
            deleted_files = base_files - head_files
            modified_files = base_files & head_files

        pipeline_logger.log_pipeline(
            f"[incremental] Identified {len(added_files)} added files, {len(modified_files)} modified files, {len(deleted_files)} deleted files",
            to_terminal=True,
        )

        changed_files: dict[str, FileContribution | None] = {}

        # Added and modified files parsing with progress logs
        to_parse = sorted(list(added_files | modified_files))
        pipeline_logger.log_pipeline(
            f"[incremental] Parsing changed files (0/{len(to_parse)})...",
            to_terminal=True,
        )

        for idx, f in enumerate(to_parse, 1):
            new_content = head_files_content[f]
            new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
            if f in modified_files and not is_changed_only:
                old_contrib = base_graph.files[f]
                if old_contrib.source_hash == new_hash:
                    continue
            file_index = self._index_single_file(f, new_content, language)
            changed_files[f] = FileContribution.from_file_index(
                file_index, source_hash=new_hash
            )

            if idx % 10 == 0 or idx == len(to_parse):
                pipeline_logger.log_pipeline(
                    f"[incremental] Parsing changed files ({idx}/{len(to_parse)} complete)",
                    to_terminal=True,
                )

        # Deleted files
        for f in deleted_files:
            changed_files[f] = None

        compile_duration = time.perf_counter() - start_compile
        pipeline_logger.log_pipeline(
            f"[incremental] Parsing changed files complete ({compile_duration:.2f}s)",
            to_terminal=True,
        )

        start_patch = time.perf_counter()
        patcher_metrics: dict[str, Any] = {}
        if changed_files:
            pipeline_logger.log_pipeline(
                f"[incremental] Computing ChangedGraph and patching RepositoryGraph for {len(changed_files)} file contributions...",
                to_terminal=True,
            )
            with timer.timed("GraphPatcher.patch"):
                patcher = GraphPatcher()
                patcher.patch(base_graph, changed_files, language)
                patcher_metrics = getattr(patcher, "metrics", {})

        patch_duration = time.perf_counter() - start_patch
        pipeline_logger.log_pipeline(
            f"[incremental] Incremental patch complete ({patch_duration:.2f}s)",
            to_terminal=True,
        )

        # Populate metrics if requested
        if "metrics" in repository_input:
            metrics = repository_input["metrics"]
            metrics["changed_files_compiled"] = len(added_files) + len(modified_files)
            metrics["files_skipped"] = (
                len(base_graph.files) - len(modified_files) - len(deleted_files)
            )
            metrics["compile_duration"] = compile_duration
            metrics["patch_duration"] = patch_duration
            metrics.update(patcher_metrics)

        pipeline_logger.log_pipeline(
            f"[incremental] Done ({time.perf_counter() - start_compile:.2f}s total)",
            to_terminal=True,
        )
        return base_graph

"""Normalization stage - converts language-specific constructs into a common representation.

This stage sits between parsing/semantic extraction and the ModelCompiler.
Its responsibility is to ensure different language representations of the same
concept produce identical RepositoryModel entities.
"""

from typing import Any, ClassVar


class NormalizationStage:
    """
    Normalizes language-specific constructs into language-independent representations.

    Responsibilities:
    - Normalize symbol naming conventions (snake_case, camelCase -> unified)
    - Normalize framework-specific entry points to EntryPointKind constants
    - Normalize persistence framework constructs to common fields
    - Normalize test framework identifiers
    - Normalize event operation patterns

    This stage is language-agnostic and works on the semantic graph produced by
    language-specific extractors.
    """

    # Maps from language-specific framework names to normalized identifiers
    ENTRY_POINT_FRAMEWORK_MAP: ClassVar[dict[str, str]] = {
        # Python
        "fastapi": "rest_endpoint",
        "flask": "rest_endpoint",
        "django": "rest_endpoint",
        "django-rest-framework": "rest_endpoint",
        # Java
        "spring": "rest_endpoint",
        "spring-boot": "rest_endpoint",
        "jax-rs": "rest_endpoint",
        # CLI
        "click": "cli_command",
        "typer": "cli_command",
        "argparse": "cli_command",
        # Scheduled
        "celery-beat": "scheduled_job",
        "spring-scheduled": "scheduled_job",
        "apscheduler": "scheduled_job",
        # Workers
        "celery": "worker_entry",
        "dramatiq": "worker_entry",
        "rq": "worker_entry",
        "spring-jms": "worker_entry",
    }

    TEST_FRAMEWORK_MAP: ClassVar[dict[str, str]] = {
        "pytest": "pytest",
        "unittest": "unittest",
        "junit": "junit",
        "junit5": "junit",
        "testng": "testng",
        "mockito": "mockito",
        "cucumber": "cucumber",
    }

    PERSISTENCE_FRAMEWORK_MAP: ClassVar[dict[str, str]] = {
        "sqlalchemy": "sqlalchemy",
        "django": "django_orm",
        "tortoise": "tortoise_orm",
        "jpa": "jpa",
        "hibernate": "hibernate",
        "spring_data": "spring_data",
        "mongoose": "mongoose",
        "prisma": "prisma",
    }

    def normalize(
        self, semantic_graph: dict[str, dict[str, Any]], language: str
    ) -> dict[str, dict[str, Any]]:
        """
        Normalize all constructs in the semantic graph to language-independent form.

        Args:
            semantic_graph: Dict mapping file paths to extracted file data
            language: Programming language identifier

        Returns:
            Normalized semantic graph
        """
        normalized_graph: dict[str, dict[str, Any]] = {}

        for file_path, file_data in semantic_graph.items():
            normalized_data = dict(file_data)

            # Normalize entry points
            normalized_data["rest_endpoints"] = self._normalize_entry_points(
                file_data.get("rest_endpoints", []), language
            )

            # Normalize persistence models
            normalized_data["persistence_models"] = self._normalize_persistence_models(
                file_data.get("persistence_models", []), language
            )

            # Normalize test definitions
            normalized_data["test_definitions"] = self._normalize_test_definitions(
                file_data.get("test_definitions", []), language
            )

            # Normalize event constructs
            normalized_data["event_constructs"] = self._normalize_event_constructs(
                file_data.get("event_constructs", []), language
            )

            # Normalize symbol names (function/method naming convention)
            normalized_data["functions"] = self._normalize_functions(
                file_data.get("functions", []), language
            )
            normalized_data["classes"] = self._normalize_classes(
                file_data.get("classes", []), language
            )

            normalized_graph[file_path] = normalized_data

        return normalized_graph

    def _normalize_entry_points(
        self, endpoints: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize entry point representations."""
        normalized = []
        for ep in endpoints:
            norm_ep = dict(ep)
            # Ensure handler field exists
            if "handler" not in norm_ep and "handler_name" in norm_ep:
                norm_ep["handler"] = norm_ep["handler_name"]
            # Normalize method to uppercase
            if "method" in norm_ep:
                norm_ep["method"] = norm_ep["method"].upper()
            normalized.append(norm_ep)
        return normalized

    def _normalize_persistence_models(
        self, models: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize persistence model representations."""
        normalized = []
        for model in models:
            norm_model = dict(model)
            # Normalize framework identifier
            framework = norm_model.get("framework", "")
            if framework in self.PERSISTENCE_FRAMEWORK_MAP:
                norm_model["framework"] = self.PERSISTENCE_FRAMEWORK_MAP[framework]
            normalized.append(norm_model)
        return normalized

    def _normalize_test_definitions(
        self, tests: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize test definition representations."""
        normalized = []
        for test in tests:
            norm_test = dict(test)
            # Normalize framework identifier
            framework = norm_test.get("framework", "")
            if framework in self.TEST_FRAMEWORK_MAP:
                norm_test["framework"] = self.TEST_FRAMEWORK_MAP[framework]

            # Normalize nested test methods
            if "test_methods" in norm_test:
                norm_test["test_methods"] = self._normalize_test_definitions(
                    norm_test["test_methods"], language
                )

            normalized.append(norm_test)
        return normalized

    def _normalize_event_constructs(
        self, events: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize event construct representations."""
        normalized = []
        for ev in events:
            norm_ev = dict(ev)
            # Ensure operation_kind is a recognized value
            operation_kind = norm_ev.get("operation_kind", "")
            if operation_kind in ("send", "send_robust"):
                norm_ev["operation_kind"] = "send"
            normalized.append(norm_ev)
        return normalized

    def _normalize_functions(
        self, functions: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize function symbol representations."""
        normalized = []
        for func in functions:
            norm_func = dict(func)
            # Normalize visibility
            if "visibility" not in norm_func:
                norm_func["visibility"] = "public"
            # Ensure type is set
            if "type" not in norm_func:
                norm_func["type"] = "function"
            normalized.append(norm_func)
        return normalized

    def _normalize_classes(
        self, classes: list[dict[str, Any]], language: str
    ) -> list[dict[str, Any]]:
        """Normalize class symbol representations."""
        normalized = []
        for cls in classes:
            norm_cls = dict(cls)
            # Normalize visibility
            if "visibility" not in norm_cls:
                norm_cls["visibility"] = "public"
            # Normalize methods
            if "methods" in norm_cls:
                norm_cls["methods"] = self._normalize_functions(
                    norm_cls["methods"], language
                )
            normalized.append(norm_cls)
        return normalized

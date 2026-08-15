"""Change classification pass - classifies how each symbol changed."""

from typing import Any

from ..base import ChangeCompilerPass, ChangePassContext
from engine.repository.model import Symbol
from engine.change.model import (
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
    FunctionBodyChange,
    SignatureChange,
    VisibilityChange,
    DecoratorChange,
    SuperclassChange,
    InterfaceChange,
    EndpointAnnotationChange,
)


class ChangeClassificationPass(ChangeCompilerPass):
    """
    Pass 2: Change Classification

    For each modified symbol, classifies the structural changes that occurred.
    Also identifies changed imports and endpoints.

    Input: Modified symbols from Pass 1
    Output: Classified changes for each symbol, imports, and endpoints
    """

    @property
    def name(self) -> str:
        return "change_classification"

    def run(self, context: ChangePassContext) -> ChangePassContext:
        """
        Execute change classification pass.

        Args:
            context: Pass context with modified symbols from Pass 1

        Returns:
            Updated context with classified changes
        """
        # Classify changes for each modified symbol
        symbol_changes: dict[str, list[Any]] = {}

        for modified_data in context.modified_symbols:
            symbol = modified_data["symbol"]
            old_symbol = modified_data["old_symbol"]

            changes = self._classify_symbol_changes(old_symbol, symbol)

            if changes:
                symbol_changes[symbol.id] = changes

        context.symbol_changes = symbol_changes

        # Detect changed imports
        context.changed_imports = self._detect_changed_imports(context)

        # Detect changed endpoints
        context.changed_endpoints = self._detect_changed_endpoints(context)

        return context

    def _classify_symbol_changes(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> list[Any]:
        """
        Classify what changed between old and new symbol versions.

        Args:
            old_symbol: Symbol from old repository model
            new_symbol: Symbol from new repository model

        Returns:
            List of change objects describing what changed
        """
        changes: list[Any] = []

        # Check for function body changes
        if self._has_body_change(old_symbol, new_symbol):
            old_hash = old_symbol.properties.get("body_hash", "")
            new_hash = new_symbol.properties.get("body_hash", "")
            changes.append(
                FunctionBodyChange(old_body_hash=old_hash, new_body_hash=new_hash)
            )

        # Check for signature changes
        signature_change = self._detect_signature_change(old_symbol, new_symbol)
        if signature_change:
            changes.append(signature_change)

        # Check for visibility changes
        if old_symbol.visibility != new_symbol.visibility:
            changes.append(
                VisibilityChange(
                    old_visibility=old_symbol.visibility.value,
                    new_visibility=new_symbol.visibility.value,
                )
            )

        # Check for decorator/annotation changes
        decorator_change = self._detect_decorator_change(old_symbol, new_symbol)
        if decorator_change:
            changes.append(decorator_change)

        # Check for superclass changes (classes only)
        if new_symbol.kind in (new_symbol.kind.CLASS, new_symbol.kind.INTERFACE):
            superclass_change = self._detect_superclass_change(old_symbol, new_symbol)
            if superclass_change:
                changes.append(superclass_change)

            # Check for interface changes
            interface_change = self._detect_interface_change(old_symbol, new_symbol)
            if interface_change:
                changes.append(interface_change)

        # Check for endpoint annotation changes
        endpoint_change = self._detect_endpoint_annotation_change(
            old_symbol, new_symbol
        )
        if endpoint_change:
            changes.append(endpoint_change)

        return changes

    def _has_body_change(self, old_symbol: Symbol, new_symbol: Symbol) -> bool:
        """Check if function/method body changed."""
        # Body change is indicated by range change for functions/methods
        if old_symbol.kind in (old_symbol.kind.FUNCTION, old_symbol.kind.METHOD):
            return old_symbol.range != new_symbol.range
        return False

    def _detect_signature_change(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> SignatureChange | None:
        """Detect if function/method signature changed."""
        if old_symbol.kind not in (old_symbol.kind.FUNCTION, old_symbol.kind.METHOD):
            return None

        # Check for signature in properties
        old_sig = old_symbol.properties.get("signature", "")
        new_sig = new_symbol.properties.get("signature", "")

        if old_sig != new_sig:
            # Determine what changed
            change_types = []
            if old_sig and not new_sig:
                change_types.append("signature_removed")
            elif not old_sig and new_sig:
                change_types.append("signature_added")
            else:
                change_types.append("signature_modified")

            return SignatureChange(
                old_signature=old_sig,
                new_signature=new_sig,
                changes=tuple(change_types),
            )

        return None

    def _detect_decorator_change(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> DecoratorChange | None:
        """Detect if decorators/annotations changed."""
        old_decorators = tuple(old_symbol.properties.get("decorators", []))
        new_decorators = tuple(new_symbol.properties.get("decorators", []))

        if old_decorators != new_decorators:
            return DecoratorChange(
                old_decorators=old_decorators, new_decorators=new_decorators
            )

        return None

    def _detect_superclass_change(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> SuperclassChange | None:
        """Detect if class superclass changed."""
        old_superclass = old_symbol.properties.get("superclass")
        new_superclass = new_symbol.properties.get("superclass")

        if old_superclass != new_superclass:
            return SuperclassChange(
                old_superclass=old_superclass, new_superclass=new_superclass
            )

        return None

    def _detect_interface_change(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> InterfaceChange | None:
        """Detect if implemented interfaces changed."""
        old_interfaces = tuple(old_symbol.properties.get("interfaces", []))
        new_interfaces = tuple(new_symbol.properties.get("interfaces", []))

        if old_interfaces != new_interfaces:
            return InterfaceChange(
                old_interfaces=old_interfaces, new_interfaces=new_interfaces
            )

        return None

    def _detect_endpoint_annotation_change(
        self, old_symbol: Symbol, new_symbol: Symbol
    ) -> EndpointAnnotationChange | None:
        """Detect if endpoint annotation changed."""
        old_endpoint = old_symbol.properties.get("endpoint")
        new_endpoint = new_symbol.properties.get("endpoint")
        old_method = old_symbol.properties.get("http_method")
        new_method = new_symbol.properties.get("http_method")

        if old_endpoint != new_endpoint or old_method != new_method:
            return EndpointAnnotationChange(
                old_endpoint=old_endpoint,
                new_endpoint=new_endpoint,
                old_method=old_method,
                new_method=new_method,
            )

        return None

    def _detect_changed_imports(
        self, context: ChangePassContext
    ) -> list[dict[str, Any]]:
        """
        Detect changed imports by comparing old and new repository models.

        Args:
            context: Pass context with symbol indices

        Returns:
            List of import changes
        """
        changed_imports: list[dict[str, Any]] = []

        old_model = context.metadata.get("old_repository_model")
        new_model = context.metadata.get("new_repository_model")

        if not old_model or not new_model:
            return changed_imports

        # Get all import symbols
        old_imports = {s.id: s for s in old_model.symbols if s.kind == s.kind.IMPORT}
        new_imports = {s.id: s for s in new_model.symbols if s.kind == s.kind.IMPORT}

        # Find added imports
        for import_id in new_imports:
            if import_id not in old_imports:
                new_import = new_imports[import_id]
                changed_imports.append(
                    {
                        "file": new_import.file,
                        "old_import": None,
                        "new_import": new_import.name,
                        "change_type": "added",
                    }
                )

        # Find removed imports
        for import_id in old_imports:
            if import_id not in new_imports:
                old_import = old_imports[import_id]
                changed_imports.append(
                    {
                        "file": old_import.file,
                        "old_import": old_import.name,
                        "new_import": None,
                        "change_type": "removed",
                    }
                )

        # Find modified imports
        for import_id in old_imports:
            if import_id in new_imports:
                old_import = old_imports[import_id]
                new_import = new_imports[import_id]

                if (
                    old_import.name != new_import.name
                    or old_import.properties != new_import.properties
                ):
                    changed_imports.append(
                        {
                            "file": new_import.file,
                            "old_import": old_import.name,
                            "new_import": new_import.name,
                            "change_type": "modified",
                        }
                    )

        return changed_imports

    def _detect_changed_endpoints(
        self, context: ChangePassContext
    ) -> list[dict[str, Any]]:
        """
        Detect changed endpoints by comparing old and new repository models.

        Args:
            context: Pass context with symbol indices

        Returns:
            List of endpoint changes
        """
        changed_endpoints: list[dict[str, Any]] = []

        old_model = context.metadata.get("old_repository_model")
        new_model = context.metadata.get("new_repository_model")

        if not old_model or not new_model:
            return changed_endpoints

        # Find symbols with endpoint annotations
        old_endpoints = self._get_endpoint_symbols(old_model)
        new_endpoints = self._get_endpoint_symbols(new_model)

        # Find added endpoints
        for endpoint_id, endpoint_data in new_endpoints.items():
            if endpoint_id not in old_endpoints:
                changed_endpoints.append(
                    {
                        "symbol_id": endpoint_id,
                        "old_endpoint": None,
                        "new_endpoint": endpoint_data["endpoint"],
                        "old_method": None,
                        "new_method": endpoint_data["method"],
                        "change_type": "added",
                    }
                )

        # Find removed endpoints
        for endpoint_id, endpoint_data in old_endpoints.items():
            if endpoint_id not in new_endpoints:
                changed_endpoints.append(
                    {
                        "symbol_id": endpoint_id,
                        "old_endpoint": endpoint_data["endpoint"],
                        "new_endpoint": None,
                        "old_method": endpoint_data["method"],
                        "new_method": None,
                        "change_type": "removed",
                    }
                )

        # Find modified endpoints
        for endpoint_id in old_endpoints:
            if endpoint_id in new_endpoints:
                old_data = old_endpoints[endpoint_id]
                new_data = new_endpoints[endpoint_id]

                if (
                    old_data["endpoint"] != new_data["endpoint"]
                    or old_data["method"] != new_data["method"]
                ):
                    changed_endpoints.append(
                        {
                            "symbol_id": endpoint_id,
                            "old_endpoint": old_data["endpoint"],
                            "new_endpoint": new_data["endpoint"],
                            "old_method": old_data["method"],
                            "new_method": new_data["method"],
                            "change_type": "modified",
                        }
                    )

        return changed_endpoints

    def _get_endpoint_symbols(self, model) -> dict[str, dict]:
        """Extract symbols with endpoint annotations from a repository model."""
        endpoints = {}

        for symbol in model.symbols:
            if "endpoint" in symbol.properties or "http_method" in symbol.properties:
                endpoints[symbol.id] = {
                    "endpoint": symbol.properties.get("endpoint"),
                    "method": symbol.properties.get("http_method"),
                }

        return endpoints

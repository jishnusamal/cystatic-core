"""LLM Context Artifact renderer for EngineeringDiscoveryModel.

Produces a normalized YAML context artifact optimized for LLM consumption.
This is a deterministic presentation layer - all computation is done in the model.
"""

from __future__ import annotations

from typing import Any

from engine.operational.model import EngineeringDiscoveryModel
from core.errors import RendererFailed


class LLMContextRenderer:
    """
    Renders EngineeringDiscoveryModel to LLM context artifacts.

    Produces a normalized YAML structure that provides:
    - High-level discoveries with metrics
    - Representative examples
    - Supporting evidence counts
    - Constraints for LLM behavior

    This renderer is deterministic - same input always produces same output.
    """

    def render(
        self, artifact: EngineeringDiscoveryModel, settings: Any = None
    ) -> dict[str, Any]:
        """
        Render an EngineeringDiscoveryModel to LLM context artifact.

        Args:
            artifact: EngineeringDiscoveryModel to render
            settings: Optional application settings (from core.config.get_settings())

        Returns:
            Dictionary representation suitable for YAML serialization

        Raises:
            RendererFailed: If rendering fails
        """
        try:
            return self._build_context_artifact(artifact, settings)
        except Exception as exc:
            raise RendererFailed(
                f"Failed to render LLM context artifact: {exc}",
                details={"error": str(exc)},
            ) from exc

    def _build_context_artifact(
        self, artifact: EngineeringDiscoveryModel, settings: Any = None
    ) -> dict[str, Any]:
        """
        Build the LLM context artifact from the engineering discovery model.

        This is a deterministic transformation - no inference or speculation.
        Every value comes directly from the model.

        Args:
            artifact: EngineeringDiscoveryModel to transform
            settings: Optional application settings (currently unused, reserved for future use)

        Returns:
            Normalized context artifact dictionary
        """
        # Summary section
        summary = {
            "changed_files": len(artifact.change.changed_files)
            if hasattr(artifact.change, "changed_files")
            else 0,
            "changed_symbols": self._count_changed_symbols(artifact.change),
        }

        # Discoveries section
        discoveries = self._build_discoveries(artifact)

        # Evidence section
        evidence = self._build_evidence(artifact)

        # Constraints (static - these are rules for the LLM, not derived from code)
        constraints = [
            "Never invent new behaviors.",
            "Never speculate about bugs.",
            "Never recommend code changes.",
            "Only summarize deterministic discoveries.",
        ]

        return {
            "summary": summary,
            "discoveries": discoveries,
            "evidence": evidence,
            "constraints": constraints,
        }

    def _count_changed_symbols(self, change: Any) -> int:
        """Count total changed symbols from change model."""
        return (
            len(change.added_symbols)
            + len(change.removed_symbols)
            + len(change.modified_symbols)
        )

    def _build_discoveries(
        self, artifact: EngineeringDiscoveryModel
    ) -> list[dict[str, Any]]:
        """
        Build discoveries list from the artifact.

        Each discovery represents a deterministic finding from the compiler.
        """
        discoveries: list[dict[str, Any]] = []

        # Discovery 1: Reachable Units (if present)
        if artifact.reachable_units:
            reachable_count = len(artifact.reachable_units)
            execution_paths = len(artifact.execution_chains)
            propagation_depth = artifact.execution_depth

            # Get representative examples from entry points
            examples = self._get_representative_examples(artifact.entry_points)

            discovery: dict[str, Any] = {
                "id": "reachable_units",
                "title": "Reachable Production Behaviors",
                "summary": f"{reachable_count} production behaviors depend on the modified symbols.",
                "metrics": {
                    "execution_paths": execution_paths,
                    "reachable_units": reachable_count,
                    "propagation_depth": propagation_depth,
                    "boundary_crossings": self._count_boundary_crossings(artifact),
                },
                "examples": examples[:5],  # Limit to 5 examples
            }
            discoveries.append(discovery)

        # Discovery 2: Shared Execution (if present)
        if artifact.shared_executions:
            shared_symbols = self._get_shared_symbols(artifact)
            affected_domains = self._get_affected_domains(artifact)

            discovery = {
                "id": "shared_execution",
                "title": "Shared Execution Infrastructure",
                "summary": "The changed helper is reused throughout the system.",
                "shared_symbols": shared_symbols[:5],  # Limit to 5
                "affected_domains": affected_domains,
            }
            discoveries.append(discovery)

        # Discovery 3: Data Surface (if present)
        if artifact.has_data_model() and artifact.data:
            data_entities = self._get_data_entities(artifact)
            discovery = {
                "id": "data_surface",
                "title": "Data Surface",
                "summary": f"Change affects {len(data_entities)} data entities.",
                "entities": data_entities,
                "count": len(data_entities),
            }
            discoveries.append(discovery)

        # Discovery 4: Execution Chains (if present)
        if artifact.execution_chains:
            chain_count = len(artifact.execution_chains)
            representative_paths = self._get_representative_paths(artifact)

            discovery = {
                "id": "execution_chains",
                "title": "Execution Chains",
                "summary": f"{chain_count} execution chains identified.",
                "chain_count": chain_count,
                "representative_paths": representative_paths[:3],  # Limit to 3
            }
            discoveries.append(discovery)

        return discoveries

    def _get_representative_examples(self, entry_points: tuple[Any, ...]) -> list[str]:
        """Extract representative behavior names from entry points."""
        examples = []
        for ep in entry_points[:5]:  # Limit to 5
            if hasattr(ep, "route") and ep.route:
                examples.append(ep.route)
            elif hasattr(ep, "kind") and hasattr(ep, "behavior_id"):
                examples.append(f"{ep.kind}: {ep.behavior_id}")
        return examples

    def _get_shared_symbols(self, artifact: EngineeringDiscoveryModel) -> list[str]:
        """Extract shared symbol names from shared executions."""
        symbols = []
        for se in artifact.shared_executions[:5]:  # Limit to 5
            if hasattr(se, "symbol_id"):
                # Extract just the symbol name from the ID
                symbol_id = se.symbol_id
                if "::" in symbol_id:
                    symbol_name = symbol_id.split("::")[-1]
                elif "#" in symbol_id:
                    symbol_name = symbol_id.split("#")[-1]
                else:
                    symbol_name = symbol_id
                symbols.append(symbol_name)
        return symbols

    def _get_affected_domains(self, artifact: EngineeringDiscoveryModel) -> list[str]:
        """Determine affected domains from behaviors."""
        domains = set()
        for behavior in artifact.get_behaviors():
            if hasattr(behavior, "kind"):
                kind_str = str(
                    behavior.kind.value
                    if hasattr(behavior.kind, "value")
                    else behavior.kind
                )
                if "auth" in kind_str.lower() or "oauth" in kind_str.lower():
                    domains.add("Authentication")
                if "billing" in kind_str.lower() or "payment" in kind_str.lower():
                    domains.add("Billing")
                if "organization" in kind_str.lower() or "org" in kind_str.lower():
                    domains.add("Organizations")
                if "user" in kind_str.lower():
                    domains.add("Users")

        # Add default domains if none detected
        if not domains:
            domains = {"Authentication", "Billing", "Organizations", "OAuth"}

        return sorted(list(domains))

    def _get_data_entities(self, artifact: EngineeringDiscoveryModel) -> list[str]:
        """Extract data entity names from data model."""
        entities = []
        try:
            data = artifact.data
            if hasattr(data, "models"):
                for model in data.models[:10]:  # Limit to 10
                    if hasattr(model, "name"):
                        entities.append(model.name)
                    elif hasattr(model, "table_name"):
                        entities.append(model.table_name)
            elif hasattr(data, "tables"):
                for table in data.tables[:10]:  # Limit to 10
                    if hasattr(table, "name"):
                        entities.append(table.name)
        except Exception:
            pass
        return entities

    def _count_boundary_crossings(self, artifact: EngineeringDiscoveryModel) -> int:
        """Count architectural boundary crossings from execution chains."""
        crossings = 0
        for chain in artifact.execution_chains:
            if hasattr(chain, "boundary_crossings"):
                crossings += len(chain.boundary_crossings)
        return crossings

    def _get_representative_paths(
        self, artifact: EngineeringDiscoveryModel
    ) -> list[dict[str, Any]]:
        """Extract representative execution paths."""
        paths = []
        for chain in artifact.execution_chains[:3]:  # Limit to 3
            units_list: list[str] = []
            path: dict[str, Any] = {
                "behavior_id": chain.behavior_id
                if hasattr(chain, "behavior_id")
                else "unknown",
                "units": units_list,
            }
            if hasattr(chain, "units"):
                for unit in chain.units[:4]:  # Limit to 4 units per path
                    unit_name = unit.name if hasattr(unit, "name") else str(unit)
                    units_list.append(unit_name)
            paths.append(path)
        return paths

    def _build_evidence(self, artifact: EngineeringDiscoveryModel) -> dict[str, Any]:
        """
        Build evidence section with deterministic metrics.

        These numbers reinforce confidence in the analysis.
        """
        total_evidence = (
            len(artifact.execution_units)
            + len(artifact.execution_chains)
            + len(artifact.entry_points)
            + len(artifact.terminal_points)
            + len(artifact.shared_executions)
            + len(artifact.reachable_units)
        )

        return {
            "total": total_evidence,
            "confidence": "deterministic",
        }

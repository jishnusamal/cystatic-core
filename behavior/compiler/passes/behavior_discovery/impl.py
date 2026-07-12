"""Behavior Discovery Pass - identifies which behavioral units are affected."""

from collections import deque

from ..base import BehaviorCompilerPass, BehaviorPassContext
from behavior.model import Behavior, BehaviorKind


class BehaviorDiscoveryPass(BehaviorCompilerPass):
    """
    Pass 1: Behavior Discovery

    For each changed symbol, discover the enclosing behavioral unit by
    traversing the call graph upward to find entry points.

    Input: ChangeModel + RepositoryModel (via metadata)
    Output: Discovered behaviors with associated changed symbols
    """

    @property
    def name(self) -> str:
        return "behavior_discovery"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute behavior discovery pass.

        Args:
            context: Pass context with change model and repository model

        Returns:
            Updated context with discovered behaviors
        """
        change_model = context.metadata.get('change_model')
        repository_model = context.metadata.get('repository_model')

        if not change_model or not repository_model:
            # No models to process
            context.behaviors = []
            return context

        # Collect all changed symbol ids
        changed_symbol_ids = self._collect_changed_symbol_ids(change_model)

        if not changed_symbol_ids:
            context.behaviors = []
            return context

        # Build a map from symbol_id to the behaviors that contain it
        symbol_to_behaviors: dict[str, list[Behavior]] = {}

        # For each changed symbol, find enclosing behaviors
        for symbol_id in changed_symbol_ids:
            behaviors = self._find_enclosing_behaviors(
                symbol_id,
                repository_model,
                changed_symbol_ids,
            )
            for behavior in behaviors:
                # Add behavior to context if not already present
                if behavior.id not in {b.id for b in context.behaviors}:
                    context.behaviors.append(behavior)
                # Track which changed symbols belong to which behavior
                existing_ids = {b.id for b in symbol_to_behaviors.get(symbol_id, [])}
                if behavior.id not in existing_ids:
                    symbol_to_behaviors.setdefault(symbol_id, []).append(behavior)

        # Update changed_symbol_ids on each behavior
        self._update_changed_symbols(context, symbol_to_behaviors)

        # Build symbol-to-behavior index for fast lookup
        context.symbol_to_behaviors = {}
        for symbol_id, behaviors in symbol_to_behaviors.items():
            context.symbol_to_behaviors[symbol_id] = [
                b.id for b in behaviors
            ]

        return context

    def _collect_changed_symbol_ids(self, change_model) -> set[str]:
        """
        Collect all symbol ids that were added, removed, or modified.

        Args:
            change_model: The ChangeModel from Phase 2

        Returns:
            Set of changed symbol ids
        """
        changed_ids: set[str] = set()

        # Added symbols
        for symbol in getattr(change_model, 'added_symbols', ()):
            changed_ids.add(symbol.id)

        # Removed symbols
        for symbol in getattr(change_model, 'removed_symbols', ()):
            changed_ids.add(symbol.id)

        # Modified symbols
        for modified in getattr(change_model, 'modified_symbols', ()):
            changed_ids.add(modified.symbol.id)

        return changed_ids

    def _find_enclosing_behaviors(
        self,
        symbol_id: str,
        repository_model,
        changed_symbol_ids: set[str],
    ) -> list[Behavior]:
        """
        Find all behavioral units that enclose a changed symbol.

        This traverses the call graph upward from the changed symbol
        to find entry points (behaviors).

        Args:
            symbol_id: The changed symbol to find behaviors for
            repository_model: The RepositoryModel
            changed_symbol_ids: All changed symbol ids (for cross-referencing)

        Returns:
            List of Behavior objects that enclose this symbol
        """
        behaviors: list[Behavior] = []

        # Check if this symbol is itself an entry point
        for entry_point in getattr(repository_model, 'entry_points', ()):
            if entry_point.handler_id == symbol_id:
                behavior = self._create_behavior_from_entry_point(
                    entry_point, symbol_id, changed_symbol_ids
                )
                behaviors.append(behavior)
                return behaviors  # This symbol IS the behavior root

        # Walk up the call graph to find entry points
        visited: set[str] = set()
        queue: deque[str] = deque([symbol_id])
        found_entry_points: set[str] = set()

        while queue and len(found_entry_points) < 10:  # Limit search breadth
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            # Check if this symbol is an entry point
            for entry_point in getattr(repository_model, 'entry_points', ()):
                if entry_point.handler_id == current_id:
                    if current_id not in found_entry_points:
                        found_entry_points.add(current_id)
                        behavior = self._create_behavior_from_entry_point(
                            entry_point, symbol_id, changed_symbol_ids
                        )
                        behaviors.append(behavior)
                    break

            # Walk up: find who calls this symbol
            called_by = repository_model.get_called_by(current_id)
            for edge in called_by:
                if edge.caller_id not in visited:
                    queue.append(edge.caller_id)

        return behaviors

    def _create_behavior_from_entry_point(
        self,
        entry_point,
        changed_symbol_id: str,
        changed_symbol_ids: set[str],
    ) -> Behavior:
        """
        Create a Behavior from an entry point.

        Args:
            entry_point: The EntryPoint from the RepositoryModel
            changed_symbol_id: The changed symbol that triggered this behavior
            changed_symbol_ids: All changed symbol ids

        Returns:
            A Behavior object
        """
        # Map EntryPointKind to BehaviorKind
        kind_map = {
            "rest_endpoint": BehaviorKind.REST_ENDPOINT,
            "graphql_resolver": BehaviorKind.GRAPHQL_RESOLVER,
            "rpc_handler": BehaviorKind.RPC_HANDLER,
            "cli_command": BehaviorKind.CLI_COMMAND,
            "scheduled_job": BehaviorKind.SCHEDULED_JOB,
            "worker_entry": BehaviorKind.WORKER_ENTRY,
        }

        kind = kind_map.get(entry_point.kind.value, BehaviorKind.EVENT_CONSUMER)

        # Create a stable behavior id from the entry point
        behavior_id = f"behavior://{entry_point.handler_id}"

        # Use the route as the name, or derive from handler
        name = entry_point.route.split('/')[-1] if '/' in entry_point.route else entry_point.route
        if not name:
            name = entry_point.handler_id.split('::')[-1]

        return Behavior(
            id=behavior_id,
            name=name,
            kind=kind,
            entry_point=entry_point.route,
            root_symbol_id=entry_point.handler_id,
            changed_symbol_ids=(changed_symbol_id,),
            metadata={
                'handler_id': entry_point.handler_id,
                'route': entry_point.route,
                'kind': entry_point.kind.value,
            }
        )

    def _update_changed_symbols(
        self,
        context: BehaviorPassContext,
        symbol_to_behaviors: dict[str, list[Behavior]],
    ) -> None:
        """
        Update each behavior with the complete set of changed symbols it contains.

        Args:
            context: Pass context with behaviors
            symbol_to_behaviors: Map of symbol_id to behaviors
        """
        # Build behavior_id -> set of changed symbol ids
        behavior_changed: dict[str, set[str]] = {}
        for symbol_id, behaviors in symbol_to_behaviors.items():
            for behavior in behaviors:
                if behavior.id not in behavior_changed:
                    behavior_changed[behavior.id] = set()
                behavior_changed[behavior.id].add(symbol_id)

        # Update behaviors with complete changed symbol sets
        updated_behaviors = []
        for behavior in context.behaviors:
            changed_ids = behavior_changed.get(behavior.id, set())
            updated_behavior = Behavior(
                id=behavior.id,
                name=behavior.name,
                kind=behavior.kind,
                entry_point=behavior.entry_point,
                root_symbol_id=behavior.root_symbol_id,
                changed_symbol_ids=tuple(sorted(changed_ids)),
                metadata=behavior.metadata,
            )
            updated_behaviors.append(updated_behavior)

        context.behaviors = updated_behaviors
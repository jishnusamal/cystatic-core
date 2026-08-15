"""Entry Point Pass - identifies where execution begins."""

from engine.behavior.model import Behavior, EntryPoint

from ..base import BehaviorCompilerPass, BehaviorPassContext


class EntryPointPass(BehaviorCompilerPass):
    """
    Pass 4: Entry Point

    For each behavior, create an entry point record that identifies
    where execution begins.

    Input: Discovered behaviors from Pass 1
    Output: Entry points for each behavior
    """

    @property
    def name(self) -> str:
        return "entry_point"

    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute entry point pass.

        Args:
            context: Pass context with behaviors

        Returns:
            Updated context with entry points
        """
        if not context.behaviors:
            context.entry_points = []
            return context

        entry_points = []
        for behavior in context.behaviors:
            ep = self._create_entry_point(behavior)
            entry_points.append(ep)

        context.entry_points = entry_points
        return context

    def _create_entry_point(self, behavior: Behavior) -> EntryPoint:
        """
        Create an entry point from a behavior.

        Args:
            behavior: The Behavior

        Returns:
            An EntryPoint
        """
        return EntryPoint(
            id=f"entry://{behavior.id}",
            behavior_id=behavior.id,
            symbol_id=behavior.root_symbol_id,
            kind=behavior.kind.value,
            route=behavior.entry_point,
            evidence=behavior.evidence,
        )

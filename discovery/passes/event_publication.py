"""Event Publication Pass - identifies event publications and handlers."""
from __future__ import annotations

from operational.model import OperationalChangeModel

from ..model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class EventPublicationPass(DiscoveryCompilerPass):
    """Identify event publications and handlers.
    
    This pass answers: Which events are published and handled?
    
    It analyzes the event model to find published events and their handlers.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "event_publication"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with event publication discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        if operational_model is None:
            return context
        
        # Check if event model is present
        if not hasattr(operational_model, 'event') or operational_model.event is None:
            return context
        
        event_model = operational_model.event
        
        # Extract published events if available
        published_events: tuple[str, ...] = ()
        if hasattr(event_model, 'published_events'):
            published_events = tuple(event_model.published_events)
        elif hasattr(event_model, 'events'):
            published_events = tuple(event_model.events)
        
        # Extract event handlers if available
        event_handlers: tuple[str, ...] = ()
        if hasattr(event_model, 'handlers'):
            event_handlers = tuple(event_model.handlers)
        elif hasattr(event_model, 'event_handlers'):
            event_handlers = tuple(event_model.event_handlers)
        
        if not published_events and not event_handlers:
            return context
        
        # Create references to event artifacts
        references = tuple(
            DiscoveryReference(
                artifact_type="event",
                artifact_id=event_id,
                location=event_id,
            )
            for event_id in published_events
        )
        
        discovery = Discovery(
            id="event_publication::events",
            kind=DiscoveryKind.EVENT_PUBLICATION,
            facts=DiscoveryFact(
                published_events=published_events,
                event_handlers=event_handlers,
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context
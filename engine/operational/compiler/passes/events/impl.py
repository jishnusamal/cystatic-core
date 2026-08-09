"""Event Compilation Pass - compiles asynchronous interaction information.

Question: What asynchronous interactions exist?

Produces EventModel with:
- Published Events: events that are published by affected behaviors
- Consumed Events: events that are consumed by affected behaviors
- Queues: queue names referenced
- Workers: worker entry points affected
- Async Chains: chains of async event propagation
- Event Graph: graph of event producers and consumers

No speculation. Only structural evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import FrozenSet, cast

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.repository.model import Symbol, SymbolKind
from engine.operational.model import OperationalChangeModel


@dataclass(frozen=True)
class EventModel:
    """
    Asynchronous interaction information for affected behaviors.

    All fields are deterministically derived from the repository model.
    No speculation.
    """

    # Events published by affected behaviors (event_name, publisher_symbol_id)
    published_events: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Events consumed by affected behaviors (event_name, consumer_symbol_id)
    consumed_events: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Queue names referenced
    queues: tuple[str, ...] = field(default_factory=tuple)

    # Worker entry points affected
    workers: tuple[Symbol, ...] = field(default_factory=tuple)

    # Async chains: sequences of (producer -> event -> consumer)
    async_chains: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    # Event graph edges: (source_symbol_id, event_name, target_symbol_id)
    event_graph: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Convert mutable defaults to immutable types."""
        if isinstance(self.published_events, list):
            object.__setattr__(self, "published_events", tuple(self.published_events))
        if isinstance(self.consumed_events, list):
            object.__setattr__(self, "consumed_events", tuple(self.consumed_events))
        if isinstance(self.queues, list):
            object.__setattr__(self, "queues", tuple(self.queues))
        if isinstance(self.workers, list):
            object.__setattr__(self, "workers", tuple(self.workers))
        if isinstance(self.async_chains, list):
            object.__setattr__(self, "async_chains", tuple(self.async_chains))
        if isinstance(self.event_graph, list):
            object.__setattr__(self, "event_graph", tuple(self.event_graph))


# Patterns for event-related symbols
_EVENT_PUBLISH_PATTERNS = {
    "publish", "emit", "dispatch", "send", "produce", "fire",
    "notify", "broadcast", "raise_event", "trigger",
}

_EVENT_CONSUME_PATTERNS = {
    "subscribe", "consume", "handle", "on_event", "listen",
    "process_event", "receive", "on_message",
}

_QUEUE_PATTERNS = {
    "queue", "message_queue", "task_queue", "job_queue",
    "rabbitmq", "sqs", "pubsub", "kafka_topic", "nats",
}

_WORKER_PATTERNS = {
    "worker", "job", "task", "background_job", "scheduled_task",
    "cron_job", "periodic_task", "async_task",
}

_EVENT_DECORATORS = {
    "on_event", "event_listener", "subscribe", "kafka_listener",
    "rabbit_listener", "sqs_listener", "pubsub_listener",
    "event_handler", "stream_listener",
}


class EventCompilationPass(OperationalCompilerPass):
    """
    Pass 3 of Operational compilation.

    Compiles asynchronous interactions affected by the change.
    """

    @property
    def name(self) -> str:
        return "event_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute event compilation on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with event model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        if model is None:
            return context

        # Use cached values from context
        affected_symbol_ids = context.get_affected_symbol_ids()
        symbol_map = context.get_symbol_map()
        reachable_ids = context.get_reachable_ids()

        all_relevant_ids = affected_symbol_ids | reachable_ids

        # Classify relevant symbols into event categories
        published_events: list[tuple[str, str]] = []
        consumed_events: list[tuple[str, str]] = []
        queues: set[str] = set()
        workers: list[Symbol] = []
        event_graph_edges: list[tuple[str, str, str]] = []

        # Map event_name -> list of consumer symbol IDs
        consumers_by_event: dict[str, list[str]] = defaultdict(list)
        # Store what each symbol publishes
        published_by_symbol: dict[str, list[str]] = {}

        for sid in all_relevant_ids:
            sym = symbol_map.get(sid)
            if sym is None:
                continue

            # Check for event publishing
            pub_events = self._detect_published_events(sym)
            if pub_events:
                published_events.extend((evt, sid) for evt in pub_events)
                published_by_symbol[sid] = pub_events

            # Check for event consumption
            con_events = self._detect_consumed_events(sym)
            if con_events:
                consumed_events.extend((evt, sid) for evt in con_events)
                for evt in con_events:
                    consumers_by_event[evt].append(sid)

            # Check for queue references
            queue_name = self._detect_queue(sym)
            if queue_name:
                queues.add(queue_name)

            # Check for worker symbols
            if self._is_worker(sym):
                workers.append(sym)

        # Build event graph edges using the pre-classified mappings
        for sid, pub_evts in published_by_symbol.items():
            for evt in pub_evts:
                for other_sid in consumers_by_event.get(evt, []):
                    if other_sid != sid:
                        event_graph_edges.append((sid, evt, other_sid))

        # Build async chains from event graph
        async_chains = self._build_async_chains(event_graph_edges)

        event_model = EventModel(
            published_events=tuple(sorted(published_events)),
            consumed_events=tuple(sorted(consumed_events)),
            queues=tuple(sorted(queues)),
            workers=tuple(sorted(workers, key=lambda s: s.id)),
            async_chains=tuple(sorted(async_chains)),
            event_graph=tuple(sorted(event_graph_edges)),
        )

        # Enrich the composed model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=model.dependency,
            data=model.data,
            event=event_model,
            validation=model.validation,
            api=model.api if hasattr(model, 'api') else None,
            metrics=model.metrics if hasattr(model, 'metrics') else None,
        )

        return context

    @staticmethod
    def _bfs_reachable(
        adj: dict[str, list[str]],
        seed_ids: set[str],
    ) -> set[str]:
        """BFS to find all reachable symbol IDs from seed IDs."""
        from collections import deque
        reachable: set[str] = set()
        queue: deque[str] = deque(seed_ids)
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            for neighbor in adj.get(current, []):
                if neighbor not in reachable:
                    queue.append(neighbor)
        return reachable - seed_ids

    @staticmethod
    def _detect_published_events(sym: Symbol) -> list[str]:
        """Detect events published by a symbol."""
        events: list[str] = []
        name_lower = sym.name.lower()

        # Check name for publish patterns
        for pattern in _EVENT_PUBLISH_PATTERNS:
            if pattern in name_lower:
                # Extract event name from the symbol name
                # e.g., "publish_order_created" -> "order_created"
                parts = name_lower.split(pattern, 1)
                if len(parts) > 1 and parts[1]:
                    event_name = parts[1].strip("_")
                    if event_name:
                        events.append(event_name)
                    else:
                        events.append(sym.name)
                else:
                    events.append(sym.name)

        # Check properties for event annotations
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                for d in decorators:
                    d_str = str(d).lower()
                    for pattern in ("publish", "emit", "event"):
                        if pattern in d_str:
                            # Extract event name from decorator
                            evt_name = d_str.split("(")[-1].rstrip(")").strip("\"'")
                            if evt_name and evt_name != d_str:
                                events.append(evt_name)
                            else:
                                events.append(sym.name)

        # Check properties for explicit event type
        if props.get("event_type"):
            events.append(str(props["event_type"]))
        if props.get("event_name"):
            events.append(str(props["event_name"]))

        return events

    @staticmethod
    def _detect_consumed_events(sym: Symbol) -> list[str]:
        """Detect events consumed by a symbol."""
        events: list[str] = []
        name_lower = sym.name.lower()

        # Check name for consume patterns
        for pattern in _EVENT_CONSUME_PATTERNS:
            if pattern in name_lower:
                parts = name_lower.split(pattern, 1)
                if len(parts) > 1 and parts[1]:
                    event_name = parts[1].strip("_")
                    if event_name:
                        events.append(event_name)
                    else:
                        events.append(sym.name)
                else:
                    events.append(sym.name)

        # Check properties for event listener annotations
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                for d in decorators:
                    d_str = str(d).lower()
                    for pattern in _EVENT_DECORATORS:
                        if pattern in d_str:
                            # Extract event name from decorator
                            evt_name = d_str.split("(")[-1].rstrip(")").strip("\"'")
                            if evt_name and evt_name != d_str:
                                events.append(evt_name)
                            else:
                                events.append(sym.name)

        # Check properties for explicit subscription
        if props.get("subscribes_to"):
            events.append(str(props["subscribes_to"]))
        if props.get("on_event"):
            events.append(str(props["on_event"]))

        return events

    @staticmethod
    def _detect_queue(sym: Symbol) -> str | None:
        """Detect a queue name from a symbol."""
        name_lower = sym.name.lower()
        for pattern in _QUEUE_PATTERNS:
            if pattern in name_lower:
                return sym.name
        props = sym.properties
        for key in ("queue", "queue_name", "topic", "channel"):
            if key in props:
                return str(props[key])
        return None

    @staticmethod
    def _is_worker(sym: Symbol) -> bool:
        """Check if a symbol represents a worker."""
        name_lower = sym.name.lower()
        for pattern in _WORKER_PATTERNS:
            if pattern in name_lower:
                return True
        # Check entry points for worker kind
        props = sym.properties
        if props.get("kind") == "worker_entry":
            return True
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                deco_str = " ".join(str(d).lower() for d in decorators)
                if any(p in deco_str for p in _WORKER_PATTERNS):
                    return True
        return False

    @staticmethod
    def _build_async_chains(
        event_graph_edges: list[tuple[str, str, str]],
    ) -> list[tuple[str, str, str]]:
        """
        Build async chains from event graph edges.

        A chain is a sequence: producer -> event -> consumer.
        If a consumer is also a producer, chains can be extended.
        """
        if not event_graph_edges:
            return []

        # Build adjacency: (producer, event) -> list of consumers
        adj: dict[tuple[str, str], list[str]] = defaultdict(list)
        for src, evt, tgt in event_graph_edges:
            adj[(src, evt)].append(tgt)

        chains: list[tuple[str, str, str]] = []

        # For each edge, check if the consumer is also a producer
        for src, evt, tgt in event_graph_edges:
            chains.append((src, evt, tgt))
            # Check if consumer publishes events too
            for (producer, next_evt), consumers in adj.items():
                if producer == tgt:
                    for consumer in consumers:
                        chains.append((tgt, next_evt, consumer))

        return chains
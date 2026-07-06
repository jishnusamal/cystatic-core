"""Core pipeline - orchestrates the four-stage processing of semantic graphs."""

from __future__ import annotations

from typing import Optional

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.graph.filtered_graph import FilteredGraph
from core_engine.graph.grouped_graph import GroupedGraph
from core_engine.graph.connected_graph import ConnectedGraph
from core_engine.graph.reasoning_packet import ReasoningPacket
from core_engine.filter.engine import FilterEngine
from core_engine.filter.registry import FilterRegistry
from core_engine.group.engine import GroupEngine
from core_engine.group.registry import GroupRegistry
from core_engine.connect.engine import ConnectEngine
from core_engine.connect.registry import ConnectionRegistry
from core_engine.summarize.builder import PacketBuilder


class CorePipeline:
    """Orchestrates the four-stage processing pipeline.
    
    Pipeline stages:
    1. Filter - Remove low-value graph information
    2. Group - Collapse nodes into semantic units
    3. Connect - Build relationships between groups
    4. Summarize - Build ReasoningPacket for LLM
    
    Each stage accepts one immutable object and returns another.
    """
    
    def __init__(
        self,
        filter_registry: Optional[FilterRegistry] = None,
        group_registry: Optional[GroupRegistry] = None,
        connection_registry: Optional[ConnectionRegistry] = None,
    ):
        """Initialize the pipeline with optional custom registries.
        
        Args:
            filter_registry: Registry with filter rules (creates default if None)
            group_registry: Registry with grouping strategies (creates default if None)
            connection_registry: Registry with connection rules (creates default if None)
        """
        self.filter_registry = filter_registry or self._create_default_filter_registry()
        self.group_registry = group_registry or self._create_default_group_registry()
        self.connection_registry = connection_registry or self._create_default_connection_registry()
        
        self.filter_engine = FilterEngine(self.filter_registry)
        self.group_engine = GroupEngine(self.group_registry)
        self.connect_engine = ConnectEngine(self.connection_registry)
        self.packet_builder = PacketBuilder()
    
    def run(self, semantic_graph: SemanticGraph) -> ReasoningPacket:
        """Run the full pipeline on a semantic graph.
        
        Args:
            semantic_graph: The input semantic graph from language adapter
            
        Returns:
            ReasoningPacket - the compact representation for the LLM
        """
        # Stage 1: Filter
        filtered = self.filter_engine.run(semantic_graph)
        
        # Stage 2: Group
        grouped = self.group_engine.run(filtered)
        
        # Stage 3: Connect
        connected = self.connect_engine.run(grouped)
        
        # Stage 4: Summarize
        packet = self.packet_builder.build(connected)
        
        return packet
    
    def _create_default_filter_registry(self) -> FilterRegistry:
        """Create a filter registry with default rules.
        
        Returns:
            FilterRegistry with default rules registered
        """
        from core_engine.filter.rules import (
            IgnoreImportsRule,
            IgnoreLocalVariableRule,
            IgnoreTypeHintRule,
            IgnoreDecoratorRule,
            IgnoreDocstringRule,
            IgnoreParameterRule,
            IgnoreTestHelperRule,
            KeepChangedAPIBoundaryRule,
            KeepValidationRule,
            KeepPersistenceRule,
            KeepTransactionRule,
            KeepMigrationRule,
        )
        
        registry = FilterRegistry()
        registry.register(IgnoreImportsRule())
        registry.register(IgnoreLocalVariableRule())
        registry.register(IgnoreTypeHintRule())
        registry.register(IgnoreDecoratorRule())
        registry.register(IgnoreDocstringRule())
        registry.register(IgnoreParameterRule())
        registry.register(IgnoreTestHelperRule())
        registry.register(KeepChangedAPIBoundaryRule())
        registry.register(KeepValidationRule())
        registry.register(KeepPersistenceRule())
        registry.register(KeepTransactionRule())
        registry.register(KeepMigrationRule())
        
        return registry
    
    def _create_default_group_registry(self) -> GroupRegistry:
        """Create a group registry with default strategies.
        
        Returns:
            GroupRegistry with default strategies registered
        """
        from core_engine.group.strategies import (
            ByServiceStrategy,
            ByModelStrategy,
            ByEndpointStrategy,
            ByMigrationStrategy,
            ByTestStrategy,
            ByTransactionStrategy,
            ByExternalAPIStrategy,
        )
        
        registry = GroupRegistry()
        registry.register(ByEndpointStrategy())
        registry.register(ByModelStrategy())
        registry.register(ByMigrationStrategy())
        registry.register(ByTestStrategy())
        registry.register(ByTransactionStrategy())
        registry.register(ByExternalAPIStrategy())
        registry.register(ByServiceStrategy())
        
        return registry
    
    def _create_default_connection_registry(self) -> ConnectionRegistry:
        """Create a connection registry with default rules.
        
        Returns:
            ConnectionRegistry with default rules registered
        """
        from core_engine.connect.rules import (
            CallConnectionRule,
            PersistenceConnectionRule,
            ValidationConnectionRule,
            MigrationConnectionRule,
            TransactionConnectionRule,
            QueryConnectionRule,
            EndpointConnectionRule,
        )
        
        registry = ConnectionRegistry()
        registry.register(CallConnectionRule())
        registry.register(PersistenceConnectionRule())
        registry.register(ValidationConnectionRule())
        registry.register(MigrationConnectionRule())
        registry.register(TransactionConnectionRule())
        registry.register(QueryConnectionRule())
        registry.register(EndpointConnectionRule())
        
        return registry
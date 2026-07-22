"""Public Interface Change Pass - identifies changes to public interfaces."""
from __future__ import annotations

from operational.model import OperationalChangeModel

from ..model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class PublicInterfaceChangePass(DiscoveryCompilerPass):
    """Identify changes to public interfaces.
    
    This pass answers: Which public interfaces have changed?
    
    It analyzes the change model and API model to find changes to
    public interfaces like REST endpoints, GraphQL schemas, etc.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "public_interface_change"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with public interface change discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        if operational_model is None or operational_model.change is None:
            return context
        change_model = operational_model.change
        
        # Track changed public interfaces
        changed_interfaces: list[str] = []
        interface_types: list[str] = []
        
        # Check for changed endpoints
        if hasattr(change_model, 'changed_endpoints'):
            for endpoint_change in change_model.changed_endpoints:
                if hasattr(endpoint_change, 'endpoint'):
                    changed_interfaces.append(endpoint_change.endpoint)
                    interface_types.append("endpoint")
                elif hasattr(endpoint_change, 'route'):
                    changed_interfaces.append(endpoint_change.route)
                    interface_types.append("endpoint")
        
        # Check API model if present
        if hasattr(operational_model, 'api') and operational_model.api is not None:
            api_model = operational_model.api
            
            # Extract changed APIs if available
            if hasattr(api_model, 'changed_endpoints'):
                changed_interfaces.extend(api_model.changed_endpoints)
                interface_types.extend(["api"] * len(api_model.changed_endpoints))
            
            if hasattr(api_model, 'changed_operations'):
                changed_interfaces.extend(api_model.changed_operations)
                interface_types.extend(["api"] * len(api_model.changed_operations))
        
        if not changed_interfaces:
            return context
        
        # Deduplicate while preserving order
        seen = set()
        unique_interfaces = []
        unique_types = []
        for interface, interface_type in zip(changed_interfaces, interface_types):
            if interface not in seen:
                seen.add(interface)
                unique_interfaces.append(interface)
                unique_types.append(interface_type)
        
        # Create references to change artifacts
        references = tuple(
            DiscoveryReference(
                artifact_type="change",
                artifact_id=f"endpoint::{interface}",
                location=interface,
            )
            for interface in unique_interfaces
        )
        
        discovery = Discovery(
            id="public_interface_change::changed_interfaces",
            kind=DiscoveryKind.PUBLIC_INTERFACE_CHANGE,
            facts=DiscoveryFact(
                changed_interfaces=tuple(unique_interfaces),
                interface_types=tuple(unique_types),
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context
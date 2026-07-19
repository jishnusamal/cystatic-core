"""Discovery compiler passes."""
from discovery.passes.base import (
    DiscoveryPassContext,
    DiscoveryCompilerPass,
)
from discovery.passes.shared_execution import SharedExecutionPass
from discovery.passes.validation_gap import ValidationGapPass
from discovery.passes.boundary_crossing import BoundaryCrossingPass
from discovery.passes.hidden_relationship import HiddenRelationshipPass
from discovery.passes.deep_execution import DeepExecutionPass
from discovery.passes.shared_dependency import SharedDependencyPass
from discovery.passes.event_publication import EventPublicationPass
from discovery.passes.state_mutation import StateMutationPass
from discovery.passes.public_interface_change import PublicInterfaceChangePass

__all__ = [
    "DiscoveryPassContext",
    "DiscoveryCompilerPass",
    "SharedExecutionPass",
    "ValidationGapPass",
    "BoundaryCrossingPass",
    "HiddenRelationshipPass",
    "DeepExecutionPass",
    "SharedDependencyPass",
    "EventPublicationPass",
    "StateMutationPass",
    "PublicInterfaceChangePass",
]
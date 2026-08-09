"""Discovery compiler passes."""

from .base import DiscoveryPassContext, DiscoveryCompilerPass
from .shared_execution import SharedExecutionPass
from .validation_gap import ValidationGapPass
from .boundary_crossing import BoundaryCrossingPass
from .hidden_relationship import HiddenRelationshipPass
from .deep_execution import DeepExecutionPass
from .shared_dependency import SharedDependencyPass
from .event_publication import EventPublicationPass
from .state_mutation import StateMutationPass
from .public_interface_change import PublicInterfaceChangePass

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

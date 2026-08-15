"""Discovery compiler passes."""

from .base import DiscoveryCompilerPass, DiscoveryPassContext
from .boundary_crossing import BoundaryCrossingPass
from .deep_execution import DeepExecutionPass
from .event_publication import EventPublicationPass
from .hidden_relationship import HiddenRelationshipPass
from .public_interface_change import PublicInterfaceChangePass
from .shared_dependency import SharedDependencyPass
from .shared_execution import SharedExecutionPass
from .state_mutation import StateMutationPass
from .validation_gap import ValidationGapPass

__all__ = [
    "BoundaryCrossingPass",
    "DeepExecutionPass",
    "DiscoveryCompilerPass",
    "DiscoveryPassContext",
    "EventPublicationPass",
    "HiddenRelationshipPass",
    "PublicInterfaceChangePass",
    "SharedDependencyPass",
    "SharedExecutionPass",
    "StateMutationPass",
    "ValidationGapPass",
]

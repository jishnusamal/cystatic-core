from collections import deque
from typing import Set
from .requirements import ResolutionRequirement

class ResolutionFrontier:
    """Manages the set/queue of active and processed requirements."""

    def __init__(self) -> None:
        self._pending = deque()
        self._processed: Set[ResolutionRequirement] = set()

    def add(self, requirement: ResolutionRequirement) -> None:
        """Add a requirement to the frontier if it hasn't been processed yet."""
        if requirement not in self._processed and requirement not in self._pending:
            self._pending.append(requirement)

    def pop(self) -> ResolutionRequirement | None:
        """Pop a pending requirement, marking it as processed."""
        if not self._pending:
            return None
        req = self._pending.popleft()
        self._processed.add(req)
        return req

    def is_empty(self) -> bool:
        return len(self._pending) == 0

    def clear(self) -> None:
        self._pending.clear()
        self._processed.clear()

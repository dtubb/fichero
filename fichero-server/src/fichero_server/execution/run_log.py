"""A run's log, bounded in memory (#5376, `activity.run.log-is-bounded`): the first lines and the latest are kept, the
middle is counted, never held. Every line still streams to the viewer as it happens and is appended to the stored
log at each node boundary (`since`), so only the run's final text names how many lines it leaves out."""
from __future__ import annotations

from collections import deque

HEAD_LINES = 200
TAIL_LINES = 1800


class BoundedLog:
    def __init__(self, head: int = HEAD_LINES, tail: int = TAIL_LINES) -> None:
        self._head_max = head
        self._head: list[str] = []
        self._tail: deque[str] = deque(maxlen=tail)
        self.count = 0

    def append(self, line: str) -> None:
        if len(self._head) < self._head_max:
            self._head.append(line)
        else:
            self._tail.append(line)
        self.count += 1

    def __len__(self) -> int:
        return self.count

    @property
    def omitted(self) -> int:
        return self.count - len(self._head) - len(self._tail)

    def since(self, start: int) -> list[str]:
        """The lines from the absolute index `start` on that are still held (all of them, when none was dropped)."""
        first_tail = self.count - len(self._tail)
        held = [(i, line) for i, line in enumerate(self._head)] + [
            (first_tail + k, line) for k, line in enumerate(self._tail)]
        return [line for i, line in held if i >= start]

    def text(self) -> str:
        lines = [*self._head, *([f"… {self.omitted} log lines omitted …"] if self.omitted else []), *self._tail]
        return "\n".join(lines)


def bounded_final_state(state: object, limit: int = 2000) -> object:
    """The `complete` frame's view of the final state (#5376): a value whose JSON is over ``limit`` characters is
    replaced by {"omitted": size}; the full state is on the run's checkpoint, not in every subscriber's replay."""
    import json

    if not isinstance(state, dict):
        return state
    kept = {}
    for key, value in state.items():
        size = len(json.dumps(value, default=str))
        kept[key] = value if size <= limit else {"omitted": size}
    return kept

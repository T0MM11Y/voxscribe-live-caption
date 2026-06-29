"""State management API."""

import threading
from typing import Optional

class StateManager:
    """Small observable state container for controller/UI coordination."""

    def __init__(self, initial_state: Optional[dict] = None):
        self._state = dict(initial_state or {})
        self._listeners = []
        self._lock = threading.RLock()

    def get(self, key: str, default=None):
        with self._lock:
            return self._state.get(key, default)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def set(self, key: str, value):
        self.update(**{key: value})

    def update(self, **changes):
        with self._lock:
            self._state.update(changes)
            snapshot = dict(self._state)
        for listener in list(self._listeners):
            try:
                listener(snapshot, dict(changes))
            except Exception:
                pass

    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

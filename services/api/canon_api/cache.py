import time
from collections.abc import Callable
from threading import Lock

DEFAULT_TTL_SECONDS = 60.0


class TimedCache[T]:
    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._value: T | None = None
        self._stored_at = 0.0
        self._lock = Lock()

    def get(self, build: Callable[[], T]) -> T:
        with self._lock:
            age = time.monotonic() - self._stored_at
            if self._value is not None and age < self.ttl_seconds:
                return self._value
            value = build()
            self._value = value
            self._stored_at = time.monotonic()
            return value

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._stored_at = 0.0

"""A local model that loads on first use and unloads after it has been idle (ARCHITECTURE.md
section 15). Loading happens once even when several threads ask at the same time."""

import gc
import threading
from collections.abc import Callable
from typing import Protocol, cast

IDLE_SECONDS = 600.0


class TimerLike(Protocol):
    daemon: bool

    def start(self) -> None: ...

    def cancel(self) -> None: ...


class LazyModel[T]:
    def __init__(
        self,
        load: Callable[[], T],
        *,
        idle_seconds: float = IDLE_SECONDS,
        timer: Callable[[float, Callable[[], None]], TimerLike] = threading.Timer,
    ) -> None:
        self._load = load
        self._idle_seconds = idle_seconds
        self._timer_factory = timer
        self._lock = threading.Lock()
        self._value: T | None = None
        self._loaded = False
        self._timer: TimerLike | None = None
        self._generation = 0

    @property
    def loaded(self) -> bool:
        return self._loaded

    def get(self) -> T:
        with self._lock:
            if not self._loaded:
                self._value = self._load()
                self._loaded = True
            self._rearm()
            return cast("T", self._value)

    def unload(self) -> None:
        with self._lock:
            self._drop()

    def _rearm(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._generation += 1
        generation = self._generation
        timer = self._timer_factory(self._idle_seconds, lambda: self._expired(generation))
        timer.daemon = True
        timer.start()
        self._timer = timer

    def _expired(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation:
                self._drop()

    def _drop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._value = None
        self._loaded = False
        gc.collect()

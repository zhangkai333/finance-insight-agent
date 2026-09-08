from __future__ import annotations
from contextlib import contextmanager
import time
from collections.abc import Callable
from threading import BoundedSemaphore, Lock
from typing import TypeVar
T=TypeVar("T")
def retry_call(operation:Callable[[],T],*,attempts:int=3,base_delay:float=.05,retry_if:Callable[[T],bool]|None=None)->tuple[T,int]:
    if attempts<1: raise ValueError("attempts 必须大于 0")
    last:T
    for attempt in range(1,attempts+1):
        try:
            last=operation()
            if retry_if is None or not retry_if(last): return last,attempt
        except Exception:
            if attempt==attempts: raise
        if attempt<attempts: time.sleep(base_delay*(2**(attempt-1)))
    return last,attempts


class ConcurrencyLimiter:
    """Bound in-flight Agent work and expose queue pressure to health checks."""

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("并发容量必须大于 0")
        self.capacity = capacity
        self._semaphore = BoundedSemaphore(capacity)
        self._lock = Lock()
        self._active = 0

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @contextmanager
    def slot(self, timeout: float):
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Agent 并发槽位已满，等待超过 {timeout:.1f} 秒")
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
            self._semaphore.release()

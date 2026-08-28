from __future__ import annotations
import time
from collections.abc import Callable
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

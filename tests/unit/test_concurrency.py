import threading
import time

import pytest

from finance_insight.resilience import ConcurrencyLimiter


def test_concurrency_limiter_caps_active_work():
    limiter = ConcurrencyLimiter(2)
    active: list[int] = []
    peak = {"value": 0}
    lock = threading.Lock()

    def work():
        with limiter.slot(1):
            with lock:
                active.append(1)
                peak["value"] = max(peak["value"], len(active))
            time.sleep(0.03)
            with lock:
                active.pop()

    threads = [threading.Thread(target=work) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak["value"] <= 2
    assert limiter.active == 0


def test_concurrency_limiter_times_out_when_full():
    limiter = ConcurrencyLimiter(1)
    with limiter.slot(0.1):
        with pytest.raises(TimeoutError):
            with limiter.slot(0.01):
                pass

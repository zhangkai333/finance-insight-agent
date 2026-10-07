from finance_insight.resilience import retry_call
from finance_insight.stores import InMemoryStore


def test_retry_succeeds_on_third_attempt():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    value, attempts = retry_call(operation, attempts=3, base_delay=0)
    assert value == "ok" and attempts == 3


def test_memory_store_round_trip():
    store = InMemoryStore()
    store.set("x", {"a": 1}, ttl_seconds=10)
    assert store.get("x") == {"a": 1}

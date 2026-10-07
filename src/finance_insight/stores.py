from __future__ import annotations

import json
import time
from threading import RLock
from typing import Any, Protocol


class Store(Protocol):
    backend:str
    def get(self,key:str)->Any|None: ...
    def set(self,key:str,value:Any,ttl_seconds:int|None=None)->None: ...

class InMemoryStore:
    backend="memory"
    def __init__(self): self._data={}; self._expires={}; self._lock=RLock()
    def get(self,key):
        with self._lock:
            if key in self._expires and self._expires[key]<time.time(): self._data.pop(key,None); self._expires.pop(key,None); return None
            return self._data.get(key)
    def set(self,key,value,ttl_seconds=None):
        with self._lock: self._data[key]=value; self._expires[key]=time.time()+ttl_seconds if ttl_seconds else float('inf')

class RedisStore:
    backend="redis"
    def __init__(self,url:str):
        import redis
        self.client=redis.Redis.from_url(url,decode_responses=True); self.client.ping()
    def get(self,key):
        value=self.client.get(key); return json.loads(value) if value else None
    def set(self,key,value,ttl_seconds=None): self.client.set(key,json.dumps(value,ensure_ascii=False,default=str),ex=ttl_seconds)

def build_store(redis_url:str|None):
    if redis_url:
        try: return RedisStore(redis_url)
        except Exception: pass
    return InMemoryStore()

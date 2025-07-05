# cache.py

import time
from typing import Any, Dict, Tuple

class SimpleCache:
    def __init__(self):
        # we'll just use a dictionary to store everything in RAM
        # each entry will be like: { "some-key": (expires_at, value) }
        self.store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        """Try to get something from cache. Return it if not expired."""
        if key in self.store:
            expire_time, value = self.store[key]
            if time.time() < expire_time:
                print(f"[CACHE HIT] Key: {key}")
                return value
            else:
                print(f"[CACHE EXPIRED] Key: {key}")
                del self.store[key]  # expired stuff gets removed
        else:
            print(f"[CACHE MISS] Key: {key}")
        return None  # nothing found or it's expired

    def set(self, key: str, value: Any, ttl: int = 300):
        """Save stuff in cache with a time-to-live (default 5 minutes)."""
        expire_time = time.time() + ttl  # mark when it should expire
        self.store[key] = (expire_time, value)
        print(f"[CACHE SET] Key: {key} | TTL: {ttl}s")

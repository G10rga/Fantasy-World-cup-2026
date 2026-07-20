"""Shared caching helpers and data-delay flag for API fallback chain."""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DATA_DELAYED_KEY = "data_source_delayed"


def get_flask_cache():
    try:
        from app import cache as flask_cache
        if flask_cache.app is not None:
            return flask_cache
    except (RuntimeError, ImportError):
        pass
    return None


def cached_fetch(cache_key: str, ttl: int, fetch_fn: Callable[[], Any]) -> Any:
    cache = get_flask_cache()
    if cache and ttl:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit
    result = fetch_fn()
    if cache and ttl and result is not None:
        cache.set(cache_key, result, timeout=ttl)
    return result


def set_data_delayed(delayed: bool = True) -> None:
    cache = get_flask_cache()
    if cache:
        cache.set(DATA_DELAYED_KEY, delayed, timeout=3600)


def is_data_delayed() -> bool:
    cache = get_flask_cache()
    if cache:
        return bool(cache.get(DATA_DELAYED_KEY))
    return False


def clear_data_delayed() -> None:
    cache = get_flask_cache()
    if cache:
        cache.delete(DATA_DELAYED_KEY)

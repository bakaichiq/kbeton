from __future__ import annotations

import pytest

pytest.importorskip("aiogram")
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from apps.bot.main import build_fsm_storage
from kbeton.core.config import settings


def test_build_memory_storage(monkeypatch):
    monkeypatch.setattr(settings, "bot_fsm_storage", "memory")
    storage = build_fsm_storage()
    assert isinstance(storage, MemoryStorage)


def test_build_redis_storage(monkeypatch):
    monkeypatch.setattr(settings, "bot_fsm_storage", "redis")
    monkeypatch.setattr(settings, "bot_fsm_redis_url", "redis://localhost:6379/15")
    storage = build_fsm_storage()
    assert isinstance(storage, RedisStorage)


def test_build_storage_invalid_value(monkeypatch):
    monkeypatch.setattr(settings, "bot_fsm_storage", "unsupported")
    with pytest.raises(RuntimeError):
        build_fsm_storage()

from __future__ import annotations

import asyncio
from typing import Callable, TypeVar, Any

T = TypeVar("T")

async def to_thread(func: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(func, *args, **kwargs)

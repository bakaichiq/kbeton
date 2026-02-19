from __future__ import annotations

import asyncio
import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage

from kbeton.core.config import settings
from kbeton.core.logging import configure_logging

from apps.bot.rbac import RBACMiddleware
from apps.bot.routers import start as start_router
from apps.bot.routers import errors as errors_router
from apps.bot.routers import finance as finance_router
from apps.bot.routers import production as production_router
from apps.bot.routers import warehouse as warehouse_router
from apps.bot.routers import admin as admin_router

log = structlog.get_logger(__name__)


def build_fsm_storage() -> BaseStorage:
    if settings.bot_fsm_storage == "redis":
        return RedisStorage.from_url(settings.bot_fsm_redis_url)
    if settings.bot_fsm_storage == "memory":
        return MemoryStorage()
    raise RuntimeError("BOT_FSM_STORAGE must be one of: memory, redis")


async def main() -> None:
    configure_logging(settings.log_level)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    storage = build_fsm_storage()
    dp = Dispatcher(storage=storage)
    dp.message.middleware(RBACMiddleware())
    dp.callback_query.middleware(RBACMiddleware())

    dp.include_router(errors_router.router)
    dp.include_router(start_router.router)
    dp.include_router(finance_router.router)
    dp.include_router(production_router.router)
    dp.include_router(warehouse_router.router)
    dp.include_router(admin_router.router)

    log.info("bot_start", env=settings.env, fsm_storage=settings.bot_fsm_storage)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

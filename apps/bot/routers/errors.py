from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.types import ErrorEvent

log = structlog.get_logger(__name__)
router = Router()

@router.errors()
async def on_error(event: ErrorEvent):
    # Handle RBAC and validation errors gracefully in chat, keep stack in logs.
    exc = event.exception
    log.warning("bot_error", exc_type=type(exc).__name__, exc=str(exc))
    try:
        # event.update may include message/callback; reply if possible
        if isinstance(exc, PermissionError):
            if str(exc) == "No user context":
                msg = "⛔️ Не удалось определить пользователя. Пишите в личный чат или отключите анонимного администратора."
            else:
                msg = "⛔️ Нет доступа."
        else:
            err_text = str(exc).strip() or "Неизвестная ошибка"
            msg = f"⚠️ Ошибка: {err_text}"
        if event.update.message:
            await event.update.message.answer(msg)
        elif event.update.callback_query:
            await event.update.callback_query.message.answer(msg)
            await event.update.callback_query.answer()
    except Exception:
        # ignore secondary errors
        pass
    return True

from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

from kbeton.db.session import session_scope
from kbeton.services.auth import get_or_create_user
from kbeton.models.enums import Role
from kbeton.services.audit import audit_log

class RBACMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]], event: Any, data: Dict[str, Any]) -> Any:
        # attach db_user into data for handlers
        data["event"] = event
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
            data["event_chat"] = event.chat
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
            if event.message:
                data["event_chat"] = event.message.chat
        if tg_user:
            data["event_from_user"] = tg_user
            full_name = " ".join([p for p in [tg_user.first_name, tg_user.last_name] if p]).strip()
            with session_scope() as session:
                user = get_or_create_user(session, tg_id=tg_user.id, full_name=full_name)
                data["db_user"] = user
                audit_log(session, actor_user_id=user.id, action="tg_event", entity_type=type(event).__name__, entity_id=str(getattr(event, "message_id", "")), payload={"username": tg_user.username or "", "text": getattr(event, "text", "")})
        return await handler(event, data)

def role_allowed(user_role: Role, allowed: set[Role]) -> bool:
    return user_role == Role.Admin or user_role in allowed

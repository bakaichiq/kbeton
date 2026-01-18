from __future__ import annotations

from kbeton.models.user import User
from kbeton.models.enums import Role
from kbeton.db.session import session_scope
from kbeton.services.auth import get_or_create_user

def _extract_full_name(tg_user) -> str:
    first = getattr(tg_user, "first_name", "") or ""
    last = getattr(tg_user, "last_name", "") or ""
    return " ".join([p for p in [first, last] if p]).strip()

def _resolve_tg_context(data, event: object | None = None) -> tuple[object | None, object | None]:
    tg_user = data.get("event_from_user")
    chat = data.get("event_chat")
    if tg_user or chat:
        return tg_user, chat
    if event is not None:
        msg = getattr(event, "message", None)
        if msg is not None and getattr(msg, "from_user", None):
            return msg.from_user, getattr(msg, "chat", None)
        if getattr(event, "from_user", None):
            return event.from_user, getattr(event, "chat", None)
        if getattr(event, "chat", None):
            return None, event.chat
    for key in ("event", "message", "callback_query", "update", "event_update"):
        ev = data.get(key)
        if ev is None:
            continue
        msg = getattr(ev, "message", None)
        if msg is not None:
            if getattr(msg, "from_user", None):
                return msg.from_user, getattr(msg, "chat", None)
        cb = getattr(ev, "callback_query", None)
        if cb is not None:
            if getattr(cb, "from_user", None):
                cb_chat = getattr(getattr(cb, "message", None), "chat", None)
                return cb.from_user, cb_chat
        if getattr(ev, "from_user", None):
            return ev.from_user, getattr(ev, "chat", None)
        if getattr(ev, "chat", None):
            return None, ev.chat
    return None, None

def get_db_user(data, event: object | None = None) -> User:
    user = data.get("db_user")
    if user is not None:
        return user
    tg_user, chat = _resolve_tg_context(data, event)
    if tg_user is None:
        if chat is None or getattr(chat, "type", None) != "private":
            raise PermissionError("No user context")
        tg_id = chat.id
        full_name = getattr(chat, "full_name", "") or getattr(chat, "title", "") or ""
    else:
        tg_id = tg_user.id
        full_name = _extract_full_name(tg_user)
    with session_scope() as session:
        user = get_or_create_user(session, tg_id=tg_id, full_name=full_name)
        data["db_user"] = user
    return user

def ensure_role(user: User, allowed: set[Role]) -> None:
    """RBAC gate.

    Admin is always allowed.
    """
    if not user.is_active:
        raise PermissionError("User inactive")
    if user.role == Role.Admin:
        return
    if user.role not in allowed:
        raise PermissionError("Access denied")

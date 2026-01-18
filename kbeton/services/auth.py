from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from kbeton.models.user import User
from kbeton.models.enums import Role

def get_or_create_user(session: Session, tg_id: int, full_name: str) -> User:
    user = session.execute(select(User).where(User.tg_id == tg_id)).scalar_one_or_none()
    if user:
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        return user
    user = User(tg_id=tg_id, full_name=full_name or "", role=Role.Viewer, is_active=True)
    session.add(user)
    session.flush()
    return user

def require_roles(user: User, allowed: set[Role]) -> None:
    if not user.is_active:
        raise PermissionError("User is inactive")
    if user.role not in allowed:
        raise PermissionError(f"Role {user.role} is not allowed")

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from kbeton.models.enums import Role
from kbeton.models.invite import UserInvite
from kbeton.models.user import User


def generate_invite_token() -> str:
    return secrets.token_urlsafe(24)


def create_user_invite(session: Session, *, role: Role, created_by_user_id: int | None) -> UserInvite:
    invite = UserInvite(
        token=generate_invite_token(),
        role=role,
        created_by_user_id=created_by_user_id,
    )
    session.add(invite)
    session.flush()
    return invite


def consume_user_invite(session: Session, *, token: str, user: User) -> UserInvite | None:
    invite = session.execute(select(UserInvite).where(UserInvite.token == token)).scalar_one_or_none()
    if invite is None or invite.used_at is not None:
        return None
    user.role = invite.role
    user.is_active = True
    invite.used_by_user_id = user.id
    invite.used_at = datetime.now().astimezone()
    session.flush()
    return invite

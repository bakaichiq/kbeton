from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kbeton.db.base import Base
from kbeton.models.enums import Role
from kbeton.models.invite import UserInvite
from kbeton.models.user import User
from kbeton.services.invites import create_user_invite, consume_user_invite


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[User.__table__, UserInvite.__table__])
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    return Session()


def test_user_invite_is_one_time_and_assigns_role():
    session = _session()
    try:
        admin = User(tg_id=1, full_name="Admin", role=Role.Admin, is_active=True)
        user = User(tg_id=2, full_name="User", role=Role.Viewer, is_active=True)
        session.add_all([admin, user])
        session.flush()

        invite = create_user_invite(session, role=Role.Operator, created_by_user_id=admin.id)
        session.commit()

        applied = consume_user_invite(session, token=invite.token, user=user)
        session.commit()

        assert applied is not None
        assert user.role == Role.Operator
        assert applied.used_by_user_id == user.id
        assert applied.used_at is not None

        second_try = consume_user_invite(session, token=invite.token, user=user)
        assert second_try is None
    finally:
        session.close()

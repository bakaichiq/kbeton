#!/usr/bin/env python
from __future__ import annotations

import argparse
from kbeton.db.session import session_scope
from kbeton.models.user import User
from kbeton.models.enums import Role
from kbeton.services.audit import audit_log

def main():
    p = argparse.ArgumentParser(description="Create or update a user by Telegram ID.")
    p.add_argument("--tg-id", type=int, required=True, help="Telegram user id")
    p.add_argument("--name", type=str, default="", help="Full name")
    p.add_argument("--role", type=str, default="Viewer", choices=[r.value for r in Role], help="Role")
    args = p.parse_args()

    with session_scope() as session:
        user = session.query(User).filter(User.tg_id == args.tg_id).one_or_none()
        if user is None:
            user = User(tg_id=args.tg_id, full_name=args.name or "", role=Role(args.role), is_active=True)
            session.add(user)
            session.flush()
            audit_log(session, actor_user_id=user.id, action="user_create", entity_type="user", entity_id=str(user.id), payload={"tg_id": args.tg_id, "role": args.role})
            print(f"Created user id={user.id} tg_id={user.tg_id} role={user.role.value}")
        else:
            if args.name:
                user.full_name = args.name
            user.role = Role(args.role)
            user.is_active = True
            audit_log(session, actor_user_id=user.id, action="user_update", entity_type="user", entity_id=str(user.id), payload={"tg_id": args.tg_id, "role": args.role})
            print(f"Updated user id={user.id} tg_id={user.tg_id} role={user.role.value}")

if __name__ == "__main__":
    main()

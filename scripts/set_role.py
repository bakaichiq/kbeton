#!/usr/bin/env python
from __future__ import annotations

import argparse
from kbeton.db.session import session_scope
from kbeton.models.user import User
from kbeton.models.enums import Role
from kbeton.services.audit import audit_log

def main():
    p = argparse.ArgumentParser(description="Set role for an existing user by Telegram ID.")
    p.add_argument("--tg-id", type=int, required=True)
    p.add_argument("--role", type=str, required=True, choices=[r.value for r in Role])
    args = p.parse_args()

    with session_scope() as session:
        user = session.query(User).filter(User.tg_id == args.tg_id).one_or_none()
        if user is None:
            raise SystemExit("User not found. Run scripts/create_user.py first.")
        old = user.role.value
        user.role = Role(args.role)
        audit_log(session, actor_user_id=user.id, action="user_set_role", entity_type="user", entity_id=str(user.id), payload={"old": old, "new": args.role})
        print(f"OK. tg_id={args.tg_id} role {old} -> {args.role}")

if __name__ == "__main__":
    main()

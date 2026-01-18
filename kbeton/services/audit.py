from __future__ import annotations

from sqlalchemy.orm import Session
from kbeton.models.audit import AuditLog

def audit_log(session: Session, *, actor_user_id: int | None, action: str, entity_type: str = "", entity_id: str = "", payload: dict | None = None) -> None:
    session.add(AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        payload=payload or {},
    ))

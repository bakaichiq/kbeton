from __future__ import annotations

from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from kbeton.models.pricing import PriceVersion
from kbeton.models.enums import PriceKind

def set_price(session: Session, *, kind: PriceKind, item_key: str, price: float, currency: str, valid_from: datetime, changed_by_user_id: int | None, comment: str="") -> PriceVersion:
    pv = PriceVersion(
        kind=kind,
        item_key=item_key,
        price=price,
        currency=currency,
        valid_from=valid_from,
        changed_by_user_id=changed_by_user_id,
        comment=comment or "",
    )
    session.add(pv)
    session.flush()
    return pv

def get_price(session: Session, *, kind: PriceKind, item_key: str, at: datetime) -> PriceVersion | None:
    return session.execute(
        select(PriceVersion)
        .where(PriceVersion.kind == kind, PriceVersion.item_key == item_key, PriceVersion.valid_from <= at)
        .order_by(desc(PriceVersion.valid_from), desc(PriceVersion.id))
        .limit(1)
    ).scalar_one_or_none()

def get_current_prices(session: Session) -> dict:
    # latest per (kind, item_key)
    rows = session.execute(select(PriceVersion).order_by(desc(PriceVersion.valid_from), desc(PriceVersion.id))).scalars().all()
    seen = set()
    out = []
    for r in rows:
        key = (r.kind.value, r.item_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return {
        "prices": [
            {"kind": r.kind.value, "item_key": r.item_key, "price": float(r.price), "currency": r.currency, "valid_from": r.valid_from.isoformat()}
            for r in out
        ]
    }

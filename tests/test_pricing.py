from __future__ import annotations

from datetime import datetime, timezone, timedelta

from kbeton.models.enums import PriceKind
from kbeton.models.user import User
from kbeton.models.enums import Role
from kbeton.services.pricing import set_price, get_price

def test_price_versioning(sqlite_session):
    s = sqlite_session
    u = User(tg_id=1, full_name="Admin", role=Role.Admin, is_active=True)
    s.add(u); s.flush()

    t0 = datetime(2026,1,1,0,0,0,tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=10)

    set_price(s, kind=PriceKind.concrete, item_key="M300", price=4500, currency="KGS", valid_from=t0, changed_by_user_id=u.id, comment="")
    set_price(s, kind=PriceKind.concrete, item_key="M300", price=4800, currency="KGS", valid_from=t1, changed_by_user_id=u.id, comment="")

    p_at_early = get_price(s, kind=PriceKind.concrete, item_key="M300", at=t0 + timedelta(days=1))
    assert p_at_early is not None and float(p_at_early.price) == 4500

    p_at_late = get_price(s, kind=PriceKind.concrete, item_key="M300", at=t1 + timedelta(days=1))
    assert p_at_late is not None and float(p_at_late.price) == 4800

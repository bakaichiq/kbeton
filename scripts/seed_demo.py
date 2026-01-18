#!/usr/bin/env python
from __future__ import annotations

from datetime import datetime, timezone
from kbeton.db.session import session_scope
from kbeton.models.enums import TxType, PatternType, PriceKind, Role
from kbeton.models.finance import FinanceArticle, MappingRule
from kbeton.models.inventory import InventoryItem, InventoryBalance
from kbeton.models.user import User
from kbeton.services.pricing import set_price

def main():
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        # Ensure at least one Admin exists
        admin = session.query(User).filter(User.role == Role.Admin).first()
        if admin is None:
            admin = User(tg_id=1, full_name="Demo Admin", role=Role.Admin, is_active=True)
            session.add(admin)
            session.flush()

        # Articles
        income = [("Продажа бетона", TxType.income), ("Продажа блоков", TxType.income)]
        expense = [("Цемент", TxType.expense), ("Дизель", TxType.expense), ("Зарплата", TxType.expense)]
        for name, kind in income + expense:
            if session.query(FinanceArticle).filter(FinanceArticle.name == name).one_or_none() is None:
                session.add(FinanceArticle(name=name, kind=kind, is_active=True))
        session.flush()

        # Rules
        art_beton = session.query(FinanceArticle).filter(FinanceArticle.name == "Продажа бетона").one()
        art_blocks = session.query(FinanceArticle).filter(FinanceArticle.name == "Продажа блоков").one()
        art_cement = session.query(FinanceArticle).filter(FinanceArticle.name == "Цемент").one()

        def add_rule(kind, pattern, article_id, ptype=PatternType.contains, priority=100):
            exists = session.query(MappingRule).filter(MappingRule.pattern == pattern, MappingRule.article_id == article_id).one_or_none()
            if exists is None:
                session.add(MappingRule(kind=kind, pattern_type=ptype, pattern=pattern, priority=priority, is_active=True, article_id=article_id, created_by_user_id=admin.id))

        add_rule(TxType.income, "бетон", art_beton.id, priority=110)
        add_rule(TxType.income, "блок", art_blocks.id, priority=105)
        add_rule(TxType.expense, "цемент", art_cement.id, priority=120)

        # Inventory items
        items = [
            ("Электроды", "кг", 10),
            ("Диск отрезной", "шт", 5),
            ("Масло", "л", 20),
        ]
        for name, uom, min_qty in items:
            it = session.query(InventoryItem).filter(InventoryItem.name == name).one_or_none()
            if it is None:
                it = InventoryItem(name=name, uom=uom, min_qty=min_qty, is_active=True)
                session.add(it)
                session.flush()
                session.add(InventoryBalance(item_id=it.id, qty=min_qty * 3))
        session.flush()

        # Prices
        set_price(session, kind=PriceKind.concrete, item_key="M300", price=4500, currency="KGS", valid_from=now, changed_by_user_id=admin.id, comment="Seed")
        set_price(session, kind=PriceKind.blocks, item_key="blocks", price=55, currency="KGS", valid_from=now, changed_by_user_id=admin.id, comment="Seed")

    print("Seed done.")

if __name__ == "__main__":
    main()

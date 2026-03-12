from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kbeton.db.base import Base
from kbeton.models.audit import AuditLog
from kbeton.models.enums import ProductType, Role, ShiftStatus, ShiftType
from kbeton.models.inventory import InventoryBalance, InventoryItem, InventoryTxn
from kbeton.models.production import ProductionOutput, ProductionShift
from kbeton.models.recipes import ConcreteRecipe
from kbeton.models.user import User
from kbeton.services.production import approve_shift, parse_concrete


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    return Session()


def test_parse_concrete_keeps_supported_formats():
    assert parse_concrete("M300=10, M350 5") == [("M300", 10.0), ("M350", 5.0)]
    assert parse_concrete("M300 10.5, M350 5,25") == [("M300", 10.5), ("M350", 5.25)]
    assert parse_concrete("") == []


def test_approve_shift_blocks_when_stock_is_insufficient():
    session = _session()
    try:
        actor = User(tg_id=1, full_name="Admin", role=Role.Admin, is_active=True)
        shift = ProductionShift(
            operator_user_id=None,
            date=date.today(),
            shift_type=ShiftType.day,
            status=ShiftStatus.submitted,
        )
        recipe = ConcreteRecipe(
            mark="M300",
            cement_kg=350,
            sand_t=0.8,
            crushed_stone_t=1.2,
            screening_t=0.1,
            water_l=180,
            additives_l=5,
            is_active=True,
        )
        session.add_all([actor, shift, recipe])
        session.flush()
        session.add(
            ProductionOutput(
                shift_id=shift.id,
                product_type=ProductType.concrete,
                quantity=1,
                uom="м3",
                mark="M300",
            )
        )
        items = [
            InventoryItem(name="цемент", uom="кг", min_qty=0, is_active=True),
            InventoryItem(name="песок", uom="тн", min_qty=0, is_active=True),
            InventoryItem(name="щебень", uom="тн", min_qty=0, is_active=True),
            InventoryItem(name="отсев", uom="тн", min_qty=0, is_active=True),
        ]
        session.add_all(items)
        session.flush()
        balances = [
            InventoryBalance(item_id=items[0].id, qty=100),
            InventoryBalance(item_id=items[1].id, qty=10),
            InventoryBalance(item_id=items[2].id, qty=10),
            InventoryBalance(item_id=items[3].id, qty=10),
        ]
        session.add_all(balances)
        session.commit()

        result = approve_shift(session, shift_id=shift.id, actor_user_id=actor.id)
        session.commit()

        session.refresh(shift)
        blocked_log = session.query(AuditLog).filter(AuditLog.action == "shift_approve_blocked").one()

        assert result.approved is False
        assert any("Недостаточно 'цемент'" in error for error in result.errors)
        assert shift.status == ShiftStatus.submitted
        assert blocked_log.entity_id == str(shift.id)
        assert session.query(InventoryTxn).count() == 0
    finally:
        session.close()

from __future__ import annotations

from datetime import date

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.orm import sessionmaker

from kbeton.models.counterparty import CounterpartySnapshot, CounterpartyBalance
from kbeton.models.enums import ProductType, ShiftStatus, ShiftType
from kbeton.models.inventory import InventoryItem, InventoryBalance
from kbeton.models.production import ProductionShift, ProductionOutput, ProductionRealization

from apps.bot.routers.finance import _build_dashboard_text
from kbeton.importers.utils import norm_counterparty_name


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata = MetaData()
    Table("import_jobs", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    for table in [
        CounterpartySnapshot.__table__,
        CounterpartyBalance.__table__,
        ProductionShift.__table__,
        ProductionOutput.__table__,
        ProductionRealization.__table__,
        InventoryItem.__table__,
        InventoryBalance.__table__,
    ]:
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    return Session()


def test_build_dashboard_text_uses_compact_sections():
    session = _session()
    try:
        session.execute(text("INSERT INTO import_jobs (id) VALUES (1)"))
        snap = CounterpartySnapshot(snapshot_date=date(2026, 3, 12), import_job_id=1)
        session.add(snap)
        session.flush()

        session.add_all(
            [
                CounterpartyBalance(
                    snapshot_id=snap.id,
                    counterparty_name="Аламуд",
                    counterparty_name_norm=norm_counterparty_name("Аламуд"),
                    receivable_money=1_500_000,
                    payable_money=0,
                    receivable_assets="",
                    payable_assets="",
                    ending_balance_money=1_500_000,
                ),
                CounterpartyBalance(
                    snapshot_id=snap.id,
                    counterparty_name="Авангард",
                    counterparty_name_norm=norm_counterparty_name("Авангард"),
                    receivable_money=100_000,
                    payable_money=0,
                    receivable_assets="",
                    payable_assets="",
                    ending_balance_money=100_000,
                ),
                CounterpartyBalance(
                    snapshot_id=snap.id,
                    counterparty_name="Терек-Таш цемент",
                    counterparty_name_norm=norm_counterparty_name("Терек-Таш цемент"),
                    receivable_money=0,
                    payable_money=150_000,
                    receivable_assets="",
                    payable_assets="",
                    ending_balance_money=-150_000,
                ),
            ]
        )

        shift = ProductionShift(
            date=date.today(),
            shift_type=ShiftType.day,
            equipment="РБУ",
            area="РБУ",
            counterparty_name="Аламуд",
            status=ShiftStatus.approved,
        )
        session.add(shift)
        session.flush()

        concrete = ProductionOutput(
            shift_id=shift.id,
            product_type=ProductType.concrete,
            quantity=300,
            uom="м3",
            mark="M350",
        )
        stone = ProductionOutput(
            shift_id=shift.id,
            product_type=ProductType.crushed_stone,
            quantity=100,
            uom="тн",
            mark="",
        )
        session.add_all([concrete, stone])
        session.flush()

        session.add(
            ProductionRealization(
                output_id=concrete.id,
                realized_qty=300,
                unit_price=1900,
                total_amount=570_000,
            )
        )

        session.add_all(
            [
                InventoryItem(id=1, name="Щебень", uom="тн", min_qty=0, is_active=True),
                InventoryItem(id=2, name="Отсев", uom="тн", min_qty=0, is_active=True),
                InventoryItem(id=3, name="Песок", uom="тн", min_qty=0, is_active=True),
                InventoryItem(id=4, name="Цемент", uom="кг", min_qty=0, is_active=True),
                InventoryItem(id=5, name="Топливо", uom="л", min_qty=0, is_active=True),
            ]
        )
        session.add_all(
            [
                InventoryBalance(item_id=1, qty=8000),
                InventoryBalance(item_id=2, qty=7000),
                InventoryBalance(item_id=3, qty=4000),
                InventoryBalance(item_id=4, qty=200),
                InventoryBalance(item_id=5, qty=2000),
            ]
        )
        session.commit()

        dashboard_text = _build_dashboard_text(session, start=date(date.today().year, date.today().month, 1), end=date.today())

        assert "Дата:" in dashboard_text
        assert "Р/с: нет данных" in dashboard_text
        assert "Реализация:" in dashboard_text
        assert "Аламуд" in dashboard_text
        assert "570 000 сом" in dashboard_text
        assert "долг 1 500 000 сом" in dashboard_text
        assert "Д/з задолженность:" in dashboard_text
        assert "К/з задолженность:" in dashboard_text
        assert "Производство:" in dashboard_text
        assert "M350" in dashboard_text
        assert "Щебень" in dashboard_text
        assert "Склад:" in dashboard_text
        assert "Топливо" in dashboard_text
    finally:
        session.close()

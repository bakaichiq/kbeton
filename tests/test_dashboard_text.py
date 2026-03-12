from __future__ import annotations

from datetime import date

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.orm import sessionmaker

from kbeton.models.counterparty import CounterpartySnapshot, CounterpartyBalance
from kbeton.models.enums import ProductType, ShiftStatus, ShiftType, TxType
from kbeton.models.finance import FinanceArticle, FinanceTransaction, ImportJob
from kbeton.models.inventory import InventoryItem, InventoryBalance
from kbeton.models.production import ProductionShift, ProductionOutput, ProductionRealization
from kbeton.models.user import User

from apps.bot.routers.finance import _build_dashboard_text
from kbeton.importers.utils import norm_counterparty_name


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    for table in [
        User.__table__,
        FinanceArticle.__table__,
        ImportJob.__table__,
        FinanceTransaction.__table__,
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


def test_build_dashboard_text_uses_visual_sections():
    session = _session()
    try:
        session.add(User(id=1, tg_id=1, full_name="Admin", is_active=True))
        session.flush()

        income_article = FinanceArticle(name="Поступление на р/с", kind=TxType.income, is_active=True)
        expense_article = FinanceArticle(name="Расход из кассы", kind=TxType.expense, is_active=True)
        session.add_all([income_article, expense_article])
        session.flush()

        session.add(
            ImportJob(
                id=1,
                kind="manual",
                status="done",
                filename="manual",
                s3_key="",
                summary={},
                created_by_user_id=1,
            )
        )
        session.flush()

        session.add_all(
            [
                FinanceTransaction(
                    import_job_id=1,
                    date=date.today(),
                    amount=1_000_000,
                    currency="KGS",
                    tx_type=TxType.income,
                    description="Поступление на банк",
                    counterparty="",
                    income_article_id=income_article.id,
                    expense_article_id=None,
                    dedup_hash="bank-1",
                    raw_fields={"payment_channel": "bank"},
                ),
                FinanceTransaction(
                    import_job_id=1,
                    date=date.today(),
                    amount=20_000,
                    currency="KGS",
                    tx_type=TxType.expense,
                    description="Выдача из кассы",
                    counterparty="",
                    income_article_id=None,
                    expense_article_id=expense_article.id,
                    dedup_hash="cash-1",
                    raw_fields={"payment_channel": "cash"},
                ),
            ]
        )

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

        assert "Д А Ш Б О Р Д" in dashboard_text
        assert "╔" in dashboard_text
        assert "┏━━ 💰 ДЕНЬГИ" in dashboard_text
        assert date.today().strftime("%d.%m.%Y") in dashboard_text
        assert "Р/с" in dashboard_text
        assert "Касса" in dashboard_text
        assert "1 000 000 сом" in dashboard_text
        assert "-20 000 сом" in dashboard_text
        assert "Источник · операции" in dashboard_text
        assert "┏━━ 🚚 РЕАЛИЗАЦИЯ" in dashboard_text
        assert "Аламуд" in dashboard_text
        assert "570 000 сом" in dashboard_text
        assert "долг 1 500 000 сом" in dashboard_text
        assert "┏━━ 📥 Д/З ЗАДОЛЖЕННОСТЬ" in dashboard_text
        assert "┏━━ 📤 К/З ЗАДОЛЖЕННОСТЬ" in dashboard_text
        assert "Производство" in dashboard_text
        assert "M350" in dashboard_text
        assert "Щебень" in dashboard_text
        assert "┏━━ 📦 Склад" in dashboard_text
        assert "Топливо" in dashboard_text
    finally:
        session.close()


def test_build_dashboard_text_supports_summary_mode():
    session = _session()
    try:
        summary_text = _build_dashboard_text(
            session,
            start=date(date.today().year, date.today().month, 1),
            end=date.today(),
            mode="summary",
        )

        assert "Д А Ш Б О Р Д" in summary_text
        assert "┏━━ 💰 ДЕНЬГИ" in summary_text
        assert "┏━━ 📦 Склад" in summary_text
    finally:
        session.close()

#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import random
from datetime import date, datetime, timedelta, timezone

from kbeton.db.session import session_scope
from kbeton.importers.utils import norm_counterparty_name
from kbeton.models.audit import AuditLog
from kbeton.models.counterparty import CounterpartyBalance, CounterpartySnapshot
from kbeton.models.enums import (
    InventoryTxnType,
    PatternType,
    PriceKind,
    ProductType,
    Role,
    ShiftStatus,
    ShiftType,
    TxType,
)
from kbeton.models.finance import FinanceArticle, FinanceTransaction, ImportJob, MappingRule
from kbeton.models.inventory import InventoryBalance, InventoryItem, InventoryTxn
from kbeton.models.production import ProductionOutput, ProductionShift
from kbeton.models.user import User
from kbeton.services.pricing import set_price

DEFAULT_ARTICLES = [
    ("Concrete sales", TxType.income),
    ("Blocks sales", TxType.income),
    ("Delivery services", TxType.income),
    ("Cement", TxType.expense),
    ("Crushed stone", TxType.expense),
    ("Diesel", TxType.expense),
    ("Payroll", TxType.expense),
    ("Equipment repairs", TxType.expense),
]

DEFAULT_RULES = [
    (TxType.income, "concrete", "Concrete sales", PatternType.contains, 120),
    (TxType.income, "blocks", "Blocks sales", PatternType.contains, 110),
    (TxType.income, "delivery", "Delivery services", PatternType.contains, 105),
    (TxType.expense, "cement", "Cement", PatternType.contains, 120),
    (TxType.expense, "diesel", "Diesel", PatternType.contains, 115),
]

DEFAULT_ITEMS = [
    ("Electrodes", "kg", 10),
    ("Cutting disk", "pcs", 5),
    ("Oil", "l", 20),
    ("Gloves", "pair", 25),
    ("Filter", "pcs", 6),
]

CONCRETE_MARKS = ["M200", "M250", "M300", "M350"]


def _hash_dedup(*parts: str) -> str:
    h = hashlib.sha256()
    h.update("|".join(parts).encode("utf-8"))
    return h.hexdigest()


def _ensure_user(session, *, tg_id: int, full_name: str, role: Role) -> User:
    u = session.query(User).filter(User.tg_id == tg_id).one_or_none()
    if u is None:
        u = User(tg_id=tg_id, full_name=full_name, role=role, is_active=True)
        session.add(u)
        session.flush()
    return u


def _ensure_articles(session) -> dict[str, FinanceArticle]:
    out: dict[str, FinanceArticle] = {}
    for name, kind in DEFAULT_ARTICLES:
        art = session.query(FinanceArticle).filter(FinanceArticle.name == name).one_or_none()
        if art is None:
            art = FinanceArticle(name=name, kind=kind, is_active=True)
            session.add(art)
            session.flush()
        out[name] = art
    return out


def _ensure_rules(session, articles: dict[str, FinanceArticle], admin_id: int) -> None:
    for kind, pattern, art_name, ptype, priority in DEFAULT_RULES:
        art = articles.get(art_name)
        if art is None:
            continue
        exists = (
            session.query(MappingRule)
            .filter(MappingRule.pattern == pattern, MappingRule.article_id == art.id)
            .one_or_none()
        )
        if exists is None:
            session.add(
                MappingRule(
                    kind=kind,
                    pattern_type=ptype,
                    pattern=pattern,
                    priority=priority,
                    is_active=True,
                    article_id=art.id,
                    created_by_user_id=admin_id,
                )
            )


def _ensure_inventory(session) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for name, uom, min_qty in DEFAULT_ITEMS:
        it = session.query(InventoryItem).filter(InventoryItem.name == name).one_or_none()
        if it is None:
            it = InventoryItem(name=name, uom=uom, min_qty=min_qty, is_active=True)
            session.add(it)
            session.flush()
            session.add(InventoryBalance(item_id=it.id, qty=float(min_qty) * 3))
        items.append(it)
    return items


def _random_date(rng: random.Random, days: int) -> date:
    return date.today() - timedelta(days=rng.randint(0, days))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed random demo data for KBeton bot.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=45, help="Lookback window in days.")
    parser.add_argument("--finance-tx", type=int, default=120)
    parser.add_argument("--inventory-tx", type=int, default=60)
    parser.add_argument("--shifts", type=int, default=40)
    parser.add_argument("--counterparties", type=int, default=12)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        # Users for all roles
        admin = session.query(User).filter(User.role == Role.Admin).first()
        if admin is None:
            admin = _ensure_user(session, tg_id=1001, full_name="Demo Admin", role=Role.Admin)
        fin = _ensure_user(session, tg_id=1002, full_name="Demo FinDir", role=Role.FinDir)
        head = _ensure_user(session, tg_id=1003, full_name="Demo HeadProd", role=Role.HeadProd)
        oper = _ensure_user(session, tg_id=1004, full_name="Demo Operator", role=Role.Operator)
        wh = _ensure_user(session, tg_id=1005, full_name="Demo Warehouse", role=Role.Warehouse)
        _ensure_user(session, tg_id=1006, full_name="Demo Viewer", role=Role.Viewer)

        # Articles, rules, prices
        articles = _ensure_articles(session)
        _ensure_rules(session, articles, admin.id)

        for mark in CONCRETE_MARKS:
            set_price(
                session,
                kind=PriceKind.concrete,
                item_key=mark,
                price=4300 + rng.randint(0, 900),
                currency="KGS",
                valid_from=now - timedelta(days=rng.randint(10, 60)),
                changed_by_user_id=fin.id,
                comment="Seed random",
            )
        set_price(
            session,
            kind=PriceKind.blocks,
            item_key="blocks",
            price=45 + rng.randint(0, 20),
            currency="KGS",
            valid_from=now - timedelta(days=rng.randint(5, 30)),
            changed_by_user_id=fin.id,
            comment="Seed random",
        )

        # Inventory
        items = _ensure_inventory(session)
        balances: dict[int, float] = {}
        for item in items:
            bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item.id).one_or_none()
            if bal is None:
                bal = InventoryBalance(item_id=item.id, qty=0)
                session.add(bal)
                session.flush()
            balances[item.id] = float(bal.qty)
        for _ in range(args.inventory_tx):
            item = rng.choice(items)
            txn_type = rng.choice([InventoryTxnType.issue, InventoryTxnType.writeoff, InventoryTxnType.adjustment])
            qty = round(rng.uniform(1, 12), 3)
            if txn_type in (InventoryTxnType.issue, InventoryTxnType.writeoff):
                balances[item.id] = max(0.0, balances.get(item.id, 0.0) - qty)
            else:
                balances[item.id] = max(0.0, balances.get(item.id, 0.0) + qty)
            session.add(
                InventoryTxn(
                    item_id=item.id,
                    txn_type=txn_type,
                    qty=qty,
                    receiver=rng.choice(["Warehouse", "Production", "Client"]),
                    department=rng.choice(["Shop 1", "Shop 2", "Warehouse"]),
                    comment="Seed random",
                    created_by_user_id=wh.id,
                )
            )
        for item_id, qty in balances.items():
            bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one()
            bal.qty = qty

        # Production shifts and outputs
        for _ in range(args.shifts):
            shift_day = _random_date(rng, args.days)
            shift_type = rng.choice([ShiftType.day, ShiftType.night])
            status = rng.choices(
                [ShiftStatus.approved, ShiftStatus.submitted, ShiftStatus.rejected],
                weights=[0.6, 0.3, 0.1],
                k=1,
            )[0]
            shift = ProductionShift(
                operator_user_id=oper.id,
                date=shift_day,
                shift_type=shift_type,
                equipment=rng.choice(["Crusher", "Concrete plant", "Press"]),
                area=rng.choice(["Site 1", "Site 2"]),
                status=status,
                comment="Seed random",
                submitted_at=now - timedelta(days=rng.randint(0, args.days)),
            )
            if status == ShiftStatus.approved:
                shift.approved_by_user_id = head.id
                shift.approved_at = now - timedelta(days=rng.randint(0, args.days))
            session.add(shift)
            session.flush()

            outputs = [
                (ProductType.crushed_stone, round(rng.uniform(10, 120), 3), "тн", ""),
                (ProductType.screening, round(rng.uniform(5, 90), 3), "тн", ""),
                (ProductType.blocks, round(rng.uniform(200, 1200), 3), "шт", ""),
            ]
            for mark in rng.sample(CONCRETE_MARKS, k=rng.randint(1, 2)):
                outputs.append((ProductType.concrete, round(rng.uniform(5, 40), 3), "м3", mark))
            for ptype, qty, uom, mark in outputs:
                session.add(
                    ProductionOutput(
                        shift_id=shift.id,
                        product_type=ptype,
                        quantity=qty,
                        uom=uom,
                        mark=mark,
                    )
                )

        # Finance imports and transactions
        import_jobs: list[ImportJob] = []
        for idx in range(2):
            job = ImportJob(
                kind="finance",
                status="done",
                filename=f"seed_finance_{idx + 1}.xlsx",
                s3_key=f"imports/finance/seed_finance_{idx + 1}.xlsx",
                summary={"seed": True, "rows": args.finance_tx},
                created_by_user_id=fin.id,
                processed_at=now - timedelta(days=rng.randint(0, args.days)),
            )
            session.add(job)
            session.flush()
            import_jobs.append(job)

        income_articles = [a for a in articles.values() if a.kind == TxType.income]
        expense_articles = [a for a in articles.values() if a.kind == TxType.expense]
        for job in import_jobs:
            for i in range(args.finance_tx):
                tx_type = rng.choices([TxType.income, TxType.expense, TxType.unknown], weights=[0.45, 0.45, 0.1], k=1)[0]
                amount = round(rng.uniform(500, 500000), 2)
                art_income = rng.choice(income_articles) if tx_type == TxType.income else None
                art_expense = rng.choice(expense_articles) if tx_type == TxType.expense else None
                desc = rng.choice(
                    [
                        "Invoice payment",
                        "Materials supply",
                        "Advance payment",
                        "Delivery services",
                        "Incoming payment",
                        "Operating expenses",
                    ]
                )
                cp = rng.choice(
                    [
                        "Beton Service LLC",
                        "TransLogistics",
                        "StroyInvest",
                        "Client A",
                        "Client B",
                        "Supplier C",
                    ]
                )
                tx_date = _random_date(rng, args.days)
                dedup_hash = _hash_dedup(str(job.id), str(tx_date), str(amount), desc, cp, str(i))
                session.add(
                    FinanceTransaction(
                        import_job_id=job.id,
                        date=tx_date,
                        amount=amount,
                        currency="KGS",
                        tx_type=tx_type,
                        description=desc,
                        counterparty=cp,
                        income_article_id=art_income.id if art_income else None,
                        expense_article_id=art_expense.id if art_expense else None,
                        dedup_hash=dedup_hash,
                        raw_fields={"seed": True, "row": i + 1},
                    )
                )

        # Counterparty snapshots
        for i in range(2):
            job = ImportJob(
                kind="counterparty",
                status="done",
                filename=f"seed_counterparty_{i + 1}.xlsx",
                s3_key=f"imports/counterparty/seed_counterparty_{i + 1}.xlsx",
                summary={"seed": True},
                created_by_user_id=fin.id,
                processed_at=now - timedelta(days=30 * i),
            )
            session.add(job)
            session.flush()
            snap_date = (date.today().replace(day=1) - timedelta(days=30 * i))
            snap = CounterpartySnapshot(snapshot_date=snap_date, import_job_id=job.id)
            session.add(snap)
            session.flush()
            for _ in range(args.counterparties):
                name = rng.choice(
                    [
                        "Beton Service LLC",
                        "StroyMonolit",
                        "Client A",
                        "Client B",
                        "Supplier C",
                        "Alpha Group",
                        "Logistics Plus",
                    ]
                )
                recv = round(rng.uniform(0, 300000), 2)
                pay = round(rng.uniform(0, 200000), 2)
                session.add(
                    CounterpartyBalance(
                        snapshot_id=snap.id,
                        counterparty_name=name,
                        counterparty_name_norm=norm_counterparty_name(name),
                        receivable_money=recv,
                        receivable_assets="",
                        payable_money=pay,
                        payable_assets="",
                        ending_balance_money=recv - pay,
                    )
                )

        # Audit logs
        for action in ["seed_demo", "pnl_view", "inventory_txn", "shift_submitted", "shift_approved"]:
            session.add(
                AuditLog(
                    actor_user_id=admin.id,
                    action=action,
                    entity_type="seed",
                    entity_id="",
                    payload={"seed": True},
                )
            )

    print("Random seed done.")


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from kbeton.importers.utils import norm_counterparty_name
from kbeton.models.counterparty import CounterpartyBalance, CounterpartySnapshot
from kbeton.models.enums import ProductType, ShiftStatus, TxType
from kbeton.models.finance import FinanceArticle, FinanceTransaction
from kbeton.models.inventory import InventoryBalance, InventoryItem
from kbeton.models.production import ProductionOutput, ProductionRealization, ProductionShift


def _bar(value: float, max_value: float, width: int = 10) -> str:
    if max_value <= 0:
        return "░" * width
    filled = max(0, min(width, round((value / max_value) * width)))
    return ("█" * filled) + ("░" * (width - filled))


def _fmt_money(value: float | None) -> str:
    amount = float(value or 0)
    if abs(amount - round(amount)) < 0.005:
        body = f"{int(round(amount)):,}".replace(",", " ")
    else:
        body = f"{amount:,.2f}".replace(",", " ")
    return f"{body} сом"


def _fmt_qty(value: float | None, uom: str) -> str:
    qty = float(value or 0)
    if abs(qty - round(qty)) < 0.0005:
        body = str(int(round(qty)))
    else:
        body = f"{qty:.3f}".rstrip("0").rstrip(".")
    return f"{body} {uom}"


def _clip(value: str, size: int) -> str:
    value = (value or "").strip()
    if len(value) <= size:
        return value
    return value[: max(1, size - 1)] + "…"


def _boxed_header(title: str, subtitle: str) -> list[str]:
    width = max(len(title), len(subtitle), 24) + 4
    return [
        "╔" + ("═" * width) + "╗",
        "║" + title.center(width) + "║",
        "║" + subtitle.center(width) + "║",
        "╚" + ("═" * width) + "╝",
    ]


def _dashboard_section(title: str, icon: str, body_lines: list[str]) -> list[str]:
    lines = [f"┏━━ {icon} {title}"]
    if not body_lines:
        body_lines = ["нет данных"]
    for line in body_lines:
        lines.append("┃" if not line else f"┃ {line}")
    lines.append("┗" + ("━" * 30))
    return lines


def _product_type_label(value: ProductType | str) -> str:
    labels = {
        ProductType.crushed_stone: "Щебень",
        ProductType.screening: "Отсев",
        ProductType.sand: "Песок",
        ProductType.concrete: "Бетон",
        ProductType.blocks: "Блоки",
    }
    if isinstance(value, ProductType):
        return labels.get(value, value.value)
    try:
        enum_value = ProductType(value)
    except Exception:
        return str(value)
    return labels.get(enum_value, enum_value.value)


def _latest_counterparty_snapshot_map(session: Session) -> tuple[CounterpartySnapshot | None, dict[str, CounterpartyBalance]]:
    snap = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
    if not snap:
        return None, {}
    rows = session.query(CounterpartyBalance).filter(CounterpartyBalance.snapshot_id == snap.id).all()
    return snap, {r.counterparty_name_norm: r for r in rows}


def _channel_bucket(raw_value: str) -> str | None:
    value = (raw_value or "").strip().lower()
    if not value:
        return None
    if any(token in value for token in ["касса", "нал", "налич", "cash"]):
        return "cash"
    if any(token in value for token in ["банк", "р/с", "рс", "расчет", "расч", "безнал", "bank"]):
        return "bank"
    return None


def _dashboard_money_lines(session: Session, *, end: date) -> list[str]:
    rows = (
        session.query(
            FinanceTransaction.amount,
            FinanceTransaction.tx_type,
            FinanceTransaction.description,
            FinanceTransaction.raw_fields,
            FinanceArticle.name,
        )
        .outerjoin(
            FinanceArticle,
            or_(
                FinanceArticle.id == FinanceTransaction.income_article_id,
                FinanceArticle.id == FinanceTransaction.expense_article_id,
            ),
        )
        .filter(FinanceTransaction.date.is_not(None))
        .filter(FinanceTransaction.date <= end)
        .all()
    )

    totals = {"bank": 0.0, "cash": 0.0}
    seen = {"bank": False, "cash": False}

    for amount, tx_type, description, raw_fields, article_name in rows:
        bucket = None
        payload = raw_fields or {}
        if isinstance(payload, dict):
            for key in ["payment_channel", "account_type", "channel", "source_account", "wallet"]:
                bucket = _channel_bucket(str(payload.get(key, "")))
                if bucket:
                    break
        if not bucket:
            bucket = _channel_bucket(f"{article_name or ''} {description or ''}")
        if not bucket:
            continue

        sign = 1.0 if tx_type == TxType.income else -1.0 if tx_type == TxType.expense else 0.0
        totals[bucket] += sign * float(amount or 0)
        seen[bucket] = True

    lines = [
        f"Р/с      · {_fmt_money(totals['bank'])}" if seen["bank"] else "Р/с      · нет данных",
        f"Касса    · {_fmt_money(totals['cash'])}" if seen["cash"] else "Касса    · нет данных",
    ]
    if seen["bank"] or seen["cash"]:
        lines.append(f"Источник · операции до {end.strftime('%d.%m.%Y')}")
    return lines


def _dashboard_realization_lines(session: Session, *, start: date, end: date, cp_map: dict[str, CounterpartyBalance]) -> list[str]:
    rows = (
        session.query(
            ProductionShift.counterparty_name,
            ProductionOutput.product_type,
            ProductionOutput.mark,
            ProductionOutput.uom,
            ProductionRealization.realized_qty,
            ProductionRealization.total_amount,
        )
        .join(ProductionOutput, ProductionOutput.id == ProductionRealization.output_id)
        .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
        .filter(ProductionShift.date >= start, ProductionShift.date <= end)
        .order_by(ProductionRealization.id.desc())
        .limit(5)
        .all()
    )
    lines = ["РЕАЛИЗАЦИЯ"]
    if not rows:
        lines.append("- нет данных")
        return lines

    for idx, (counterparty_name, product_type, mark, uom, realized_qty, total_amount) in enumerate(rows):
        cp_name = (counterparty_name or "").strip()
        cp_norm = norm_counterparty_name(cp_name)
        cp_row = cp_map.get(cp_norm) if cp_norm else None
        if cp_row and float(cp_row.receivable_money or 0) > 0:
            status = f"долг {_fmt_money(cp_row.receivable_money)}"
        elif cp_row:
            status = "оплачено"
        else:
            status = "нет данных"
        product_name = _product_type_label(product_type)
        if product_type == ProductType.concrete and (mark or "").strip():
            product_name = (mark or "").strip()
        lines.append(f"◆ {_clip(cp_name or 'Без контрагента', 26)}")
        lines.append(f"  Марка   · {product_name}")
        lines.append(f"  Объем   · {_fmt_qty(realized_qty, uom)}")
        lines.append(f"  Сумма   · {_fmt_money(total_amount)}")
        lines.append(f"  Статус  · {status}")
        if idx != len(rows) - 1:
            lines.append("")
    return lines


def _dashboard_counterparty_lines(title: str, rows: list[tuple[str, float]]) -> list[str]:
    lines = [title]
    if not rows:
        lines.append("- нет данных")
        return lines
    max_amount = max((amount for _name, amount in rows[:5]), default=0)
    for name, amount in rows[:5]:
        lines.append(f"{_clip(name, 18):<18} {_bar(amount, max_amount, 8)} {_fmt_money(amount)}")
    return lines


def _dashboard_production_lines(session: Session, *, start: date, end: date) -> list[str]:
    rows = (
        session.query(ProductionOutput.product_type, ProductionOutput.mark, ProductionOutput.quantity, ProductionOutput.uom)
        .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
        .filter(ProductionShift.status == ShiftStatus.approved)
        .filter(ProductionShift.date >= start, ProductionShift.date <= end)
        .all()
    )
    lines = ["Производство:"]
    if not rows:
        lines.append("- нет данных")
        return lines

    totals: dict[tuple[str, str, str], float] = {}
    for product_type, mark, quantity, uom in rows:
        ptype = product_type.value if isinstance(product_type, ProductType) else str(product_type)
        key = (ptype, (mark or "").strip(), uom or "ед.")
        totals[key] = totals.get(key, 0.0) + float(quantity or 0)

    ordered: list[tuple[str, str, str]] = []
    for key in [
        (ProductType.concrete.value, "M350", "м3"),
        (ProductType.concrete.value, "M300", "м3"),
        (ProductType.concrete.value, "M250", "м3"),
        (ProductType.concrete.value, "M200", "м3"),
    ]:
        if key in totals:
            ordered.append(key)
    for ptype in [ProductType.crushed_stone.value, ProductType.screening.value, ProductType.sand.value, ProductType.blocks.value]:
        matching = [k for k in totals.keys() if k[0] == ptype]
        ordered.extend(sorted(matching))
    remaining = [k for k in totals.keys() if k not in ordered]
    ordered.extend(sorted(remaining))

    seen: set[tuple[str, str, str]] = set()
    max_qty = max(totals.values(), default=0)
    for ptype, mark, uom in ordered:
        key = (ptype, mark, uom)
        if key in seen:
            continue
        seen.add(key)
        qty = totals[key]
        label = _product_type_label(ptype)
        if ptype == ProductType.concrete.value and mark:
            label = mark
        lines.append(f"{_clip(label, 18):<18} {_bar(qty, max_qty, 8)} {_fmt_qty(qty, uom)}")
    return lines


def _dashboard_inventory_lines(session: Session) -> list[str]:
    rows = (
        session.query(InventoryItem.name, InventoryItem.uom, InventoryBalance.qty)
        .join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id)
        .filter(InventoryItem.is_active == True)
        .all()
    )
    lines = ["Склад:"]
    if not rows:
        lines.append("- нет данных")
        return lines

    labels = [
        ("Щебень", ("щебень",)),
        ("Отсев", ("отсев",)),
        ("Песок", ("песок",)),
        ("Цемент", ("цемент",)),
        ("Топливо", ("топливо", "дизель", "соляр")),
    ]
    selected: dict[str, tuple[str, float, str]] = {}
    for raw_name, uom, qty in rows:
        low = (raw_name or "").strip().lower()
        for label, tokens in labels:
            if label in selected:
                continue
            if any(token in low for token in tokens):
                selected[label] = (raw_name, float(qty or 0), uom or "ед.")
                break

    max_qty = max((float(value[1] or 0) for value in selected.values()), default=0)
    for label, _tokens in labels:
        item = selected.get(label)
        if item:
            _raw_name, qty, uom = item
            lines.append(f"{_clip(label, 18):<18} {_bar(qty, max_qty, 8)} {_fmt_qty(qty, uom)}")
        else:
            lines.append(f"{_clip(label, 18):<18} {'░' * 8} нет данных")
    return lines


def build_dashboard_text(session: Session, *, start: date, end: date) -> str:
    snap, cp_map = _latest_counterparty_snapshot_map(session)
    cp_rows = list(cp_map.values())
    debtors = sorted(
        ((r.counterparty_name, float(r.receivable_money or 0)) for r in cp_rows if float(r.receivable_money or 0) > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    creditors = sorted(
        ((r.counterparty_name, float(r.payable_money or 0)) for r in cp_rows if float(r.payable_money or 0) > 0),
        key=lambda x: x[1],
        reverse=True,
    )

    lines = _boxed_header("Д А Ш Б О Р Д", end.strftime("%d.%m.%Y"))
    money_lines = _dashboard_money_lines(session, end=end)
    if snap:
        money_lines.append(f"Снимок   · {snap.snapshot_date.strftime('%d.%m.%Y')}")
    lines.extend([""] + _dashboard_section("ДЕНЬГИ", "💰", money_lines))

    realization_lines = _dashboard_realization_lines(session, start=start, end=end, cp_map=cp_map)
    realization_body = ["нет данных"] if len(realization_lines) == 2 and realization_lines[1] == "- нет данных" else realization_lines[1:]
    lines.extend([""] + _dashboard_section(realization_lines[0], "🚚", realization_body))

    debt_lines = _dashboard_counterparty_lines("Д/З ЗАДОЛЖЕННОСТЬ", debtors)
    debt_body = ["нет данных"] if len(debt_lines) == 2 and debt_lines[1] == "- нет данных" else debt_lines[1:]
    lines.extend([""] + _dashboard_section(debt_lines[0], "📥", debt_body))

    credit_lines = _dashboard_counterparty_lines("К/З ЗАДОЛЖЕННОСТЬ", creditors)
    credit_body = ["нет данных"] if len(credit_lines) == 2 and credit_lines[1] == "- нет данных" else credit_lines[1:]
    lines.extend([""] + _dashboard_section(credit_lines[0], "📤", credit_body))

    prod_lines = _dashboard_production_lines(session, start=start, end=end)
    prod_body = ["нет данных"] if len(prod_lines) == 2 and prod_lines[1] == "- нет данных" else prod_lines[1:]
    lines.extend([""] + _dashboard_section(prod_lines[0].rstrip(":"), "🏭", prod_body))

    stock_lines = _dashboard_inventory_lines(session)
    stock_body = ["нет данных"] if len(stock_lines) == 2 and stock_lines[1] == "- нет данных" else stock_lines[1:]
    lines.extend([""] + _dashboard_section(stock_lines[0].rstrip(":"), "📦", stock_body))

    return "\n".join(lines)

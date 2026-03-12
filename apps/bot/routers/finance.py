from __future__ import annotations

import html
import uuid
from datetime import date, datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from kbeton.db.session import session_scope
from kbeton.models.enums import Role, TxType, PriceKind, PatternType, InventoryTxnType
from kbeton.models.costs import MaterialPrice, OverheadCost
from kbeton.models.recipes import ConcreteRecipe
from kbeton.models.finance import ImportJob, FinanceArticle, FinanceTransaction, MappingRule
from kbeton.models.counterparty import CounterpartySnapshot, CounterpartyBalance
from kbeton.models.production import ProductionShift, ProductionOutput, ProductionRealization
from kbeton.models.inventory import InventoryTxn, InventoryItem, InventoryBalance
from kbeton.models.enums import ShiftStatus, ProductType
from kbeton.services.s3 import put_bytes
from kbeton.services.audit import audit_log
from kbeton.services.pricing import set_price, get_current_prices
from kbeton.services.mapping import apply_article
from kbeton.services.manual_finance import create_manual_finance_tx
from kbeton.reports.pnl import pnl as pnl_calc
from kbeton.reports.export_xlsx import pnl_to_xlsx
from kbeton.importers.utils import norm_counterparty_name

from apps.bot.keyboards import (
    pnl_period_kb,
    articles_kb,
    yes_no_kb,
    finance_menu,
    material_price_kb,
    overhead_cost_kb,
    concrete_cost_mark_kb,
)
from apps.bot.states import (
    CounterpartyUploadState,
    CounterpartyCardState,
    CounterpartyAddState,
    RealizationState,
    ArticleAddState,
    PriceSetState,
    MappingRuleAddState,
    MaterialPriceState,
    OverheadCostState,
)
from apps.bot.utils import get_db_user, ensure_role

from apps.worker.celery_app import celery

router = Router()

MATERIAL_UNITS = {
    "цемент": "кг",
    "песок": "тн",
    "щебень": "тн",
    "отсев": "тн",
    "вода": "л",
    "добавки": "л",
}

PRODUCT_TYPE_RU = {
    ProductType.crushed_stone: "Щебень",
    ProductType.screening: "Отсев",
    ProductType.sand: "Песок",
    ProductType.concrete: "Бетон",
    ProductType.blocks: "Блоки",
}

DU_PRODUCT_TYPES = {ProductType.crushed_stone, ProductType.screening, ProductType.sand}

def _product_type_label(value: ProductType | str) -> str:
    if isinstance(value, ProductType):
        return PRODUCT_TYPE_RU.get(value, value.value)
    try:
        return PRODUCT_TYPE_RU.get(ProductType(value), str(value))
    except Exception:
        return str(value)

def _upsert_counterparty_registry_entry(name: str, actor_user_id: int | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    norm = norm_counterparty_name(cleaned)
    if not norm:
        return ""

    with session_scope() as session:
        snap = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
        if not snap:
            job = ImportJob(
                kind="counterparty",
                status="done",
                filename="manual_counterparty",
                s3_key="",
                created_by_user_id=actor_user_id,
                summary={"manual": True},
            )
            session.add(job)
            session.flush()
            snap = CounterpartySnapshot(snapshot_date=date.today(), import_job_id=job.id)
            session.add(snap)
            session.flush()

        existing = (
            session.query(CounterpartyBalance)
            .filter(CounterpartyBalance.snapshot_id == snap.id)
            .filter(CounterpartyBalance.counterparty_name_norm == norm)
            .one_or_none()
        )
        if existing:
            return existing.counterparty_name

        session.add(
            CounterpartyBalance(
                snapshot_id=snap.id,
                counterparty_name=cleaned,
                counterparty_name_norm=norm,
                receivable_money=0,
                receivable_assets="",
                payable_money=0,
                payable_assets="",
                ending_balance_money=0,
            )
        )
        audit_log(
            session,
            actor_user_id=actor_user_id,
            action="counterparty_manual_add",
            entity_type="counterparty_snapshot",
            entity_id=str(snap.id),
            payload={"name": cleaned, "name_norm": norm},
        )
    return cleaned

def _parse_float(value: str) -> float | None:
    try:
        return float((value or "").strip().replace(",", "."))
    except ValueError:
        return None

def _latest_material_prices(session) -> dict:
    rows = (
        session.query(MaterialPrice)
        .order_by(MaterialPrice.valid_from.desc(), MaterialPrice.id.desc())
        .all()
    )
    seen = set()
    out = {}
    for r in rows:
        key = (r.item_key or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out[key] = r
    return out

def _latest_overheads(session) -> dict:
    rows = (
        session.query(OverheadCost)
        .order_by(OverheadCost.valid_from.desc(), OverheadCost.id.desc())
        .all()
    )
    seen = set()
    out = {}
    for r in rows:
        key = (r.name or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out[key] = r
    return out

def _calc_recipe_cost(recipe: ConcreteRecipe, prices: dict, overheads: dict) -> tuple[float, list[str]]:
    missing = []
    total = 0.0
    def _add(item: str, qty: float):
        nonlocal total
        if qty <= 0:
            return
        p = prices.get(item)
        if not p:
            missing.append(item)
            return
        total += float(p.price) * qty
    _add("цемент", float(recipe.cement_kg or 0))
    _add("песок", float(recipe.sand_t or 0))
    _add("щебень", float(recipe.crushed_stone_t or 0))
    _add("отсев", float(recipe.screening_t or 0))
    _add("вода", float(recipe.water_l or 0))
    _add("добавки", float(recipe.additives_l or 0))
    for _, oh in overheads.items():
        total += float(oh.cost_per_m3 or 0)
    return total, missing

def _range_for(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "day":
        return today, today
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "month":
        return date(today.year, today.month, 1), today
    if period == "quarter":
        q = (today.month - 1)//3
        m = q*3 + 1
        return date(today.year, m, 1), today
    if period == "year":
        return date(today.year, 1, 1), today
    return today, today

def _bar(value: float, max_value: float, width: int = 10) -> str:
    if max_value <= 0:
        return "░" * width
    filled = max(0, min(width, round((value / max_value) * width)))
    return ("█" * filled) + ("░" * (width - filled))

def _production_dashboard_summary(session, *, start: date, end: date) -> list[str]:
    rows = (
        session.query(ProductionShift.date, ProductionOutput.product_type, ProductionOutput.mark, ProductionOutput.quantity)
        .join(ProductionOutput, ProductionOutput.shift_id == ProductionShift.id)
        .filter(ProductionShift.status == ShiftStatus.approved)
        .filter(ProductionShift.date >= start, ProductionShift.date <= end)
        .all()
    )
    if not rows:
        return ["🏭 Производство", "Нет данных за период."]

    totals: dict[str, float] = {}
    concrete_marks: dict[str, float] = {}
    last7_start = end - timedelta(days=6)
    daily_concrete: dict[date, float] = {last7_start + timedelta(days=i): 0.0 for i in range(7)}

    for row_date, product_type, mark, qty in rows:
        qty_f = float(qty or 0)
        if product_type == ProductType.concrete:
            concrete_marks[mark or "-"] = concrete_marks.get(mark or "-", 0.0) + qty_f
            if row_date in daily_concrete:
                daily_concrete[row_date] += qty_f
        else:
            key = product_type.value
            totals[key] = totals.get(key, 0.0) + qty_f

    lines = ["🏭 Производство"]
    labels = {
        "crushed_stone": ("Щебень", "тн"),
        "screening": ("Отсев", "тн"),
        "sand": ("Песок", "тн"),
        "blocks": ("Блоки", "шт"),
    }
    has_any = False
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in totals and totals[key] > 0:
            label, uom = labels[key]
            lines.append(f"{label}: {totals[key]:.2f} {uom}")
            has_any = True

    if concrete_marks:
        has_any = True
        total_concrete = sum(concrete_marks.values())
        lines.append(f"Бетон (всего): {total_concrete:.2f} м3")
        top_marks = sorted(concrete_marks.items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("Марки (топ):")
        max_mark = max((v for _, v in top_marks), default=0.0)
        for mark_name, qty in top_marks:
            lines.append(f"{mark_name}: {_bar(qty, max_mark, 8)} {qty:.1f}")

        lines.append("Бетон за 7 дней:")
        max_day = max(daily_concrete.values()) if daily_concrete else 0.0
        for d in sorted(daily_concrete.keys()):
            qty = daily_concrete[d]
            lines.append(f"{d.strftime('%d.%m')}: {_bar(qty, max_day, 8)} {qty:.1f}")

    real_rows = (
        session.query(ProductionOutput.mark, ProductionRealization.realized_qty, ProductionRealization.total_amount)
        .join(ProductionOutput, ProductionOutput.id == ProductionRealization.output_id)
        .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
        .filter(ProductionShift.date >= start, ProductionShift.date <= end)
        .all()
    )
    if real_rows:
        total_real_amount = sum(float(r.total_amount or 0) for r in real_rows)
        total_real_qty = sum(float(r.realized_qty or 0) for r in real_rows)
        lines.append(f"Реализация: {total_real_qty:.2f} ед. | {total_real_amount:.2f} KGS")
        by_mark: dict[str, float] = {}
        for mark, qty, _amt in real_rows:
            by_mark[(mark or "-")] = by_mark.get((mark or "-"), 0.0) + float(qty or 0)
        top_real = sorted(by_mark.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_real:
            lines.append("Реализовано (топ):")
            max_real = max((v for _, v in top_real), default=0.0)
            for mark_name, qty in top_real:
                lines.append(f"{mark_name}: {_bar(qty, max_real, 8)} {qty:.1f}")

    if not has_any:
        lines.append("Нет подтвержденного выпуска за период.")
    return lines

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

def _kv_line(label: str, value: str, width: int = 22) -> str:
    return f"{_clip(label, width):<{width}} {value}"

def _amount_line(label: str, amount: float, width: int = 22) -> str:
    return f"{_clip(label, width):.<{width}} {_fmt_money(amount)}"

def _latest_counterparty_snapshot_map(session) -> tuple[CounterpartySnapshot | None, dict[str, CounterpartyBalance]]:
    snap = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
    if not snap:
        return None, {}
    rows = session.query(CounterpartyBalance).filter(CounterpartyBalance.snapshot_id == snap.id).all()
    return snap, {r.counterparty_name_norm: r for r in rows}

def _dashboard_realization_lines(session, *, start: date, end: date, cp_map: dict[str, CounterpartyBalance]) -> list[str]:
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
        lines.append(f"▪ {_clip(cp_name or 'Без контрагента', 28)}")
        lines.append(f"  марка:  {product_name}")
        lines.append(f"  объем:  {_fmt_qty(realized_qty, uom)}")
        lines.append(f"  сумма:  {_fmt_money(total_amount)}")
        lines.append(f"  статус: {status}")
        if idx != len(rows) - 1:
            lines.append("")
    return lines

def _dashboard_counterparty_lines(title: str, rows: list[tuple[str, float]]) -> list[str]:
    lines = [title]
    if not rows:
        lines.append("- нет данных")
        return lines
    for name, amount in rows[:5]:
        lines.append(f"▪ {_clip(name, 24)}")
        lines.append(f"  {_fmt_money(amount)}")
    return lines

def _dashboard_production_lines(session, *, start: date, end: date) -> list[str]:
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
    for ptype, mark, uom in ordered:
        key = (ptype, mark, uom)
        if key in seen:
            continue
        seen.add(key)
        qty = totals[key]
        label = _product_type_label(ptype)
        if ptype == ProductType.concrete.value and mark:
            label = mark
        lines.append(f"▪ {_kv_line(label, _fmt_qty(qty, uom))}")
    return lines

def _dashboard_inventory_lines(session) -> list[str]:
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

    for label, _tokens in labels:
        item = selected.get(label)
        if item:
            _raw_name, qty, uom = item
            lines.append(f"▪ {_kv_line(label, _fmt_qty(qty, uom))}")
        else:
            lines.append(f"▪ {_kv_line(label, 'нет данных')}")
    return lines

def _build_dashboard_text(session, *, start: date, end: date) -> str:
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

    lines = [
        "▌ ДАШБОРД",
        f"  {end.strftime('%d.%m.%Y')}",
        "",
        "◾ ДЕНЬГИ",
        f"  Р/с:   нет данных",
        f"  Касса: нет данных",
    ]
    if snap:
        lines.append(f"  Снимок взаиморасчетов: {snap.snapshot_date.strftime('%d.%m.%Y')}")

    realization_lines = _dashboard_realization_lines(session, start=start, end=end, cp_map=cp_map)
    lines.extend(["", f"◾ {realization_lines[0]}"])
    if len(realization_lines) == 2 and realization_lines[1] == "- нет данных":
        lines.append("  нет данных")
    else:
        for line in realization_lines[1:]:
            lines.append(line if not line else f"  {line}")

    debt_lines = _dashboard_counterparty_lines("Д/З ЗАДОЛЖЕННОСТЬ", debtors)
    lines.extend(["", f"◾ {debt_lines[0]}"])
    for line in debt_lines[1:]:
        if line == "- нет данных":
            lines.append("  нет данных")
        else:
            lines.append(f"  {line}")

    credit_lines = _dashboard_counterparty_lines("К/З ЗАДОЛЖЕННОСТЬ", creditors)
    lines.extend(["", f"◾ {credit_lines[0]}"])
    for line in credit_lines[1:]:
        if line == "- нет данных":
            lines.append("  нет данных")
        else:
            lines.append(f"  {line}")

    prod_lines = _dashboard_production_lines(session, start=start, end=end)
    lines.extend(["", f"◾ {prod_lines[0].rstrip(':')}"])
    for line in prod_lines[1:]:
        if line == "- нет данных":
            lines.append("  нет данных")
        else:
            lines.append(f"  {line}")

    stock_lines = _dashboard_inventory_lines(session)
    lines.extend(["", f"◾ {stock_lines[0].rstrip(':')}"])
    for line in stock_lines[1:]:
        if line == "- нет данных":
            lines.append("  нет данных")
        else:
            lines.append(f"  {line}")

    return "\n".join(lines)

def _realization_candidates(session):
    outputs = (
        session.query(ProductionOutput, ProductionShift)
        .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
        .filter(ProductionShift.status == ShiftStatus.approved)
        .order_by(ProductionShift.date.desc(), ProductionOutput.id.desc())
        .limit(120)
        .all()
    )
    realized_rows = (
        session.query(ProductionRealization.output_id, ProductionRealization.realized_qty)
        .all()
    )
    realized_map: dict[int, float] = {}
    for output_id, qty in realized_rows:
        realized_map[int(output_id)] = realized_map.get(int(output_id), 0.0) + float(qty or 0)

    candidates = []
    for out, shift in outputs:
        if out.product_type in DU_PRODUCT_TYPES:
            # Выпуск ДУ (щебень/отсев/песок) не отправляем в финансовую "Реализацию".
            continue
        produced = float(out.quantity or 0)
        realized = realized_map.get(out.id, 0.0)
        remaining = round(produced - realized, 3)
        if remaining <= 0:
            continue
        ptype_ru = _product_type_label(out.product_type)
        label = f"{shift.date.isoformat()} | смена {shift.id} | {ptype_ru} {out.mark or ''}".strip()
        candidates.append({
            "output_id": out.id,
            "shift_id": shift.id,
            "date": shift.date,
            "product_type": ptype_ru,
            "product_type_code": out.product_type.value,
            "mark": out.mark or "",
            "uom": out.uom,
            "produced_qty": produced,
            "realized_qty": realized,
            "remaining_qty": remaining,
            "counterparty_name": (shift.counterparty_name or "").strip(),
            "label": label,
        })
    return candidates

def _realization_item_caption(c: dict) -> str:
    product_name = f"{c['product_type']} {c['mark'] or ''}".strip()
    lines = [
        f"Дата выпуска: {c['date'].isoformat()}",
        f"Смена: #{c['shift_id']}",
        f"Продукция: {product_name}",
        f"Выпуск: {c['produced_qty']:.3f} {c['uom']}",
        f"Уже реализовано: {c['realized_qty']:.3f} {c['uom']}",
        f"Доступно к реализации: {c['remaining_qty']:.3f} {c['uom']}",
    ]
    if c.get("counterparty_name"):
        lines.append(f"Контрагент (из смены): {c['counterparty_name']}")
    return "\n".join(lines)

def _realization_preview_text(meta: dict, qty: float, unit_price: float) -> str:
    uom = meta.get("uom") or "ед."
    product_name = f"{meta.get('product_type', '')} {meta.get('mark', '')}".strip()
    total_amount = round(qty * unit_price, 2)
    dt = meta.get("date")
    dt_txt = dt.isoformat() if dt else "-"
    return (
        "Проверьте данные перед сохранением:\n\n"
        f"Продукция: {product_name or '-'}\n"
        f"Смена: #{meta.get('shift_id', '-')}\n"
        f"Дата выпуска: {dt_txt}\n"
        f"Объем реализации: {qty:.3f} {uom}\n"
        f"Цена за единицу: {unit_price:.2f} KGS/{uom}\n"
        f"Сумма реализации: {total_amount:.2f} KGS"
    )

def _pending_expense_receipts(session):
    rows = (
        session.query(InventoryTxn, InventoryItem)
        .join(InventoryItem, InventoryItem.id == InventoryTxn.item_id)
        .filter(InventoryTxn.txn_type == InventoryTxnType.receipt)
        .filter(InventoryTxn.total_cost.isnot(None))
        .filter(InventoryTxn.total_cost > 0)
        .filter(InventoryTxn.finance_approval_required == True)
        .filter(InventoryTxn.finance_txn_id.is_(None))
        .order_by(InventoryTxn.id.desc())
        .limit(30)
        .all()
    )
    result = []
    for txn, item in rows:
        result.append({
            "txn_id": txn.id,
            "item_id": item.id,
            "item_name": item.name,
            "uom": item.uom,
            "qty": float(txn.qty or 0),
            "unit_price": float(txn.unit_price or 0),
            "total_cost": float(txn.total_cost or 0),
            "fact_weight": float(txn.fact_weight or 0),
            "comment": txn.comment or "",
            "invoice_photo_s3_key": txn.invoice_photo_s3_key or "",
            "created_at": txn.created_at,
        })
    return result

def _pending_expense_caption(row: dict) -> str:
    created = row.get("created_at")
    created_txt = created.strftime("%d.%m %H:%M") if created else "-"
    lines = [
        f"Заявка на расход #{row['txn_id']}",
        f"Материал: {row['item_name']}",
        f"Объем: {row['qty']:.3f} {row['uom']}",
        f"Цена: {row['unit_price']:.2f} KGS/{row['uom']}",
        f"Сумма: {row['total_cost']:.2f} KGS",
        f"Факт вес: {row['fact_weight']:.3f}",
        f"Дата прихода: {created_txt}",
    ]
    if row.get("comment"):
        lines.append(f"Комментарий: {row['comment']}")
    if row.get("invoice_photo_s3_key"):
        lines.append("Накладная: фото сохранено")
    return "\n".join(lines)

def _pnl_payload(period: str):
    start, end = _range_for(period)
    with session_scope() as session:
        rows, meta = pnl_calc(session, start=start, end=end, period=period)
        xlsx = pnl_to_xlsx(rows, period=period, start=start, end=end, totals=meta)
    text = (
        f"📈 P&L ({period})\n"
        f"Период: {start.isoformat()} → {end.isoformat()}\n"
        f"Доход: {meta['total_income']:.2f}\n"
        f"Расход: {meta['total_expense']:.2f}\n"
        f"Чистая прибыль: {meta['total_net']:.2f}\n"
        f"Неразобранное: {meta.get('unknown_count', 0)}"
    )
    top_inc = meta.get("top_income_articles", [])[:3]
    top_exp = meta.get("top_expense_articles", [])[:3]
    if top_inc:
        lines = ["\nТОП доходы:"]
        for r in top_inc:
            lines.append(f"- {r['name']}: {float(r['amount']):.2f}")
        text += "\n" + "\n".join(lines)
    if top_exp:
        lines = ["\nТОП расходы:"]
        for r in top_exp:
            lines.append(f"- {r['name']}: {float(r['amount']):.2f}")
        text += "\n" + "\n".join(lines)
    caption = f"P&L {period} {start.isoformat()}-{end.isoformat()}"
    return text, xlsx, caption

@router.message(F.text == "📥 Загрузить взаиморасчеты (контрагенты)")
async def cp_upload_prompt(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    await state.set_state(CounterpartyUploadState.waiting_file)
    await message.answer("Отправьте XLSX снимок взаиморасчетов (контрагенты).")

@router.message(CounterpartyUploadState.waiting_file, F.document)
async def cp_upload_handle(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})

    doc = message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        await message.answer("Нужен файл .xlsx")
        return
    file = await message.bot.get_file(doc.file_id)
    b = await message.bot.download_file(file.file_path)
    content = b.read()

    key = f"imports/counterparty/{uuid.uuid4().hex}_{doc.file_name}"
    put_bytes(key, content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with session_scope() as session:
        job = ImportJob(kind="counterparty", status="pending", filename=doc.file_name, s3_key=key, created_by_user_id=user.id)
        session.add(job)
        session.flush()
        audit_log(session, actor_user_id=user.id, action="counterparty_import_created", entity_type="import_job", entity_id=str(job.id), payload={"filename": doc.file_name, "s3_key": key})
        job_id = job.id

    celery.send_task("apps.worker.tasks.process_counterparty_import", args=[job_id])
    await state.clear()
    await message.answer(f"✅ Импорт контрагентов создан. job_id={job_id}.", reply_markup=finance_menu(user.role))

@router.message(CounterpartyUploadState.waiting_file)
async def cp_upload_waiting(message: Message, **data):
    await message.answer("Пожалуйста, отправьте XLSX как файл (document) или напишите 'отмена'.")

@router.message(F.text == "📦 Статус импорта")
async def import_status(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        jobs = (
            session.query(ImportJob)
            .order_by(ImportJob.id.desc())
            .limit(10)
            .all()
        )
    if not jobs:
        await message.answer("Импортов пока нет.")
        return
    lines = ["📦 Последние импорты (до 10):"]
    for j in jobs:
        status = j.status
        summary = j.summary or {}
        err = j.error or ""
        parts = [f"#{j.id} {j.kind} — {status}"]
        if j.filename:
            parts.append(f"файл: {j.filename}")
        if summary:
            parts.append(f"итог: {summary}")
        if err:
            parts.append(f"ошибка: {err}")
        lines.append(" | ".join(parts))
    await message.answer("\n".join(lines))

@router.message(F.text == "➕ Добавить контрагента")
async def counterparty_add_prompt(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    await state.set_state(CounterpartyAddState.waiting_name)
    await message.answer("Введите название контрагента для добавления в реестр.")

@router.message(CounterpartyAddState.waiting_name)
async def counterparty_add_save(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    raw_name = (message.text or "").strip()
    if raw_name.lower() == "отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    if len(raw_name) < 2:
        await message.answer("Название слишком короткое. Введите корректное название контрагента.")
        return
    saved_name = _upsert_counterparty_registry_entry(raw_name, user.id)
    if not saved_name:
        await message.answer("Не удалось сохранить контрагента. Попробуйте еще раз.")
        return
    await state.clear()
    await message.answer(f"✅ Контрагент добавлен: {saved_name}", reply_markup=finance_menu(user.role))

@router.message(F.text == "💸 Реализация")
async def realization_menu(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        candidates = _realization_candidates(session)
        audit_log(session, actor_user_id=user.id, action="realization_candidates_view", entity_type="production_output", entity_id="", payload={"count": len(candidates)})
    if not candidates:
        await message.answer(
            "💸 Реализация\n\n"
            "Нет доступных позиций для продажи.\n"
            "Позиции появятся после согласования смены производства."
        )
        return
    b = InlineKeyboardBuilder()
    lines = [
        "💸 Реализация",
        "",
        "Выберите позицию из согласованного выпуска.",
        "Показываются только позиции с остатком к реализации.",
        f"Доступно позиций: {len(candidates)}",
        "",
        "Список (первые 20):",
    ]
    for c in candidates[:20]:
        text = f"{c['date'].isoformat()} | смена #{c['shift_id']} | {c['product_type']} {c['mark'] or '-'} | остаток {c['remaining_qty']:.3f} {c['uom']}"
        if c["counterparty_name"]:
            text += f" | {c['counterparty_name']}"
        lines.append(f"- {text}")
        button_text = f"Смена #{c['shift_id']} • {c['mark'] or c['product_type']} • {c['remaining_qty']:.1f} {c['uom']}"
        b.button(text=button_text[:64], callback_data=f"realize_pick:{c['output_id']}")
    b.adjust(1)
    await message.answer("\n".join(lines), reply_markup=b.as_markup())

@router.message(F.text == "✅ Согласование расходов")
async def expense_approval_menu(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        rows = _pending_expense_receipts(session)
        audit_log(
            session,
            actor_user_id=user.id,
            action="inventory_expense_approval_queue_view",
            entity_type="inventory_txn",
            entity_id="",
            payload={"count": len(rows)},
        )
    if not rows:
        await message.answer(
            "✅ Согласование расходов\n\n"
            "Нет заявок на согласование.\n"
            "Они появятся после складского прихода с ценой/суммой."
        )
        return
    b = InlineKeyboardBuilder()
    lines = [
        "✅ Согласование расходов",
        "",
        "Ниже заявки из склада (приходы), которые еще не проведены в P&L.",
        f"Ожидает согласования: {len(rows)}",
        "",
        "Список (первые 30):",
    ]
    for r in rows:
        lines.append(
            f"- #{r['txn_id']} {r['item_name']}: {r['qty']:.3f} {r['uom']} × {r['unit_price']:.2f} = {r['total_cost']:.2f} KGS"
        )
        b.button(
            text=f"#{r['txn_id']} {r['item_name']} • {r['total_cost']:.0f} KGS"[:64],
            callback_data=f"invexp_pick:{r['txn_id']}",
        )
    b.adjust(1)
    await message.answer("\n".join(lines), reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("invexp_pick:"))
async def expense_approval_pick(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    txn_id = int(call.data.split(":")[1])
    with session_scope() as session:
        rows = _pending_expense_receipts(session)
    selected = next((r for r in rows if r["txn_id"] == txn_id), None)
    if not selected:
        await call.message.answer("Заявка уже согласована или не найдена.")
        await call.answer()
        return
    b = InlineKeyboardBuilder()
    b.button(text="✅ Согласовать расход", callback_data=f"invexp_approve:{txn_id}")
    b.button(text="↩️ К списку", callback_data="invexp_back:list")
    b.adjust(1)
    await call.message.answer(_pending_expense_caption(selected), reply_markup=b.as_markup())
    await call.answer()

@router.callback_query(F.data == "invexp_back:list")
async def expense_approval_back_list(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    await call.answer()
    await expense_approval_menu(call.message, **data)

@router.callback_query(F.data.startswith("invexp_approve:"))
async def expense_approval_approve(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    txn_id = int(call.data.split(":")[1])
    with session_scope() as session:
        row = (
            session.query(InventoryTxn, InventoryItem)
            .join(InventoryItem, InventoryItem.id == InventoryTxn.item_id)
            .filter(InventoryTxn.id == txn_id)
            .one_or_none()
        )
        if row is None:
            await call.message.answer("Заявка не найдена.")
            await call.answer()
            return
        txn, item = row
        if txn.txn_type != InventoryTxnType.receipt:
            await call.message.answer("Это не заявка на приход.")
            await call.answer()
            return
        if txn.finance_txn_id is not None:
            await call.message.answer("Эта заявка уже согласована и проведена в P&L.")
            await call.answer()
            return
        total_cost = float(txn.total_cost or 0)
        if total_cost <= 0:
            await call.message.answer("У заявки нет суммы расхода для проведения.")
            await call.answer()
            return

        fin_tx = create_manual_finance_tx(
            session,
            tx_date=datetime.now().date(),
            amount=total_cost,
            tx_type=TxType.expense,
            description=f"Склад приход (согласован): {item.name}",
            counterparty="",
            actor_user_id=user.id,
            article_name="Закупка материалов (склад)",
            raw_fields={
                "source": "inventory_receipt_approved",
                "inventory_txn_id": txn.id,
                "inventory_item_id": item.id,
                "qty": float(txn.qty or 0),
                "unit_price": float(txn.unit_price or 0),
                "total_cost": total_cost,
                "fact_weight": float(txn.fact_weight or 0),
            },
        )
        txn.finance_txn_id = fin_tx.id
        txn.finance_approval_required = False
        txn.expense_approved_by_user_id = user.id
        txn.expense_approved_at = datetime.now().astimezone()
        audit_log(
            session,
            actor_user_id=user.id,
            action="inventory_expense_approved",
            entity_type="inventory_txn",
            entity_id=str(txn.id),
            payload={"finance_txn_id": fin_tx.id, "total_cost": total_cost},
        )
        item_name = item.name
        qty = float(txn.qty or 0)
        uom = item.uom
        unit_price = float(txn.unit_price or 0)

    await call.message.answer(
        "✅ Расход согласован и проведен в P&L\n"
        f"Материал: {item_name}\n"
        f"Объем: {qty:.3f} {uom}\n"
        f"Цена: {unit_price:.2f} KGS/{uom}\n"
        f"Сумма: {total_cost:.2f} KGS",
        reply_markup=finance_menu(user.role),
    )
    await call.answer()

@router.callback_query(F.data.startswith("realize_pick:"))
async def realization_pick(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    output_id = int(call.data.split(":")[1])
    with session_scope() as session:
        candidates = _realization_candidates(session)
    selected = next((c for c in candidates if c["output_id"] == output_id), None)
    if not selected:
        await call.message.answer("Эта позиция уже полностью реализована или не найдена.")
        await call.answer()
        return
    await state.update_data(realize_output_id=output_id, realize_meta=selected)
    await state.set_state(RealizationState.waiting_qty)
    await call.message.answer(
        "Вы выбрали позицию для реализации:\n\n"
        f"{_realization_item_caption(selected)}\n\n"
        f"Шаг 1/2: Введите объем реализации в {selected['uom']}.\n"
        "Пример: 12.5"
    )
    await call.answer()

@router.message(RealizationState.waiting_qty)
async def realization_qty(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (объем реализации).")
        return
    st = await state.get_data()
    meta = st.get("realize_meta") or {}
    remaining = float(meta.get("remaining_qty") or 0)
    if qty <= 0:
        await message.answer("Объем должен быть больше 0.")
        return
    if remaining and qty > remaining:
        await message.answer(
            f"Нельзя больше доступного остатка: {remaining:.3f} {meta.get('uom') or ''}\n"
            "Введите меньшее значение."
        )
        return
    await state.update_data(realize_qty=qty)
    await state.set_state(RealizationState.waiting_unit_price)
    await message.answer(
        f"Шаг 2/2: Введите цену реализации за 1 {meta.get('uom') or 'ед.'} (KGS).\n"
        "Пример: 4200"
    )

@router.message(RealizationState.waiting_unit_price)
async def realization_price(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    try:
        unit_price = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (цена за единицу).")
        return
    if unit_price <= 0:
        await message.answer("Цена должна быть больше 0.")
        return
    st = await state.get_data()
    meta = st.get("realize_meta") or {}
    qty = float(st["realize_qty"])
    total_amount = round(qty * unit_price, 2)
    await state.update_data(realize_unit_price=unit_price, realize_total_amount=total_amount)
    await state.set_state(RealizationState.waiting_confirm)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Сохранить реализацию", callback_data="realize_confirm:save")
    b.button(text="✏️ Изменить цену", callback_data="realize_confirm:edit_price")
    b.button(text="↩️ Изменить объем", callback_data="realize_confirm:edit_qty")
    b.button(text="❌ Отмена", callback_data="realize_confirm:cancel")
    b.adjust(1, 2, 1)
    await message.answer(_realization_preview_text(meta, qty, unit_price), reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("realize_confirm:"))
async def realization_confirm_action(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    action = (call.data or "").split(":", 1)[1]
    st = await state.get_data()

    if action == "cancel":
        await state.clear()
        await call.message.answer("Реализация отменена.", reply_markup=finance_menu(user.role))
        await call.answer()
        return
    if action == "edit_qty":
        meta = st.get("realize_meta") or {}
        await state.set_state(RealizationState.waiting_qty)
        await call.message.answer(
            f"Введите новый объем реализации (доступно: {float(meta.get('remaining_qty') or 0):.3f} {meta.get('uom') or ''})."
        )
        await call.answer()
        return
    if action == "edit_price":
        meta = st.get("realize_meta") or {}
        await state.set_state(RealizationState.waiting_unit_price)
        await call.message.answer(f"Введите новую цену за 1 {meta.get('uom') or 'ед.'} (KGS).")
        await call.answer()
        return
    if action != "save":
        await call.answer()
        return

    try:
        output_id = int(st["realize_output_id"])
        qty = float(st["realize_qty"])
        unit_price = float(st["realize_unit_price"])
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await call.message.answer(
            "Сессия реализации устарела. Откройте `💸 Реализация` заново.",
            reply_markup=finance_menu(user.role),
        )
        await call.answer()
        return

    total_amount = round(qty * unit_price, 2)
    with session_scope() as session:
        out = session.query(ProductionOutput).filter(ProductionOutput.id == output_id).one()
        shift = session.query(ProductionShift).filter(ProductionShift.id == out.shift_id).one()
        product_type_ru = _product_type_label(out.product_type)
        already_realized = sum(
            float(r.realized_qty or 0)
            for r in session.query(ProductionRealization).filter(ProductionRealization.output_id == out.id).all()
        )
        remaining_now = float(out.quantity or 0) - already_realized
        if qty > round(remaining_now, 6):
            await state.clear()
            await call.message.answer(
                f"Позиция изменилась. Доступно сейчас: {remaining_now:.3f} {out.uom}. Откройте `💸 Реализация` заново.",
                reply_markup=finance_menu(user.role),
            )
            await call.answer()
            return
        fin_tx = create_manual_finance_tx(
            session,
            tx_date=date.today(),
            amount=total_amount,
            tx_type=TxType.income,
            description=f"Реализация: {product_type_ru} {out.mark or ''} / смена {shift.id}",
            counterparty=(shift.counterparty_name or "").strip(),
            actor_user_id=user.id,
            article_name="Реализация продукции",
            raw_fields={"source": "production_realization", "output_id": out.id, "shift_id": shift.id, "qty": qty, "unit_price": unit_price},
        )
        real = ProductionRealization(
            output_id=out.id,
            realized_qty=qty,
            unit_price=unit_price,
            total_amount=total_amount,
            finance_txn_id=fin_tx.id,
            created_by_user_id=user.id,
        )
        session.add(real)
        session.flush()
        audit_log(session, actor_user_id=user.id, action="production_realized", entity_type="production_realization", entity_id=str(real.id), payload={"output_id": out.id, "qty": qty, "unit_price": unit_price, "total_amount": total_amount})
        uom = out.uom
        product_label = f"{product_type_ru} {out.mark or ''}".strip()
    await state.clear()
    await call.message.answer(
        f"✅ Реализация сохранена\n"
        f"{product_label}: {qty:.3f} {uom}\n"
        f"Цена: {unit_price:.3f} KGS/{uom}\n"
        f"Сумма: {total_amount:.2f} KGS\n\n"
        "Сумма добавлена в финансы и попадет в P&L/дашборд.",
        reply_markup=finance_menu(user.role),
    )
    await call.answer()

@router.message(F.text == "📄 P&L")
async def pnl_prompt(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    await message.answer("Выберите период:", reply_markup=pnl_period_kb())

@router.message(Command("today"))
async def pnl_today(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    text, xlsx, caption = _pnl_payload("day")
    await message.answer(text)
    await message.answer_document(document=BufferedInputFile(xlsx, filename="pnl.xlsx"), caption=caption)
    with session_scope() as session:
        audit_log(session, actor_user_id=user.id, action="pnl_view", entity_type="pnl", entity_id="day", payload={"period": "day"})

@router.message(Command("week"))
async def pnl_week(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    text, xlsx, caption = _pnl_payload("week")
    await message.answer(text)
    await message.answer_document(document=BufferedInputFile(xlsx, filename="pnl.xlsx"), caption=caption)
    with session_scope() as session:
        audit_log(session, actor_user_id=user.id, action="pnl_view", entity_type="pnl", entity_id="week", payload={"period": "week"})

@router.message(Command("month"))
async def pnl_month(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    text, xlsx, caption = _pnl_payload("month")
    await message.answer(text)
    await message.answer_document(document=BufferedInputFile(xlsx, filename="pnl.xlsx"), caption=caption)
    with session_scope() as session:
        audit_log(session, actor_user_id=user.id, action="pnl_view", entity_type="pnl", entity_id="month", payload={"period": "month"})

@router.callback_query(F.data.startswith("pnl:"))
async def pnl_show(call: CallbackQuery, **data):
    user = get_db_user(data, call)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    period = call.data.split(":", 1)[1]
    text, xlsx, caption = _pnl_payload(period)
    await call.message.answer(text)
    await call.message.answer_document(
        document=BufferedInputFile(xlsx, filename="pnl.xlsx"),
        caption=caption,
    )
    await call.answer()
    with session_scope() as session:
        audit_log(session, actor_user_id=user.id, action="pnl_view", entity_type="pnl", entity_id=period, payload={"period": period})

@router.message(F.text == "🧾 Статьи доходов")
async def income_articles(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    await state.update_data(article_kind="income")
    await state.set_state(ArticleAddState.waiting_name)
    with session_scope() as session:
        arts = session.query(FinanceArticle).filter(FinanceArticle.kind == TxType.income).order_by(FinanceArticle.name.asc()).all()
        lines = ["🧾 Статьи доходов:"]
        for a in arts[:50]:
            lines.append(f"- {a.name}")
    lines.append("\nНапишите *название новой статьи* одним сообщением (или отправьте 'отмена' / /cancel).")
    await message.answer("\n".join(lines))

@router.message(F.text == "🧾 Статьи расходов")
async def expense_articles(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    await state.update_data(article_kind="expense")
    await state.set_state(ArticleAddState.waiting_name)
    with session_scope() as session:
        arts = session.query(FinanceArticle).filter(FinanceArticle.kind == TxType.expense).order_by(FinanceArticle.name.asc()).all()
        lines = ["🧾 Статьи расходов:"]
        for a in arts[:50]:
            lines.append(f"- {a.name}")
    lines.append("\nНапишите *название новой статьи* одним сообщением (или отправьте 'отмена' / /cancel).")
    await message.answer("\n".join(lines))

@router.message(F.text == "📐 Правила маппинга")
async def rules_menu(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        rules = (
            session.query(MappingRule, FinanceArticle)
            .join(FinanceArticle, FinanceArticle.id == MappingRule.article_id)
            .order_by(MappingRule.id.desc())
            .limit(10)
            .all()
        )
        audit_log(session, actor_user_id=user.id, action="mapping_rules_view", entity_type="mapping_rule", entity_id="", payload={"count": len(rules)})
    lines = ["📐 Правила маппинга (последние 10):"]
    for r, art in rules:
        lines.append(f"- {r.id}: {r.kind.value}/{r.pattern_type.value} prio={r.priority} '{r.pattern}' → {art.name}")
    lines.append("\nЧтобы добавить правило, отправьте строку:")
    lines.append("kind;pattern_type;pattern;priority;article_id")
    lines.append("пример: expense;regex;^цемент;100;12")
    lines.append("или: income;contains;бетон;50;Продажи бетона")
    await state.set_state(MappingRuleAddState.waiting_rule)
    await message.answer("\n".join(lines))

@router.message(MappingRuleAddState.waiting_rule)
async def rules_add(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    text = (message.text or "").strip()
    if text.lower() == "отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    parts = [p.strip() for p in text.split(";")]
    if len(parts) < 5:
        await message.answer("Неверный формат. Пример: expense;regex;^цемент;100;12")
        return
    kind_s, ptype_s, pattern, prio_s, article_ref = parts[0], parts[1], parts[2], parts[3], ";".join(parts[4:])
    try:
        kind = TxType(kind_s)
    except Exception:
        await message.answer("kind должен быть income или expense.")
        return
    try:
        ptype = PatternType(ptype_s)
    except Exception:
        await message.answer("pattern_type должен быть contains или regex.")
        return
    try:
        priority = int(prio_s)
    except ValueError:
        await message.answer("priority должен быть числом.")
        return
    with session_scope() as session:
        art = None
        if article_ref.isdigit():
            art = session.query(FinanceArticle).filter(FinanceArticle.id == int(article_ref)).one_or_none()
        if not art:
            art = session.query(FinanceArticle).filter(FinanceArticle.name == article_ref).one_or_none()
        if not art:
            await message.answer("article_id/название не найдено.")
            return
        rule = MappingRule(kind=kind, pattern_type=ptype, pattern=pattern, priority=priority, is_active=True, article_id=art.id, created_by_user_id=user.id)
        session.add(rule)
        session.flush()
        audit_log(session, actor_user_id=user.id, action="mapping_rule_add", entity_type="mapping_rule", entity_id=str(rule.id), payload={"kind": kind.value, "pattern_type": ptype.value, "pattern": pattern, "priority": priority, "article_id": art.id})
    await state.clear()
    await message.answer(f"✅ Правило добавлено: {rule.id}", reply_markup=finance_menu(user.role))

@router.message(ArticleAddState.waiting_name)
async def add_article(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    if (message.text or "").strip().lower() == "отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пустое название. Повторите или 'отмена' / /cancel.")
        return
    st = await state.get_data()
    kind = TxType.income if st.get("article_kind") == "income" else TxType.expense
    with session_scope() as session:
        art = FinanceArticle(kind=kind, name=name, is_active=True)
        session.add(art)
        session.flush()
        audit_log(session, actor_user_id=user.id, action="article_add", entity_type="finance_article", entity_id=str(art.id), payload={"kind": kind.value, "name": name})
    await state.clear()
    await message.answer(f"✅ Добавлено: {name}", reply_markup=finance_menu(user.role))

@router.message(F.text == "🧩 Неразобранное")
async def unclassified(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        txs = session.query(FinanceTransaction).filter(FinanceTransaction.tx_type == TxType.unknown).order_by(FinanceTransaction.id.desc()).limit(5).all()
        income_arts = session.query(FinanceArticle).filter(FinanceArticle.kind == TxType.income).order_by(FinanceArticle.name.asc()).all()
        expense_arts = session.query(FinanceArticle).filter(FinanceArticle.kind == TxType.expense).order_by(FinanceArticle.name.asc()).all()
        audit_log(session, actor_user_id=user.id, action="unclassified_view", entity_type="finance_transaction", entity_id="", payload={"count": len(txs)})
    if not txs:
        await message.answer("✅ Неразобранных строк нет.")
        return
    for tx in txs:
        text = f"ID {tx.id} | {tx.date} | {float(tx.amount):.2f} {tx.currency}\n{(tx.description or '')[:200]}\nКонтрагент: {tx.counterparty}"
        # choose kind first
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="Доход → выбрать статью", callback_data=f"pickkind:{tx.id}:income")
        b.button(text="Расход → выбрать статью", callback_data=f"pickkind:{tx.id}:expense")
        b.adjust(1)
        await message.answer(text, reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("pickkind:"))
async def pick_kind(call: CallbackQuery, **data):
    user = get_db_user(data, call)
    ensure_role(user, {Role.Admin, Role.FinDir})
    _, txid, kind = call.data.split(":")
    txid = int(txid)
    kind_enum = TxType.income if kind == "income" else TxType.expense
    with session_scope() as session:
        arts = session.query(FinanceArticle).filter(FinanceArticle.kind == kind_enum).order_by(FinanceArticle.name.asc()).all()
        pairs = [(a.id, a.name) for a in arts]
    if not pairs:
        await call.message.answer("Сначала добавьте статьи в этом разделе.")
        await call.answer()
        return
    await call.message.answer("Выберите статью:", reply_markup=articles_kb(pairs, prefix=f"assign:{txid}:{kind}"))
    await call.answer()

@router.callback_query(F.data.startswith("assign:"))
async def assign_article(call: CallbackQuery, **data):
    user = get_db_user(data, call)
    ensure_role(user, {Role.Admin, Role.FinDir})
    # assign:TXID:kind:ARTICLEID
    _, txid, kind, aid = call.data.split(":")
    txid = int(txid)
    aid = int(aid)
    kind_enum = TxType.income if kind == "income" else TxType.expense

    with session_scope() as session:
        tx = session.query(FinanceTransaction).filter(FinanceTransaction.id == txid).one()
        income_article_id, expense_article_id = apply_article(session, tx_type=kind_enum, article_id=aid)
        tx.tx_type = kind_enum
        tx.income_article_id = income_article_id
        tx.expense_article_id = expense_article_id
        audit_log(session, actor_user_id=user.id, action="txn_assign_article", entity_type="finance_transaction", entity_id=str(tx.id), payload={"kind": kind_enum.value, "article_id": aid})
        desc = tx.description or ""
    await call.message.answer("✅ Назначено. Создать правило маппинга (contains) автоматически?", reply_markup=yes_no_kb(prefix=f"mk_rule:{txid}:{kind}:{aid}"))
    await call.answer()

@router.callback_query(F.data.startswith("mk_rule:"))
async def make_rule(call: CallbackQuery, **data):
    user = get_db_user(data, call)
    ensure_role(user, {Role.Admin, Role.FinDir})
    # mk_rule:TXID:kind:aid:yes/no
    parts = call.data.split(":")
    txid = int(parts[1])
    kind = parts[2]
    aid = int(parts[3])
    answer = parts[4]
    if answer == "no":
        await call.message.answer("Ок, без правила.")
        await call.answer()
        return
    kind_enum = TxType.income if kind == "income" else TxType.expense
    with session_scope() as session:
        tx = session.query(FinanceTransaction).filter(FinanceTransaction.id == txid).one()
        # Auto pattern: first 24 chars of description normalized
        pattern = (tx.description or "").strip()
        if len(pattern) > 24:
            pattern = pattern[:24]
        pattern = pattern.lower()
        if not pattern:
            pattern = (tx.counterparty or "").strip().lower()[:24]
        if not pattern:
            await call.message.answer("Не удалось сформировать паттерн (пустое описание).")
            await call.answer()
            return
        rule = MappingRule(kind=kind_enum, pattern_type=PatternType.contains, pattern=pattern, priority=100, is_active=True, article_id=aid, created_by_user_id=user.id)
        session.add(rule)
        session.flush()
        audit_log(session, actor_user_id=user.id, action="mapping_rule_add", entity_type="mapping_rule", entity_id=str(rule.id), payload={"kind": kind_enum.value, "pattern": pattern, "article_id": aid})
    await call.message.answer(f"✅ Правило добавлено: contains '{pattern}' → {kind_enum.value} (article_id={aid})")
    await call.answer()

@router.message(F.text == "🏷️ Цены")
async def prices_menu(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        cur = get_current_prices(session)
    lines = ["🏷️ Текущие цены:"]
    for p in cur["prices"]:
        lines.append(f"- {p['kind']} {p['item_key']}: {p['price']} {p['currency']} (с {p['valid_from']})")
    lines.append("\nЧтобы обновить: отправьте одной строкой:")
    lines.append("БЕТОН:  M300=4500, M350=4800")
    lines.append("БЛОКИ:  blocks=120")
    lines.append("Я применю valid_from=сейчас (без согласования).")
    await state.set_state(PriceSetState.waiting_price)
    await message.answer("\n".join(lines))

def _parse_price_line(line: str) -> list[tuple[PriceKind, str, float]]:
    # returns list of (kind, item_key, price)
    out = []
    s = (line or "").strip()
    # split by comma
    parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
        elif ":" in p:
            k, v = p.split(":", 1)
        elif "-" in p and p.count("-") == 1 and " " not in p:
            k, v = p.split("-", 1)
        else:
            # allow 'M300 4500'
            ss = p.split()
            if len(ss) != 2:
                continue
            k, v = ss[0], ss[1]
        k = k.strip()
        v = v.strip().replace(" ", "").replace(",", ".")
        try:
            price = float(v)
        except ValueError:
            continue
        if k.lower() in ("blocks", "block", "блок", "блоки"):
            out.append((PriceKind.blocks, "blocks", price))
        else:
            # concrete mark
            out.append((PriceKind.concrete, k.upper(), price))
    return out

@router.message(PriceSetState.waiting_price)
async def prices_set(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    if (message.text or "").strip().lower() == "отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    items = _parse_price_line(message.text or "")
    if not items:
        await message.answer("Не распознал. Пример: M300=4500, M350=4800 или blocks=120. Или 'отмена' / /cancel.")
        return
    now = datetime.now().astimezone()
    with session_scope() as session:
        for kind, key, price in items:
            pv = set_price(session, kind=kind, item_key=key, price=price, currency="KGS", valid_from=now, changed_by_user_id=user.id, comment="bot update")
            audit_log(session, actor_user_id=user.id, action="price_set", entity_type="price_version", entity_id=str(pv.id), payload={"kind": kind.value, "item_key": key, "price": price})
    await state.clear()
    await message.answer("✅ Цены обновлены.", reply_markup=finance_menu(user.role))

@router.message(F.text == "🧾 Цены материалов")
async def material_prices_menu(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        cur = _latest_material_prices(session)
    lines = ["🧾 Цены материалов (текущие):"]
    for key in ["цемент", "песок", "щебень", "отсев", "вода", "добавки"]:
        p = cur.get(key)
        if p:
            lines.append(f"- {key}: {float(p.price):.3f} {p.currency}/{p.unit} (с {p.valid_from.isoformat()})")
        else:
            lines.append(f"- {key}: не задано")
    lines.append("\nВыберите материал для обновления:")
    await state.set_state(MaterialPriceState.waiting_item)
    await message.answer("\n".join(lines), reply_markup=material_price_kb())

@router.message(MaterialPriceState.waiting_item)
async def material_price_item(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    t = (message.text or "").strip().lower()
    if t in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    if t not in MATERIAL_UNITS:
        await message.answer("Выберите материал кнопкой.", reply_markup=material_price_kb())
        return
    await state.update_data(item_key=t)
    await state.set_state(MaterialPriceState.waiting_price)
    await message.answer(f"Цена за {MATERIAL_UNITS[t]} (KGS):")

@router.message(MaterialPriceState.waiting_price)
async def material_price_value(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число.")
        return
    st = await state.get_data()
    key = st.get("item_key")
    now = datetime.now().astimezone()
    with session_scope() as session:
        mp = MaterialPrice(
            item_key=key,
            unit=MATERIAL_UNITS[key],
            price=qty,
            currency="KGS",
            valid_from=now,
            changed_by_user_id=user.id,
        )
        session.add(mp)
        audit_log(session, actor_user_id=user.id, action="material_price_set", entity_type="material_price", entity_id=str(mp.id or 0), payload={"item_key": key, "price": qty})
    await state.clear()
    await message.answer("✅ Цена материала обновлена.", reply_markup=finance_menu(user.role))

@router.message(F.text == "⚙️ Накладные на 1м3")
async def overhead_menu(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    with session_scope() as session:
        cur = _latest_overheads(session)
    lines = ["⚙️ Накладные на 1 м3 (текущие):"]
    for key in ["энергия", "амортизация"]:
        p = cur.get(key)
        if p:
            lines.append(f"- {key}: {float(p.cost_per_m3):.3f} {p.currency}/м3 (с {p.valid_from.isoformat()})")
        else:
            lines.append(f"- {key}: не задано")
    lines.append("\nВыберите статью накладных:")
    await state.set_state(OverheadCostState.waiting_name)
    await message.answer("\n".join(lines), reply_markup=overhead_cost_kb())

@router.message(OverheadCostState.waiting_name)
async def overhead_name(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    t = (message.text or "").strip().lower()
    if t in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    if t not in ("энергия", "амортизация"):
        await message.answer("Выберите статью кнопкой.", reply_markup=overhead_cost_kb())
        return
    await state.update_data(name=t)
    await state.set_state(OverheadCostState.waiting_cost)
    await message.answer("Сумма на 1 м3 (KGS):")

@router.message(OverheadCostState.waiting_cost)
async def overhead_cost_value(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir})
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число.")
        return
    st = await state.get_data()
    name = st.get("name")
    now = datetime.now().astimezone()
    with session_scope() as session:
        oh = OverheadCost(
            name=name,
            cost_per_m3=qty,
            currency="KGS",
            valid_from=now,
            changed_by_user_id=user.id,
        )
        session.add(oh)
        audit_log(session, actor_user_id=user.id, action="overhead_cost_set", entity_type="overhead_cost", entity_id=str(oh.id or 0), payload={"name": name, "cost": qty})
    await state.clear()
    await message.answer("✅ Накладные обновлены.", reply_markup=finance_menu(user.role))

@router.message(F.text == "📊 Себестоимость бетона")
async def concrete_cost_report(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    with session_scope() as session:
        recipes = session.query(ConcreteRecipe).filter(ConcreteRecipe.is_active == True).order_by(ConcreteRecipe.mark.asc()).all()
        prices = _latest_material_prices(session)
        overheads = _latest_overheads(session)
    if not recipes:
        await message.answer("Нет активных рецептур. Добавьте в '🧪 Рецептуры бетона'.")
        return
    lines = ["📊 Себестоимость бетона (на 1 м3):"]
    total_sum = 0.0
    count = 0
    missing_any = []
    for r in recipes:
        cost, missing = _calc_recipe_cost(r, prices, overheads)
        if missing:
            missing_any.append(f"{r.mark}: нет цены для {', '.join(sorted(set(missing)))}")
            continue
        lines.append(f"- {r.mark}: {cost:.3f} KGS/м3")
        total_sum += cost
        count += 1
    if count > 0:
        lines.append(f"Средняя по всем маркам: {(total_sum / count):.3f} KGS/м3")
    if missing_any:
        lines.append("⚠️ Нет цен для расчета:")
        for m in missing_any[:10]:
            lines.append(f"- {m}")
    await message.answer("\n".join(lines))

@router.message(F.text == "📊 Дашборд")
async def dashboard_quick(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    start, end = _range_for("month")
    with session_scope() as session:
        text = _build_dashboard_text(session, start=start, end=end)
        audit_log(session, actor_user_id=user.id, action="dashboard_view", entity_type="pnl", entity_id="month", payload={"period": "month"})
    await message.answer(f"<pre>{html.escape(text)}</pre>", parse_mode="HTML")

@router.message(F.text == "Контрагенты/Задолженность (снимки)")
async def cp_report(message: Message, state: FSMContext, **data):
    # not in keyboard by default; kept for compatibility
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    await cp_summary(message, state)

@router.message(F.text.contains("Контрагенты"))
async def cp_summary(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    with session_scope() as session:
        snap = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
        if not snap:
            await message.answer("Нет снимков. Загрузите XLSX взаиморасчетов.")
            return
        rows = session.query(CounterpartyBalance).filter(CounterpartyBalance.snapshot_id == snap.id).all()
        audit_log(session, actor_user_id=user.id, action="counterparty_summary_view", entity_type="counterparty_snapshot", entity_id=str(snap.id), payload={})
    # top debtors / creditors
    debtors = sorted(rows, key=lambda r: float(r.receivable_money), reverse=True)[:10]
    creditors = sorted(rows, key=lambda r: float(r.payable_money), reverse=True)[:10]
    assets_recv = [r.receivable_assets for r in rows if (r.receivable_assets or "").strip()]
    assets_pay = [r.payable_assets for r in rows if (r.payable_assets or "").strip()]
    def _group_assets(items):
        m = {}
        for it in items:
            key = it.strip().lower()
            m[key] = m.get(key, 0) + 1
        return sorted(m.items(), key=lambda x: x[1], reverse=True)[:10]
    recv_g = _group_assets(assets_recv)
    pay_g = _group_assets(assets_pay)

    lines = [f"🤝 Контрагенты (последний снимок: {snap.snapshot_date.isoformat()})"]
    lines.append("\nТОП должники (нам должны деньги):")
    for r in debtors:
        lines.append(f"- {r.counterparty_name}: {float(r.receivable_money):.2f}")
    lines.append("\nТОП кредиторы (мы должны деньги):")
    for r in creditors:
        lines.append(f"- {r.counterparty_name}: {float(r.payable_money):.2f}")
    lines.append("\nАктивы нам должны (топ):")
    for a, cnt in recv_g:
        lines.append(f"- {a} ×{cnt}")
    lines.append("\nАктивы мы должны (топ):")
    for a, cnt in pay_g:
        lines.append(f"- {a} ×{cnt}")
    await message.answer("\n".join(lines))
    await message.answer("Чтобы открыть карточку контрагента, отправьте его название (или 'отмена').")
    await state.set_state(CounterpartyCardState.waiting_name)

@router.message(CounterpartyCardState.waiting_name)
async def cp_card(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    text = (message.text or "").strip()
    if text.lower() == "отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=finance_menu(user.role))
        return
    q = norm_counterparty_name(text)
    if not q:
        await message.answer("Введите название контрагента или 'отмена'.")
        return
    with session_scope() as session:
        snap = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
        if not snap:
            await message.answer("Нет снимков. Загрузите XLSX взаиморасчетов.")
            await state.clear()
            return
        matches = (
            session.query(CounterpartyBalance)
            .filter(CounterpartyBalance.snapshot_id == snap.id)
            .filter(CounterpartyBalance.counterparty_name_norm.ilike(f"%{q}%"))
            .limit(5)
            .all()
        )
        audit_log(session, actor_user_id=user.id, action="counterparty_card_view", entity_type="counterparty_snapshot", entity_id=str(snap.id), payload={"query": q, "count": len(matches)})
    if not matches:
        await message.answer("Не найдено. Попробуйте другое название или 'отмена'.")
        return
    if len(matches) > 1:
        names = "\n".join([f"- {m.counterparty_name}" for m in matches])
        await message.answer(f"Найдено несколько:\n{names}\nУточните название.")
        return
    m = matches[0]
    msg = (
        f"👤 Контрагент: {m.counterparty_name}\n"
        f"Нам должны (деньги): {float(m.receivable_money):.2f}\n"
        f"Нам должны (активы): {m.receivable_assets or '-'}\n"
        f"Мы должны (деньги): {float(m.payable_money):.2f}\n"
        f"Мы должны (активы): {m.payable_assets or '-'}\n"
        f"Сальдо конечное (денежное): {float(m.ending_balance_money):.2f}"
    )
    await state.clear()
    await message.answer(msg, reply_markup=finance_menu(user.role))

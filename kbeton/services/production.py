from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re

from sqlalchemy.orm import Session

from kbeton.db.session import session_scope
from kbeton.models.counterparty import CounterpartyBalance, CounterpartySnapshot
from kbeton.models.enums import (
    InventoryTxnType,
    PriceKind,
    ProductType,
    ShiftStatus,
    ShiftType,
)
from kbeton.models.inventory import InventoryBalance, InventoryItem, InventoryTxn
from kbeton.models.pricing import PriceVersion
from kbeton.models.production import ProductionOutput, ProductionShift
from kbeton.models.recipes import ConcreteRecipe
from kbeton.services.audit import audit_log


@dataclass(slots=True)
class ShiftApprovalResult:
    shift_id: int
    approved: bool
    errors: list[str]
    warnings: list[str]
    notes: list[str]
    low_balance_lines: list[str]


def parse_concrete(line: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    s = (line or "").strip()
    if not s:
        return out
    pattern = re.compile(r"([^\s=,:;]+)\s*(?:=|:|\s)\s*([0-9]+(?:[.,][0-9]+)?)")
    for key, value in pattern.findall(s):
        key = key.strip().upper()
        try:
            qty = float(value.strip().replace(",", "."))
        except ValueError:
            continue
        out.append((key, qty))
    return out


def get_concrete_marks() -> list[str]:
    with session_scope() as session:
        recipe_rows = (
            session.query(ConcreteRecipe)
            .filter(ConcreteRecipe.is_active == True)
            .order_by(ConcreteRecipe.mark.asc())
            .all()
        )
        if recipe_rows:
            return [row.mark for row in recipe_rows]
        rows = (
            session.query(PriceVersion)
            .filter(PriceVersion.kind == PriceKind.concrete)
            .order_by(PriceVersion.valid_from.desc(), PriceVersion.id.desc())
            .all()
        )
    seen: set[str] = set()
    marks: list[str] = []
    for row in rows:
        key = (row.item_key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        marks.append(key)
    return marks


def build_shift_summary(state: dict) -> list[str]:
    shift_type = "день" if state.get("shift_type") == "day" else "ночь"
    line_type = state.get("line_type", "")
    line = "ДУ" if line_type == "du" else "РБУ"
    lines = [
        f"Смена: {shift_type}",
        f"Линия: {line}",
    ]
    equipment = state.get("equipment", "")
    area = state.get("area", "")
    if equipment:
        lines.append(f"Оборудование: {equipment}")
    if area:
        lines.append(f"Площадка: {area}")
    if line_type == "du":
        lines.append(f"Щебень: {float(state.get('crushed', 0)):.3f} тн")
        lines.append(f"Отсев: {float(state.get('screening', 0)):.3f} тн")
        lines.append(f"Песок: {float(state.get('sand', 0)):.3f} тн")
    elif line_type == "rbu":
        counterparty_name = (state.get("counterparty_name") or "").strip()
        lines.append(f"Контрагент: {counterparty_name or '-'}")
        concrete = state.get("concrete", [])
        if concrete:
            lines.append("Бетон по маркам (м3):")
            for mark, qty in concrete:
                lines.append(f"- {mark}: {float(qty):.3f}")
        else:
            lines.append("Бетон: нет")
    comment = (state.get("comment") or "").strip()
    lines.append(f"Комментарий: {comment or '-'}")
    return lines


def line_label(line_type: str) -> str:
    return "ДУ" if line_type == "du" else "РБУ"


def shift_line_from_outputs(outputs: list[ProductionOutput]) -> str:
    for output in outputs:
        if output.product_type == ProductType.concrete:
            return "rbu"
    return "du"


def build_shift_summary_from_shift(shift: ProductionShift) -> list[str]:
    line_type = shift_line_from_outputs(shift.outputs)
    shift_type = "день" if shift.shift_type == ShiftType.day else "ночь"
    lines = [
        f"Смена: {shift_type}",
        f"Линия: {line_label(line_type)}",
    ]
    if shift.equipment:
        lines.append(f"Оборудование: {shift.equipment}")
    if shift.area:
        lines.append(f"Площадка: {shift.area}")
    if line_type == "rbu":
        lines.append(f"Контрагент: {(shift.counterparty_name or '').strip() or '-'}")
    outputs: dict[str, float] = {}
    concrete: dict[str, float] = {}
    for output in shift.outputs:
        if output.product_type == ProductType.concrete:
            concrete[output.mark or "-"] = concrete.get(output.mark or "-", 0.0) + float(output.quantity or 0)
        else:
            outputs[output.product_type.value] = outputs.get(output.product_type.value, 0.0) + float(output.quantity or 0)
    labels = {
        "crushed_stone": "Щебень",
        "screening": "Отсев",
        "sand": "Песок",
        "blocks": "Блоки",
    }
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in outputs:
            uom = "тн" if key in ("crushed_stone", "screening", "sand") else "шт"
            lines.append(f"{labels[key]}: {outputs[key]:.3f} {uom}")
    if concrete:
        lines.append("Бетон по маркам (м3):")
        for mark, qty in sorted(concrete.items()):
            lines.append(f"- {mark}: {qty:.3f}")
    comment = (shift.comment or "").strip()
    lines.append(f"Комментарий: {comment or '-'}")
    return lines


def build_pending_shift_lines(shift: ProductionShift) -> list[str]:
    outputs: dict[str, float] = {}
    concrete: dict[str, float] = {}
    for output in shift.outputs:
        if output.product_type == ProductType.concrete:
            concrete[output.mark or "-"] = concrete.get(output.mark or "-", 0.0) + float(output.quantity or 0)
        else:
            outputs[output.product_type.value] = outputs.get(output.product_type.value, 0.0) + float(output.quantity or 0)
    lines = [
        f"ID={shift.id} | {shift.date} | {shift.shift_type.value}",
        f"Оборудование: {shift.equipment}",
        f"Площадка: {shift.area}",
    ]
    if (shift.counterparty_name or "").strip():
        lines.append(f"Контрагент: {shift.counterparty_name}")
    labels = {
        "crushed_stone": "Щебень",
        "screening": "Отсев",
        "sand": "Песок",
        "blocks": "Блоки",
    }
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in outputs:
            uom = "тн" if key in ("crushed_stone", "screening", "sand") else "шт"
            lines.append(f"{labels[key]}: {outputs[key]:.3f} {uom}")
    if concrete:
        lines.append("Бетон по маркам (м3):")
        for mark, qty in sorted(concrete.items()):
            lines.append(f"- {mark}: {qty:.3f}")
    lines.append(f"Комментарий: {(shift.comment or '-')[:200]}")
    return lines


def report_period_bounds(period: str) -> tuple[date, date, str]:
    today = date.today()
    if period == "day":
        return today, today, "день"
    if period == "week":
        return today - timedelta(days=6), today, "7 дней"
    return today - timedelta(days=29), today, "30 дней"


def get_shift_report_data(
    session: Session,
    *,
    start: date,
    end: date,
    line: str,
    operator_id: int | None,
) -> tuple[list[ProductionShift], dict]:
    query = session.query(ProductionShift).filter(
        ProductionShift.status == ShiftStatus.approved,
        ProductionShift.date >= start,
        ProductionShift.date <= end,
    )
    if operator_id:
        query = query.filter(ProductionShift.operator_user_id == operator_id)
    shifts = query.order_by(ProductionShift.date.desc(), ProductionShift.id.desc()).all()
    visible_shifts: list[ProductionShift] = []
    totals: dict[str, float] = {}
    concrete: dict[str, float] = {}
    for shift in shifts:
        line_type = shift_line_from_outputs(shift.outputs)
        if line != "all" and line_type != line:
            continue
        for output in shift.outputs:
            if output.product_type == ProductType.concrete:
                key = output.mark or "-"
                concrete[key] = concrete.get(key, 0.0) + float(output.quantity or 0)
            else:
                totals[output.product_type.value] = totals.get(output.product_type.value, 0.0) + float(output.quantity or 0)
        visible_shifts.append(shift)
    meta = {"totals": totals, "concrete": concrete, "count": len(visible_shifts)}
    return visible_shifts, meta


def get_counterparty_registry() -> list[str]:
    with session_scope() as session:
        snapshot = session.query(CounterpartySnapshot).order_by(CounterpartySnapshot.id.desc()).first()
        if not snapshot:
            return []
        rows = (
            session.query(CounterpartyBalance.counterparty_name)
            .filter(CounterpartyBalance.snapshot_id == snapshot.id)
            .order_by(CounterpartyBalance.counterparty_name.asc())
            .all()
        )
    seen: set[str] = set()
    names: list[str] = []
    for (name,) in rows:
        value = (name or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        names.append(value)
    return names


def _apply_balance(session: Session, *, item_id: int, delta: float) -> None:
    balance = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one_or_none()
    if not balance:
        balance = InventoryBalance(item_id=item_id, qty=0)
        session.add(balance)
        session.flush()
    balance.qty = float(balance.qty) + float(delta)


def auto_writeoff_concrete(
    session: Session,
    shift: ProductionShift,
    actor_user_id: int,
) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    outputs = [output for output in shift.outputs if output.product_type == ProductType.concrete]
    if not outputs:
        return errors, warnings, notes

    item_map = {item.name.strip().lower(): item for item in session.query(InventoryItem).all()}
    name_map = {
        "цемент": "cement_kg",
        "песок": "sand_t",
        "щебень": "crushed_stone_t",
        "отсев": "screening_t",
    }
    required_items = {name: item_map.get(name) for name in name_map}

    totals = {name: 0.0 for name in name_map}
    for output in outputs:
        mark = (output.mark or "").strip()
        recipe = (
            session.query(ConcreteRecipe)
            .filter(ConcreteRecipe.mark == mark, ConcreteRecipe.is_active == True)
            .one_or_none()
        )
        if recipe is None:
            errors.append(f"Нет активной рецептуры для марки {mark}.")
            continue
        qty_m3 = float(output.quantity or 0)
        totals["цемент"] += float(recipe.cement_kg or 0) * qty_m3
        totals["песок"] += float(recipe.sand_t or 0) * qty_m3
        totals["щебень"] += float(recipe.crushed_stone_t or 0) * qty_m3
        totals["отсев"] += float(recipe.screening_t or 0) * qty_m3

    for name, total in totals.items():
        if total <= 0:
            continue
        item = required_items.get(name)
        if not item:
            errors.append(f"Нет расходника '{name}' в справочнике склада.")
            continue
        balance = session.query(InventoryBalance).filter(InventoryBalance.item_id == item.id).one_or_none()
        available = float(balance.qty) if balance else 0.0
        if available < total:
            errors.append(
                f"Недостаточно '{item.name}': нужно {total:.3f} {item.uom}, "
                f"остаток {available:.3f} {item.uom}."
            )

    if errors:
        return errors, warnings, notes

    for name, total in totals.items():
        if total <= 0:
            continue
        item = required_items.get(name)
        if not item:
            continue
        session.add(
            InventoryTxn(
                item_id=item.id,
                txn_type=InventoryTxnType.writeoff,
                qty=abs(total),
                receiver="РБУ",
                department="Производство",
                comment=f"Автосписание по смене {shift.id}",
                created_by_user_id=actor_user_id,
            )
        )
        _apply_balance(session, item_id=item.id, delta=-abs(total))
        notes.append(f"{item.name}: -{total:.3f} {item.uom}")

    return errors, warnings, notes


def collect_low_balance_lines(session: Session, *, limit: int = 10) -> list[str]:
    rows = (
        session.query(InventoryItem, InventoryBalance)
        .join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id)
        .filter(InventoryItem.is_active == True)
        .all()
    )
    lines: list[str] = []
    for item, balance in rows:
        if float(balance.qty) <= float(item.min_qty):
            lines.append(
                f"{item.name}: {float(balance.qty):.3f} {item.uom} "
                f"(мин {float(item.min_qty):.3f})"
            )
    return lines[:limit]


def approve_shift(session: Session, *, shift_id: int, actor_user_id: int) -> ShiftApprovalResult:
    shift = session.query(ProductionShift).filter(ProductionShift.id == shift_id).one()
    errors, warnings, notes = auto_writeoff_concrete(session, shift, actor_user_id)
    approved = False
    if errors:
        audit_log(
            session,
            actor_user_id=actor_user_id,
            action="shift_approve_blocked",
            entity_type="production_shift",
            entity_id=str(shift.id),
            payload={"errors": errors},
        )
    else:
        shift.status = ShiftStatus.approved
        shift.approved_by_user_id = actor_user_id
        shift.approved_at = datetime.now().astimezone()
        shift.approval_comment = ""
        audit_log(
            session,
            actor_user_id=actor_user_id,
            action="shift_approved",
            entity_type="production_shift",
            entity_id=str(shift.id),
            payload={},
        )
        approved = True
    return ShiftApprovalResult(
        shift_id=shift.id,
        approved=approved,
        errors=errors,
        warnings=warnings,
        notes=notes,
        low_balance_lines=collect_low_balance_lines(session),
    )

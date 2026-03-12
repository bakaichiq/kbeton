from __future__ import annotations

import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from kbeton.db.session import session_scope
from kbeton.models.enums import Role, InventoryTxnType
from kbeton.models.inventory import InventoryItem, InventoryBalance, InventoryTxn
from kbeton.services.audit import audit_log
from kbeton.services.s3 import put_bytes

from apps.bot.states import InventoryTxnState, InventoryAdjustState
from apps.bot.keyboards import pager_kb
from apps.bot.ui import list_text, section_text, wizard_text
from apps.bot.utils import get_db_user, ensure_role

router = Router()
BALANCES_PAGE_SIZE = 12

def _items_kb(items: list[InventoryItem], action: str):
    b = InlineKeyboardBuilder()
    for it in items[:30]:
        b.button(text=f"{it.name} ({it.uom})", callback_data=f"inv_item:{action}:{it.id}")
    b.adjust(1)
    return b.as_markup()

def _apply_balance(session, item_id: int, delta: float):
    bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one_or_none()
    if not bal:
        bal = InventoryBalance(item_id=item_id, qty=0)
        session.add(bal)
        session.flush()
    bal.qty = float(bal.qty) + float(delta)


def _balances_page_payload(page: int) -> tuple[str, object]:
    safe_page = max(0, page)
    with session_scope() as session:
        total = (
            session.query(InventoryItem)
            .join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id)
            .count()
        )
        total_pages = max(1, (total + BALANCES_PAGE_SIZE - 1) // BALANCES_PAGE_SIZE)
        safe_page = min(safe_page, total_pages - 1)
        rows = (
            session.query(InventoryItem, InventoryBalance)
            .join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id)
            .order_by(InventoryItem.name.asc())
            .offset(safe_page * BALANCES_PAGE_SIZE)
            .limit(BALANCES_PAGE_SIZE)
            .all()
        )
    body_lines = []
    for item, balance in rows:
        flag = "⚠️ " if float(balance.qty) <= float(item.min_qty) else ""
        body_lines.append(
            f"{flag}{item.name}: {float(balance.qty):.3f} {item.uom} "
            f"(мин {float(item.min_qty):.3f})"
        )
    text = list_text(
        "Остатки склада",
        body_lines,
        page=safe_page,
        total_pages=total_pages,
        total_items=total,
        icon="📦",
        hint="⚠️ означает остаток ниже минимума.",
    )
    markup = pager_kb("inv_balances", safe_page, total_pages) if total_pages > 1 else None
    return text, markup

@router.message(F.text == "📤 Выдать расходник")
async def issue_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    with session_scope() as session:
        items = session.query(InventoryItem).filter(InventoryItem.is_active == True).order_by(InventoryItem.name.asc()).all()
    if not items:
        await message.answer("Нет номенклатуры расходников. Попросите Admin добавить в '⚙️ Настройки/справочники'.")
        return
    await state.set_state(InventoryTxnState.waiting_item)
    await state.update_data(inv_action="issue")
    await message.answer(wizard_text("Выдача расходника", step=1, total=4, body_lines=["Выберите расходник."]), reply_markup=_items_kb(items, action="issue"))

@router.message(F.text == "📥 Приход")
async def receipt_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    with session_scope() as session:
        items = session.query(InventoryItem).filter(InventoryItem.is_active == True).order_by(InventoryItem.name.asc()).all()
    if not items:
        await message.answer("Нет номенклатуры расходников. Попросите Admin добавить в '⚙️ Настройки/справочники'.")
        return
    await state.set_state(InventoryTxnState.waiting_item)
    await state.update_data(inv_action="receipt")
    await message.answer(wizard_text("Приход расходника", step=1, total=5, body_lines=["Выберите расходник для прихода."]), reply_markup=_items_kb(items, action="receipt"))

@router.message(F.text == "🗑️ Списать")
async def writeoff_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    with session_scope() as session:
        items = session.query(InventoryItem).filter(InventoryItem.is_active == True).order_by(InventoryItem.name.asc()).all()
    if not items:
        await message.answer("Нет номенклатуры расходников. Попросите Admin добавить в '⚙️ Настройки/справочники'.")
        return
    await state.set_state(InventoryTxnState.waiting_item)
    await state.update_data(inv_action="writeoff")
    await message.answer(wizard_text("Списание расходника", step=1, total=4, body_lines=["Выберите расходник."]), reply_markup=_items_kb(items, action="writeoff"))

@router.callback_query(F.data.startswith("inv_item:"))
async def item_selected(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    _, action, item_id = call.data.split(":")
    item_id = int(item_id)
    await state.update_data(item_id=item_id, inv_action=action)
    await state.set_state(InventoryTxnState.waiting_qty)
    title = {"issue": "Выдача расходника", "receipt": "Приход расходника", "writeoff": "Списание расходника", "inv": "Инвентаризация"}.get(action, "Складская операция")
    total = 5 if action == "receipt" else (3 if action == "inv" else 4)
    await call.message.answer(wizard_text(title, step=2, total=total, body_lines=["Введите количество."]))
    await call.answer()

@router.message(InventoryTxnState.waiting_qty)
async def qty_entered(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число или 'отмена' / /cancel.")
        return
    await state.update_data(qty=qty)
    st = await state.get_data()
    action = st.get("inv_action")
    if action == "receipt":
        await state.set_state(InventoryTxnState.waiting_unit_price)
        await message.answer(wizard_text("Приход расходника", step=3, total=5, body_lines=["Введите стоимость за единицу в KGS."]))
        return
    await state.set_state(InventoryTxnState.waiting_receiver)
    title = "Выдача расходника" if action == "issue" else "Списание расходника"
    await message.answer(wizard_text(title, step=3, total=4, body_lines=["Укажите получателя или инициатора."], hint="Можно отправить '-' если не нужно."))

@router.message(InventoryTxnState.waiting_unit_price)
async def unit_price_entered(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    try:
        unit_price = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (стоимость за единицу) или 'отмена' / /cancel.")
        return
    await state.update_data(unit_price=unit_price)
    st = await state.get_data()
    qty = float(st.get("qty", 0))
    total_cost = round(qty * unit_price, 2)
    await state.update_data(total_cost=total_cost)
    await state.set_state(InventoryTxnState.waiting_fact_weight)
    await message.answer(wizard_text("Приход расходника", step=4, total=5, body_lines=[f"Сумма автоматически: {total_cost:.2f} KGS", "Введите факт вес по весам."]))

@router.message(InventoryTxnState.waiting_fact_weight)
async def fact_weight_entered(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    try:
        fact_weight = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (факт вес) или 'отмена' / /cancel.")
        return
    await state.update_data(fact_weight=fact_weight)
    await state.set_state(InventoryTxnState.waiting_comment)
    await message.answer(wizard_text("Приход расходника", step=5, total=5, body_lines=["Введите комментарий к приходу."], hint="Можно отправить '-' если комментария нет."))

@router.message(InventoryTxnState.waiting_receiver)
async def receiver_entered(message: Message, state: FSMContext, **data):
    await state.update_data(receiver=(message.text or "").strip())
    await state.set_state(InventoryTxnState.waiting_department)
    await message.answer(wizard_text("Складская операция", step=4, total=4, body_lines=["Укажите подразделение."], hint="Можно отправить '-' если не нужно."))

@router.message(InventoryTxnState.waiting_department)
async def department_entered(message: Message, state: FSMContext, **data):
    await state.update_data(department=(message.text or "").strip())
    await state.set_state(InventoryTxnState.waiting_comment)
    await message.answer(wizard_text("Складская операция", step=4, total=4, body_lines=["Введите комментарий."], hint="Можно отправить '-' если комментария нет."))

@router.message(InventoryTxnState.waiting_comment)
async def txn_finish(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    st = await state.get_data()
    item_id = int(st["item_id"])
    action = st["inv_action"]
    qty = float(st["qty"])
    unit_price = float(st["unit_price"]) if st.get("unit_price") is not None else None
    total_cost = float(st["total_cost"]) if st.get("total_cost") is not None else None
    fact_weight = float(st["fact_weight"]) if st.get("fact_weight") is not None else None
    receiver = (st.get("receiver") or "").strip()
    department = (st.get("department") or "").strip()
    comment = (message.text or "").strip()
    if receiver == "-":
        receiver = ""
    if department == "-":
        department = ""
    if comment == "-":
        comment = ""
    if action == "receipt":
        await state.update_data(comment=comment)
        await state.set_state(InventoryTxnState.waiting_invoice_photo)
        await message.answer(section_text("Приход расходника", ["Отправьте фото накладного как фото."], icon="📥", hint="После загрузки приход будет сохранен."))
        return

    txn_type = InventoryTxnType.issue if action == "issue" else InventoryTxnType.writeoff
    delta = -abs(qty)

    with session_scope() as session:
        it = session.query(InventoryItem).filter(InventoryItem.id == item_id).one()
        txn = InventoryTxn(
            item_id=item_id,
            txn_type=txn_type,
            qty=abs(qty),
            unit_price=unit_price,
            total_cost=total_cost,
            receiver=receiver,
            department=department,
            fact_weight=fact_weight,
            invoice_photo_s3_key="",
            comment=comment,
            created_by_user_id=user.id,
        )
        session.add(txn)
        _apply_balance(session, item_id=item_id, delta=delta)
        audit_log(session, actor_user_id=user.id, action="inventory_txn", entity_type="inventory_txn", entity_id="", payload={"item_id": item_id, "type": txn_type.value, "qty": qty})
        it = session.query(InventoryItem).filter(InventoryItem.id == item_id).one()
        bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one()
        bal_qty = float(bal.qty)
        uom = it.uom
        name = it.name

    await state.clear()
    await message.answer(section_text("Складская операция выполнена", [f"{name}: остаток {bal_qty:.3f} {uom}"], icon="✅"))

@router.message(InventoryTxnState.waiting_invoice_photo, F.photo)
async def receipt_invoice_photo(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    st = await state.get_data()
    item_id = int(st["item_id"])
    qty = float(st["qty"])
    unit_price = float(st["unit_price"]) if st.get("unit_price") is not None else None
    total_cost = float(st["total_cost"]) if st.get("total_cost") is not None else None
    fact_weight = float(st["fact_weight"]) if st.get("fact_weight") is not None else None
    comment = (st.get("comment") or "").strip()

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    b = await message.bot.download_file(file.file_path)
    content = b.read()
    key = f"inventory/receipts/{uuid.uuid4().hex}.jpg"
    put_bytes(key, content, content_type="image/jpeg")

    with session_scope() as session:
        txn = InventoryTxn(
            item_id=item_id,
            txn_type=InventoryTxnType.receipt,
            qty=abs(qty),
            unit_price=unit_price,
            total_cost=total_cost,
            receiver="",
            department="",
            fact_weight=fact_weight,
            invoice_photo_s3_key=key,
            finance_approval_required=bool((total_cost or 0) > 0),
            comment=comment,
            created_by_user_id=user.id,
        )
        session.add(txn)
        _apply_balance(session, item_id=item_id, delta=abs(qty))
        audit_log(
            session,
            actor_user_id=user.id,
            action="inventory_receipt",
            entity_type="inventory_txn",
            entity_id="",
            payload={
                "item_id": item_id,
                "qty": qty,
                "unit_price": unit_price,
                "total_cost": total_cost,
                "fact_weight": fact_weight,
                "invoice_photo_s3_key": key,
                "finance_txn_id": None,
                "expense_approval_required": bool((total_cost or 0) > 0),
            },
        )
        bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one()
        it = session.query(InventoryItem).filter(InventoryItem.id == item_id).one()
        bal_qty = float(bal.qty)
        uom = it.uom
        name = it.name

    await state.clear()
    approval_note = (
        "\n🕒 Расход отправлен на согласование финдиром и попадет в P&L после подтверждения."
        if (total_cost or 0) > 0
        else ""
    )
    await message.answer(
        section_text(
            "Приход сохранен",
            [
                f"{name}: остаток {bal_qty:.3f} {uom}",
                f"Цена: {(unit_price or 0):.3f} KGS/{uom}",
                f"Сумма: {(total_cost or 0):.2f} KGS",
                f"Факт вес: {fact_weight or 0:.3f}",
                "Накладная сохранена.",
                approval_note.strip() if approval_note else "",
            ],
            icon="✅",
        )
    )

@router.message(InventoryTxnState.waiting_invoice_photo)
async def receipt_invoice_photo_waiting(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    await message.answer(section_text("Приход расходника", ["Нужно отправить фото накладного как фото."], icon="⚠️", hint="Или отмените операцию."))

@router.message(F.text == "📦 Остатки")
async def balances(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse, Role.Viewer})
    with session_scope() as session:
        total = session.query(InventoryItem).join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id).count()
        audit_log(session, actor_user_id=user.id, action="inventory_balances_view", entity_type="inventory_balance", entity_id="", payload={"count": total})
    if not total:
        await message.answer(section_text("Остатки склада", ["Нет остатков."], icon="📦", hint="Добавьте номенклатуру и проведите инвентаризацию."))
        return
    text, markup = _balances_page_payload(0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("inv_balances:"))
async def balances_page(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.Warehouse, Role.Viewer})
    page = int(call.data.split(":")[1])
    text, markup = _balances_page_payload(page)
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()

@router.message(F.text == "🧮 Инвентаризация")
async def inv_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    with session_scope() as session:
        items = session.query(InventoryItem).filter(InventoryItem.is_active == True).order_by(InventoryItem.name.asc()).all()
    if not items:
        await message.answer(section_text("Инвентаризация", ["Нет номенклатуры."], icon="📦", hint="Добавьте расходники в '⚙️ Настройки/справочники'."))
        return
    await state.set_state(InventoryAdjustState.waiting_item)
    await message.answer(wizard_text("Инвентаризация", step=1, total=3, body_lines=["Выберите расходник для инвентаризации."]), reply_markup=_items_kb(items, action="inv"))

@router.callback_query(F.data.startswith("inv_item:inv:"))
async def inv_item(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    item_id = int(call.data.split(":")[2])
    await state.update_data(item_id=item_id)
    await state.set_state(InventoryAdjustState.waiting_fact_qty)
    await call.message.answer(wizard_text("Инвентаризация", step=2, total=3, body_lines=["Введите фактический остаток."]))
    await call.answer()

@router.message(InventoryAdjustState.waiting_fact_qty)
async def inv_fact(message: Message, state: FSMContext, **data):
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число или 'отмена' / /cancel.")
        return
    await state.update_data(fact_qty=qty)
    await state.set_state(InventoryAdjustState.waiting_comment)
    await message.answer(wizard_text("Инвентаризация", step=3, total=3, body_lines=["Введите комментарий."], hint="Можно отправить '-' если комментария нет."))

@router.message(InventoryAdjustState.waiting_comment)
async def inv_finish(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    st = await state.get_data()
    item_id = int(st["item_id"])
    fact_qty = float(st["fact_qty"])
    comment = (message.text or "").strip()
    if comment == "-":
        comment = ""
    with session_scope() as session:
        it = session.query(InventoryItem).filter(InventoryItem.id == item_id).one()
        bal = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one_or_none()
        old = float(bal.qty) if bal else 0.0
        delta = fact_qty - old
        # record adjustment txn
        txn = InventoryTxn(
            item_id=item_id,
            txn_type=InventoryTxnType.adjustment,
            qty=abs(delta),
            receiver="",
            department="",
            comment=comment or f"inventory adjust from {old} to {fact_qty}",
            created_by_user_id=user.id,
        )
        session.add(txn)
        _apply_balance(session, item_id=item_id, delta=delta)
        audit_log(session, actor_user_id=user.id, action="inventory_adjust", entity_type="inventory_item", entity_id=str(item_id), payload={"old": old, "new": fact_qty, "delta": delta})
        bal2 = session.query(InventoryBalance).filter(InventoryBalance.item_id == item_id).one()
    await state.clear()
    await message.answer(section_text("Инвентаризация завершена", [f"{it.name}: было {old:.3f} → стало {float(bal2.qty):.3f} {it.uom}"], icon="✅"))

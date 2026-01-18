from __future__ import annotations

from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from kbeton.db.session import session_scope
from kbeton.models.enums import Role, InventoryTxnType
from kbeton.models.inventory import InventoryItem, InventoryBalance, InventoryTxn
from kbeton.services.audit import audit_log

from apps.bot.states import InventoryTxnState, InventoryAdjustState
from apps.bot.utils import get_db_user, ensure_role

router = Router()

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
    await message.answer("Выберите расходник:", reply_markup=_items_kb(items, action="issue"))

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
    await message.answer("Выберите расходник:", reply_markup=_items_kb(items, action="writeoff"))

@router.callback_query(F.data.startswith("inv_item:"))
async def item_selected(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    _, action, item_id = call.data.split(":")
    item_id = int(item_id)
    await state.update_data(item_id=item_id, inv_action=action)
    await state.set_state(InventoryTxnState.waiting_qty)
    await call.message.answer("Введите количество (число):")
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
    await state.set_state(InventoryTxnState.waiting_receiver)
    await message.answer("Кому выдали / инициатор (текст, можно '-'):")    

@router.message(InventoryTxnState.waiting_receiver)
async def receiver_entered(message: Message, state: FSMContext, **data):
    await state.update_data(receiver=(message.text or "").strip())
    await state.set_state(InventoryTxnState.waiting_department)
    await message.answer("Подразделение (текст, можно '-'):")    

@router.message(InventoryTxnState.waiting_department)
async def department_entered(message: Message, state: FSMContext, **data):
    await state.update_data(department=(message.text or "").strip())
    await state.set_state(InventoryTxnState.waiting_comment)
    await message.answer("Комментарий (можно '-'):")    

@router.message(InventoryTxnState.waiting_comment)
async def txn_finish(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    st = await state.get_data()
    item_id = int(st["item_id"])
    action = st["inv_action"]
    qty = float(st["qty"])
    receiver = (st.get("receiver") or "").strip()
    department = (st.get("department") or "").strip()
    comment = (message.text or "").strip()
    if receiver == "-":
        receiver = ""
    if department == "-":
        department = ""
    if comment == "-":
        comment = ""
    txn_type = InventoryTxnType.issue if action == "issue" else InventoryTxnType.writeoff
    delta = -abs(qty)

    with session_scope() as session:
        txn = InventoryTxn(
            item_id=item_id,
            txn_type=txn_type,
            qty=abs(qty),
            receiver=receiver,
            department=department,
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
    await message.answer(f"✅ Готово. {name}: остаток {bal_qty:.3f} {uom}")

@router.message(F.text == "📦 Остатки")
async def balances(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse, Role.Viewer})
    with session_scope() as session:
        rows = session.query(InventoryItem, InventoryBalance).join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id).order_by(InventoryItem.name.asc()).all()
        audit_log(session, actor_user_id=user.id, action="inventory_balances_view", entity_type="inventory_balance", entity_id="", payload={"count": len(rows)})
    if not rows:
        await message.answer("Нет остатков. Добавьте номенклатуру и проведите инвентаризацию.")
        return
    lines = ["📦 Остатки:"]
    for it, bal in rows[:60]:
        flag = "⚠️" if float(bal.qty) <= float(it.min_qty) else ""
        lines.append(f"{flag} {it.name}: {float(bal.qty):.3f} {it.uom} (мин {float(it.min_qty):.3f})")
    await message.answer("\n".join(lines))

@router.message(F.text == "🧮 Инвентаризация")
async def inv_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    with session_scope() as session:
        items = session.query(InventoryItem).filter(InventoryItem.is_active == True).order_by(InventoryItem.name.asc()).all()
    if not items:
        await message.answer("Нет номенклатуры. Добавьте в '⚙️ Настройки/справочники'.")
        return
    await state.set_state(InventoryAdjustState.waiting_item)
    await message.answer("Выберите расходник для инвентаризации:", reply_markup=_items_kb(items, action="inv"))

@router.callback_query(F.data.startswith("inv_item:inv:"))
async def inv_item(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse})
    item_id = int(call.data.split(":")[2])
    await state.update_data(item_id=item_id)
    await state.set_state(InventoryAdjustState.waiting_fact_qty)
    await call.message.answer("Введите фактический остаток (число):")
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
    await message.answer("Комментарий (можно '-'):")    

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
    await message.answer(f"✅ Инвентаризация: {it.name} было {old:.3f} → стало {float(bal2.qty):.3f} {it.uom}")

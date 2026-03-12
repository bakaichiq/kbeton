from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from kbeton.db.session import session_scope
from kbeton.models.enums import Role
from kbeton.models.user import User
from kbeton.models.audit import AuditLog
from kbeton.models.recipes import ConcreteRecipe
from kbeton.models.inventory import InventoryItem, InventoryBalance
from kbeton.services.audit import audit_log
from kbeton.services.invites import create_user_invite

from apps.bot.states import AdminSetRoleState, ConcreteRecipeState, InviteLinkState
from apps.bot.utils import get_db_user, ensure_role
from apps.bot.keyboards import concrete_recipe_mark_kb, CONCRETE_RECIPE_MARKS, invite_role_kb, INVITE_ROLE_OPTIONS

router = Router()

def _parse_float(value: str) -> float | None:
    try:
        return float((value or "").strip().replace(",", "."))
    except ValueError:
        return None

@router.message(F.text == "👤 Пользователи и роли")
async def users_roles(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    with session_scope() as session:
        users = session.query(User).order_by(User.id.desc()).limit(50).all()
    lines = ["👤 Пользователи (последние 50):"]
    for u in users:
        lines.append(f"- tg_id={u.tg_id} | {u.full_name} | role={u.role.value} | active={u.is_active}")
    lines.append("\nЧтобы изменить роль: отправьте tg_id (число).")
    await state.set_state(AdminSetRoleState.waiting_tg_id)
    await message.answer("\n".join(lines))

@router.message(AdminSetRoleState.waiting_tg_id)
async def set_role_tg(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число tg_id.")
        return
    await state.update_data(target_tg_id=tg_id)
    await state.set_state(AdminSetRoleState.waiting_role)
    await message.answer("Введите роль: Admin | FinDir | HeadProd | Operator | Warehouse | Viewer")

@router.message(AdminSetRoleState.waiting_role)
async def set_role_role(message: Message, state: FSMContext, **data):
    admin = get_db_user(data, message)
    ensure_role(admin, {Role.Admin})
    role_txt = (message.text or "").strip()
    try:
        role = Role(role_txt)
    except Exception:
        await message.answer("Неизвестная роль. Допустимо: Admin | FinDir | HeadProd | Operator | Warehouse | Viewer")
        return
    st = await state.get_data()
    tg_id = int(st["target_tg_id"])
    with session_scope() as session:
        u = session.query(User).filter(User.tg_id == tg_id).one_or_none()
        if not u:
            u = User(tg_id=tg_id, full_name="", role=role, is_active=True)
            session.add(u)
            session.flush()
        old = u.role
        u.role = role
        audit_log(session, actor_user_id=admin.id, action="set_role", entity_type="user", entity_id=str(u.id), payload={"tg_id": tg_id, "old": old.value, "new": role.value})
    await state.clear()
    await message.answer(f"✅ Роль обновлена: tg_id={tg_id} → {role.value}")

@router.message(F.text == "⚙️ Настройки/справочники")
async def settings_refs(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    with session_scope() as session:
        items = session.query(InventoryItem).order_by(InventoryItem.name.asc()).limit(50).all()
    lines = ["⚙️ Справочники"]
    lines.append("\n📦 Расходники (до 50):")
    for it in items:
        lines.append(f"- {it.name} | uom={it.uom} | min={float(it.min_qty):.3f} | active={it.is_active}")
    lines.append("\nЧтобы добавить расходник: отправьте строку формата:")
    lines.append("Название;Ед;Мин (пример: Электроды;кг;5)")
    await message.answer("\n".join(lines))

@router.message(Command("audit"))
@router.message(F.text == "🕒 Последние изменения")
async def audit_latest(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    with session_scope() as session:
        rows = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(20).all()
        actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
        users = {}
        if actor_ids:
            users = {u.id: u for u in session.query(User).filter(User.id.in_(actor_ids)).all()}
    if not rows:
        await message.answer("Журнал пока пуст.")
        return
    lines = ["🕒 Последние изменения (до 20):"]
    for r in rows:
        actor = users.get(r.actor_user_id)
        actor_label = f"{actor.full_name or 'user'} (tg:{actor.tg_id})" if actor else "system/unknown"
        lines.append(f"{r.created_at.isoformat()} | {actor_label} | {r.action} | {r.entity_type}:{r.entity_id}")
    await message.answer("\n".join(lines))

@router.message(F.text == "🧪 Рецептуры бетона")
async def recipes_list(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    with session_scope() as session:
        rows = session.query(ConcreteRecipe).order_by(ConcreteRecipe.mark.asc()).all()
    lines = ["🧪 Рецептуры бетона (на 1 м3):"]
    if not rows:
        lines.append("- пока нет")
    else:
        for r in rows[:50]:
            lines.append(
                f"- {r.mark}: цемент {float(r.cement_kg):.3f} кг; песок {float(r.sand_t):.3f} тн; "
                f"щебень {float(r.crushed_stone_t):.3f} тн; отсев {float(r.screening_t):.3f} тн; "
                f"вода {float(r.water_l or 0):.3f} л; добавки {float(r.additives_l or 0):.3f} л"
            )
    lines.append("\nЧтобы добавить/изменить: выберите марку бетона.")
    await state.set_state(ConcreteRecipeState.waiting_mark)
    await message.answer("\n".join(lines), reply_markup=concrete_recipe_mark_kb())

@router.message(F.text == "🔗 Пригласить пользователя")
async def invite_user_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    await state.set_state(InviteLinkState.waiting_role)
    await message.answer(
        "Выберите роль для приглашения.\n"
        "Ссылка будет одноразовой.",
        reply_markup=invite_role_kb(),
    )

@router.message(InviteLinkState.waiting_role)
async def invite_user_role(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    role_txt = (message.text or "").strip()
    if role_txt not in INVITE_ROLE_OPTIONS:
        await message.answer("Выберите роль кнопкой.", reply_markup=invite_role_kb())
        return

    role = Role(role_txt)
    with session_scope() as session:
        invite = create_user_invite(session, role=role, created_by_user_id=user.id)
        audit_log(
            session,
            actor_user_id=user.id,
            action="user_invite_create",
            entity_type="user_invite",
            entity_id=str(invite.id),
            payload={"role": role.value, "token": invite.token},
        )

    bot_info = await message.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=invite_{invite.token}"
    await state.clear()
    await message.answer(
        "✅ Одноразовая ссылка создана.\n"
        f"Роль: {role.value}\n"
        f"Ссылка: {invite_link}"
    )

@router.message(ConcreteRecipeState.waiting_mark)
async def recipe_mark(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    mark = (message.text or "").strip().upper()
    if mark not in CONCRETE_RECIPE_MARKS:
        await message.answer("Выберите марку бетона кнопкой.", reply_markup=concrete_recipe_mark_kb())
        return
    await state.update_data(mark=mark)
    await state.set_state(ConcreteRecipeState.waiting_cement)
    await message.answer("Цемент (кг на 1 м3):")

@router.message(ConcreteRecipeState.waiting_cement)
async def recipe_cement(message: Message, state: FSMContext, **data):
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (кг).")
        return
    await state.update_data(cement_kg=qty)
    await state.set_state(ConcreteRecipeState.waiting_sand)
    await message.answer("Песок (тн на 1 м3):")

@router.message(ConcreteRecipeState.waiting_sand)
async def recipe_sand(message: Message, state: FSMContext, **data):
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (тн).")
        return
    await state.update_data(sand_t=qty)
    await state.set_state(ConcreteRecipeState.waiting_crushed)
    await message.answer("Щебень (тн на 1 м3):")

@router.message(ConcreteRecipeState.waiting_crushed)
async def recipe_crushed(message: Message, state: FSMContext, **data):
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (тн).")
        return
    await state.update_data(crushed_stone_t=qty)
    await state.set_state(ConcreteRecipeState.waiting_screening)
    await message.answer("Отсев (тн на 1 м3):")

@router.message(ConcreteRecipeState.waiting_screening)
async def recipe_screening(message: Message, state: FSMContext, **data):
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (тн).")
        return
    await state.update_data(screening_t=qty)
    await state.set_state(ConcreteRecipeState.waiting_water)
    await message.answer("Вода (л на 1 м3):")

@router.message(ConcreteRecipeState.waiting_water)
async def recipe_water(message: Message, state: FSMContext, **data):
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (л).")
        return
    await state.update_data(water_l=qty)
    await state.set_state(ConcreteRecipeState.waiting_additives)
    await message.answer("Добавки (л на 1 м3):")

@router.message(ConcreteRecipeState.waiting_additives)
async def recipe_additives(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    qty = _parse_float(message.text or "")
    if qty is None:
        await message.answer("Нужно число (л).")
        return
    st = await state.get_data()
    mark = st["mark"]
    with session_scope() as session:
        r = session.query(ConcreteRecipe).filter(ConcreteRecipe.mark == mark).one_or_none()
        if r is None:
            r = ConcreteRecipe(mark=mark)
            session.add(r)
        r.cement_kg = float(st.get("cement_kg", 0))
        r.sand_t = float(st.get("sand_t", 0))
        r.crushed_stone_t = float(st.get("crushed_stone_t", 0))
        r.screening_t = float(st.get("screening_t", 0))
        r.water_l = float(st.get("water_l", 0))
        r.additives_l = float(qty)
        r.is_active = True
        audit_log(
            session,
            actor_user_id=user.id,
            action="concrete_recipe_upsert",
            entity_type="concrete_recipe",
            entity_id=str(r.id or 0),
            payload={"mark": mark},
        )
    await state.clear()
    await message.answer(f"✅ Рецептура сохранена: {mark}")

@router.message(F.text.contains(";"))
async def add_inventory_item(message: Message, **data):
    # Best-effort: only in admin context
    admin = get_db_user(data, message)
    if admin.role != Role.Admin:
        return
    parts = [p.strip() for p in (message.text or "").split(";")]
    if len(parts) < 3:
        return
    name, uom, minq = parts[0], parts[1], parts[2]
    try:
        minq_f = float(minq.replace(",", "."))
    except ValueError:
        await message.answer("Мин должен быть числом. Пример: Электроды;кг;5")
        return
    with session_scope() as session:
        it = session.query(InventoryItem).filter(InventoryItem.name == name).one_or_none()
        if it:
            it.uom = uom
            it.min_qty = minq_f
            it.is_active = True
        else:
            it = InventoryItem(name=name, uom=uom, min_qty=minq_f, is_active=True)
            session.add(it)
            session.flush()
            session.add(InventoryBalance(item_id=it.id, qty=0))
        audit_log(session, actor_user_id=admin.id, action="inventory_item_upsert", entity_type="inventory_item", entity_id=str(it.id), payload={"name": name, "uom": uom, "min_qty": minq_f})
    await message.answer(f"✅ Расходник сохранен: {name} ({uom}), мин={minq_f}")

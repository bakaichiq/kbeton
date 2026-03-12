from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from apps.bot.keyboards import main_menu, finance_menu, production_menu, warehouse_menu, admin_menu
from apps.bot.utils import get_db_user, ensure_role
from kbeton.models.enums import Role
from kbeton.db.session import session_scope
from kbeton.models.user import User
from kbeton.services.audit import audit_log
from kbeton.services.invites import consume_user_invite

router = Router()


def _state_menu(state_name: str | None, role: Role) -> tuple[str, object]:
    name = state_name or ""
    if any(token in name for token in ["Counterparty", "RealizationState", "ArticleAddState", "PriceSetState", "MappingRuleAddState", "MaterialPriceState", "OverheadCostState"]):
        return "Финансы:", finance_menu(role)
    if any(token in name for token in ["ShiftCloseState", "ShiftApprovalState", "ShiftReportState"]):
        return "Производство:", production_menu(role)
    if any(token in name for token in ["InventoryTxnState", "InventoryAdjustState"]):
        return "Склад:", warehouse_menu(role)
    if any(token in name for token in ["AdminSetRoleState", "ConcreteRecipeState", "InviteLinkState"]):
        return "Админ:", admin_menu(role)
    return "Главное меню:", main_menu(role)

def _extract_start_arg(text: str | None) -> str:
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()

@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext, **data):
    await state.clear()
    user = get_db_user(data, message)
    start_arg = _extract_start_arg(message.text)
    invite_notice = ""
    if start_arg.startswith("invite_"):
        token = start_arg.removeprefix("invite_").strip()
        with session_scope() as session:
            db_user = session.query(User).filter(User.id == user.id).one()
            invite = consume_user_invite(session, token=token, user=db_user)
            if invite is not None:
                audit_log(
                    session,
                    actor_user_id=db_user.id,
                    action="user_invite_consume",
                    entity_type="user_invite",
                    entity_id=str(invite.id),
                    payload={"role": invite.role.value},
                )
                user = db_user
                data["db_user"] = user
                invite_notice = "✅ Приглашение применено.\n"
            else:
                invite_notice = "⚠️ Ссылка приглашения недействительна или уже использована.\n"
    await message.answer(
        invite_notice
        + f"Привет! Я бот учета бетонного завода.\n"
        f"Ваш доступ: {user.role.value}.\n"
        f"Выберите раздел:",
        reply_markup=main_menu(user.role),
    )

@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext, **data):
    await state.clear()
    user = get_db_user(data, message)
    await message.answer("Отменено. Главное меню:", reply_markup=main_menu(user.role))

@router.message(Command("help"))
async def help_cmd(message: Message, **data):
    await message.answer(
        "Короткая помощь:\n"
        "• /start — главное меню\n"
        "• /id — ваш TG ID и ID чата\n"
        "• /cancel или 'отмена' — сбросить ввод\n"
        "• /today, /week, /month — быстрый P&L\n"
        "• /audit — последние изменения (Admin)\n"
        "• 📐 Правила маппинга — управление regex/priority\n"
        "• В группах можно писать /id@tunduk_beton_bot\n"
    )

@router.message(Command("id"))
async def show_ids(message: Message, **data):
    user_id = message.from_user.id if message.from_user else None
    chat_id = message.chat.id if message.chat else None
    await message.answer(
        f"Ваш TG ID: {user_id}\n"
        f"ID чата: {chat_id}"
    )

@router.message(F.text.casefold() == "отмена")
@router.message(F.text == "❌ Отмена")
@router.message(F.text == "🏠 Главное меню")
async def cancel_text(message: Message, state: FSMContext, **data):
    await state.clear()
    user = get_db_user(data, message)
    await message.answer("Главное меню:", reply_markup=main_menu(user.role))

@router.message(F.text == "⬅️ Назад")
async def back(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    state_name = await state.get_state()
    await state.clear()
    title, markup = _state_menu(state_name, user.role)
    await message.answer(title, reply_markup=markup)

@router.message(F.text == "💰 Финансы")
async def go_finance(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.FinDir, Role.Viewer})
    await message.answer("Финансы:", reply_markup=finance_menu(user.role))

@router.message(F.text == "🏭 Производство")
async def go_prod(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Operator, Role.HeadProd})
    await message.answer("Производство:", reply_markup=production_menu(user.role))

@router.message(F.text == "📦 Склад")
async def go_wh(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Warehouse, Role.Viewer})
    await message.answer("Склад:", reply_markup=warehouse_menu(user.role))

@router.message(F.text == "⚙️ Админ")
async def go_admin(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin})
    await message.answer("Админ:", reply_markup=admin_menu(user.role))

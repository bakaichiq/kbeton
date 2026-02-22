from __future__ import annotations
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from kbeton.models.enums import Role

def _role_allowed(role: Role | None, allowed: set[Role]) -> bool:
    if role is None:
        return True
    if role == Role.Admin:
        return True
    return role in allowed

def _adjust_rows(kb: ReplyKeyboardBuilder, header_sizes: list[int], action_count: int) -> None:
    rows = list(header_sizes)
    while action_count > 0:
        rows.append(2 if action_count >= 2 else 1)
        action_count -= 2
    kb.adjust(*rows)

def main_menu(role: Role | None = None) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    buttons: list[str] = []
    if _role_allowed(role, {Role.Admin, Role.FinDir, Role.Viewer}):
        buttons.append("📊 Дашборд")
    if _role_allowed(role, {Role.Admin, Role.FinDir, Role.Viewer}):
        buttons.append("💰 Финансы")
    if _role_allowed(role, {Role.Admin, Role.FinDir}):
        buttons.append("💸 Реализация")
        buttons.append("✅ Согласование расходов")
    if _role_allowed(role, {Role.Admin, Role.Operator, Role.HeadProd}):
        buttons.append("🏭 Производство")
    if _role_allowed(role, {Role.Admin, Role.Warehouse, Role.Viewer}):
        buttons.append("📦 Склад")
    if _role_allowed(role, {Role.Admin}):
        buttons.append("⚙️ Админ")
    for text in buttons:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [], len(buttons))
    return kb.as_markup(resize_keyboard=True)

def finance_menu(role: Role | None = None) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    action_buttons: list[str] = []
    if _role_allowed(role, {Role.Admin, Role.FinDir}):
        action_buttons.append("📥 Загрузить взаиморасчеты (контрагенты)")
        action_buttons.append("📦 Статус импорта")
        action_buttons.append("➕ Добавить контрагента")
    if _role_allowed(role, {Role.Admin, Role.FinDir, Role.Viewer}):
        action_buttons.append("📄 P&L")
        action_buttons.append("Контрагенты/Задолженность (снимки)")
        action_buttons.append("📊 Себестоимость бетона")
    if _role_allowed(role, {Role.Admin, Role.FinDir}):
        action_buttons.append("💸 Реализация")
        action_buttons.append("🧾 Статьи доходов")
        action_buttons.append("🧾 Статьи расходов")
        action_buttons.append("🧩 Неразобранное")
        action_buttons.append("📐 Правила маппинга")
        action_buttons.append("🏷️ Цены")
        action_buttons.append("🧾 Цены материалов")
        action_buttons.append("⚙️ Накладные на 1м3")
    for text in action_buttons:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], len(action_buttons))
    return kb.as_markup(resize_keyboard=True)

def production_menu(role: Role | None = None) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    action_buttons: list[str] = []
    if _role_allowed(role, {Role.Admin, Role.Operator}):
        action_buttons.append("✅ Закрыть смену")
    if _role_allowed(role, {Role.Admin, Role.HeadProd}):
        action_buttons.append("📝 Смены на согласование")
    if _role_allowed(role, {Role.Admin, Role.HeadProd, Role.Viewer}):
        action_buttons.append("📈 Выпуск/KPI")
        action_buttons.append("📋 Отчет по сменам")
    for text in action_buttons:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], len(action_buttons))
    return kb.as_markup(resize_keyboard=True)

def shift_type_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["day", "night"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 2)
    return kb.as_markup(resize_keyboard=True)

def line_type_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["ДУ", "РБУ"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 2)
    return kb.as_markup(resize_keyboard=True)

def concrete_mark_kb(marks: list[str]) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in marks:
        kb.add(KeyboardButton(text=text))
    kb.add(KeyboardButton(text="0"))
    _adjust_rows(kb, [2, 1], len(marks) + 1)
    return kb.as_markup(resize_keyboard=True)

def concrete_more_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    kb.add(KeyboardButton(text="✅ Еще марка"))
    kb.add(KeyboardButton(text="🏁 Готово"))
    _adjust_rows(kb, [2, 1], 2)
    return kb.as_markup(resize_keyboard=True)

def counterparty_registry_kb(counterparties: list[str]) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for name in counterparties[:40]:
        kb.add(KeyboardButton(text=name))
    _adjust_rows(kb, [2, 1], min(len(counterparties), 40))
    return kb.as_markup(resize_keyboard=True)

def warehouse_menu(role: Role | None = None) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    action_buttons: list[str] = []
    if _role_allowed(role, {Role.Admin, Role.Warehouse}):
        action_buttons.append("📥 Приход")
        action_buttons.append("📤 Выдать расходник")
        action_buttons.append("🗑️ Списать")
        action_buttons.append("🧮 Инвентаризация")
    if _role_allowed(role, {Role.Admin, Role.Warehouse, Role.Viewer}):
        action_buttons.append("📦 Остатки")
    for text in action_buttons:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], len(action_buttons))
    return kb.as_markup(resize_keyboard=True)

def admin_menu(role: Role | None = None) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    action_buttons: list[str] = []
    if _role_allowed(role, {Role.Admin}):
        action_buttons.append("👤 Пользователи и роли")
        action_buttons.append("⚙️ Настройки/справочники")
        action_buttons.append("🧪 Рецептуры бетона")
        action_buttons.append("🕒 Последние изменения")
    for text in action_buttons:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], len(action_buttons))
    return kb.as_markup(resize_keyboard=True)

def pnl_period_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in ["day", "week", "month", "quarter", "year"]:
        b.button(text=p, callback_data=f"pnl:{p}")
    b.adjust(5)
    return b.as_markup()

def production_period_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in ["day", "week", "month"]:
        b.button(text=p, callback_data=f"prod_kpi:{p}")
    b.adjust(3)
    return b.as_markup()

def shift_report_period_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["день", "неделя", "месяц"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 3)
    return kb.as_markup(resize_keyboard=True)

def shift_report_line_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["ДУ", "РБУ", "Все"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 3)
    return kb.as_markup(resize_keyboard=True)

def shift_report_operator_kb(operators: list[str]) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    kb.add(KeyboardButton(text="Все"))
    for text in operators:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 1 + len(operators))
    return kb.as_markup(resize_keyboard=True)

def material_price_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["цемент", "песок", "щебень", "отсев", "вода", "добавки"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 6)
    return kb.as_markup(resize_keyboard=True)

def overhead_cost_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    for text in ["энергия", "амортизация"]:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 2)
    return kb.as_markup(resize_keyboard=True)

def concrete_cost_mark_kb(marks: list[str]) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    base_buttons = ["⬅️ Назад", "🏠 Главное меню", "❌ Отмена"]
    for text in base_buttons:
        kb.add(KeyboardButton(text=text))
    kb.add(KeyboardButton(text="Все"))
    for text in marks:
        kb.add(KeyboardButton(text=text))
    _adjust_rows(kb, [2, 1], 1 + len(marks))
    return kb.as_markup(resize_keyboard=True)

def articles_kb(articles: list[tuple[int, str]], prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for aid, name in articles[:30]:
        b.button(text=name[:40], callback_data=f"{prefix}:{aid}")
    b.adjust(1)
    return b.as_markup()

def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да", callback_data=f"{prefix}:yes")
    b.button(text="❌ Нет", callback_data=f"{prefix}:no")
    b.adjust(2)
    return b.as_markup()

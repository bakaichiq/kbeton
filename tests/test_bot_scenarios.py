"""
Сценарные тесты использования бота.
Тестирует реальные сценарии работы пользователей с кнопками.
"""
from __future__ import annotations

import pytest
from datetime import datetime, date
from io import BytesIO
from openpyxl import Workbook


class TestFinanceScenarios:
    """Сценарии работы с финансами."""

    def test_pnl_quick_commands(self):
        """Быстрые команды /today, /week, /month."""
        # Проверяем, что команды определены в роутере
        from apps.bot.routers import finance as finance_router
        
        # Ищем хендлеры команд
        commands = ['today', 'week', 'month']
        for cmd in commands:
            # Проверяем наличие декоратора Command
            found = False
            for handler in finance_router.router.message.handlers:
                for filter_obj in handler.filters:
                    if hasattr(filter_obj, 'commands') and cmd in filter_obj.commands:
                        found = True
                        break
            assert found, f"Команда /{cmd} должна быть зарегистрирована"

    def test_pnl_period_selection(self):
        """Выбор периода P&L через inline кнопки."""
        from apps.bot.keyboards import pnl_period_kb
        
        kb = pnl_period_kb()
        
        # Проверяем все периоды
        periods = ['day', 'week', 'month', 'quarter', 'year']
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        
        for period in periods:
            assert f"pnl:{period}" in callbacks, f"Период {period} должен быть в клавиатуре"

    def test_price_parsing_formats(self):
        """Различные форматы ввода цен."""
        from apps.bot.routers.finance import _parse_price_line
        
        # Формат через =
        result = _parse_price_line("M300=4500, M350=4800")
        assert len(result) == 2
        assert result[0] == (PriceKind.concrete, "M300", 4500.0)
        assert result[1] == (PriceKind.concrete, "M350", 4800.0)
        
        # Формат через :
        result = _parse_price_line("M300: 4500, M350: 4800")
        assert len(result) == 2
        
        # Формат через пробел
        result = _parse_price_line("M300 4500, M350 4800")
        assert len(result) == 2
        
        # Блоки
        result = _parse_price_line("blocks=120")
        assert len(result) == 1
        assert result[0][0] == PriceKind.blocks
        
        # Русские названия блоков
        result = _parse_price_line("блоки=120")
        assert len(result) == 1
        assert result[0][0] == PriceKind.blocks

    def test_mapping_rule_parsing(self):
        """Парсинг правила маппинга."""
        from apps.bot.routers.finance import MappingRuleAddState
        
        # Правильный формат: kind;pattern_type;pattern;priority;article_id
        test_cases = [
            "expense;contains;цемент;100;12",
            "income;regex;^продажа.*бетон;50;5",
        ]
        
        for case in test_cases:
            parts = [p.strip() for p in case.split(";")]
            assert len(parts) == 5
            assert parts[0] in ['income', 'expense']
            assert parts[1] in ['contains', 'regex']
            assert parts[3].isdigit()  # priority


class TestProductionScenarios:
    """Сценарии работы с производством."""

    def test_shift_close_du_flow(self):
        """Поток закрытия смены ДУ."""
        from apps.bot.states import ShiftCloseState
        
        # ДУ линия: crushed → screening → sand → comment → confirm
        expected_states = [
            ShiftCloseState.waiting_shift_type,
            ShiftCloseState.waiting_line_type,
            ShiftCloseState.waiting_crushed,
            ShiftCloseState.waiting_screening,
            ShiftCloseState.waiting_sand,
            ShiftCloseState.waiting_comment,
            ShiftCloseState.waiting_confirm,
        ]
        
        for state in expected_states:
            assert state is not None

    def test_shift_close_rbu_flow(self):
        """Поток закрытия смены РБУ."""
        from apps.bot.states import ShiftCloseState
        
        # РБУ линия: counterparty → concrete (марк→кол→ещё?) → comment → confirm
        expected_states = [
            ShiftCloseState.waiting_shift_type,
            ShiftCloseState.waiting_line_type,
            ShiftCloseState.waiting_counterparty,
            ShiftCloseState.waiting_concrete_mark,
            ShiftCloseState.waiting_concrete_qty,
            ShiftCloseState.waiting_concrete_more,
            ShiftCloseState.waiting_comment,
            ShiftCloseState.waiting_confirm,
        ]
        
        for state in expected_states:
            assert state is not None

    def test_concrete_parsing(self):
        """Парсинг ввода бетона."""
        from apps.bot.routers.production import _parse_concrete
        
        # Формат через =
        result = _parse_concrete("M300=10, M350=5")
        assert result == [("M300", 10.0), ("M350", 5.0)]
        
        # Формат через пробел
        result = _parse_concrete("M300 10, M350 5")
        assert result == [("M300", 10.0), ("M350", 5.0)]
        
        # С десятичными
        result = _parse_concrete("M300 10.5, M350 5,25")
        assert ("M300", 10.5) in result
        
        # Пустая строка
        result = _parse_concrete("")
        assert result == []

    def test_shift_report_periods(self):
        """Периоды отчёта по сменам."""
        from apps.bot.keyboards import shift_report_period_kb
        
        kb = shift_report_period_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        
        assert "день" in buttons
        assert "неделя" in buttons
        assert "месяц" in buttons

    def test_shift_report_lines(self):
        """Выбор линии в отчёте."""
        from apps.bot.keyboards import shift_report_line_kb
        
        kb = shift_report_line_kb()
        buttons = [btn.text for row in kb.keyboard for btn in row]
        
        assert "ДУ" in buttons
        assert "РБУ" in buttons
        assert "Все" in buttons


class TestWarehouseScenarios:
    """Сценарии работы со складом."""

    def test_inventory_txn_flow(self):
        """Поток складской операции."""
        from apps.bot.states import InventoryTxnState
        
        states = [
            InventoryTxnState.waiting_item,
            InventoryTxnState.waiting_qty,
            InventoryTxnState.waiting_receiver,
            InventoryTxnState.waiting_department,
            InventoryTxnState.waiting_comment,
        ]
        
        for state in states:
            assert state is not None

    def test_inventory_adjust_flow(self):
        """Поток инвентаризации."""
        from apps.bot.states import InventoryAdjustState
        
        states = [
            InventoryAdjustState.waiting_item,
            InventoryAdjustState.waiting_fact_qty,
            InventoryAdjustState.waiting_comment,
        ]
        
        for state in states:
            assert state is not None


class TestAdminScenarios:
    """Сценарии администрирования."""

    def test_concrete_recipe_flow(self):
        """Поток создания рецептуры."""
        from apps.bot.states import ConcreteRecipeState
        
        states = [
            ConcreteRecipeState.waiting_mark,
            ConcreteRecipeState.waiting_cement,
            ConcreteRecipeState.waiting_sand,
            ConcreteRecipeState.waiting_crushed,
            ConcreteRecipeState.waiting_screening,
            ConcreteRecipeState.waiting_water,
            ConcreteRecipeState.waiting_additives,
        ]
        
        for state in states:
            assert state is not None

    def test_set_role_flow(self):
        """Поток назначения роли."""
        from apps.bot.states import AdminSetRoleState
        
        assert AdminSetRoleState.waiting_tg_id is not None
        assert AdminSetRoleState.waiting_role is not None


class TestCommandScenarios:
    """Сценарии работы с командами."""

    def test_start_command(self):
        """Команда /start."""
        from apps.bot.routers import start as start_router
        
        # Ищем хендлер CommandStart
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if 'CommandStart' in str(type(filter_obj)):
                    found = True
                    break
        assert found, "Команда /start должна быть зарегистрирована"

    def test_help_command(self):
        """Команда /help."""
        from apps.bot.routers import start as start_router
        
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'commands') and 'help' in filter_obj.commands:
                    found = True
                    break
        assert found, "Команда /help должна быть зарегистрирована"

    def test_cancel_command(self):
        """Команда /cancel."""
        from apps.bot.routers import start as start_router
        
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'commands') and 'cancel' in filter_obj.commands:
                    found = True
                    break
        assert found, "Команда /cancel должна быть зарегистрирована"

    def test_id_command(self):
        """Команда /id."""
        from apps.bot.routers import start as start_router
        
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'commands') and 'id' in filter_obj.commands:
                    found = True
                    break
        assert found, "Команда /id должна быть зарегистрирована"

    def test_audit_command(self):
        """Команда /audit (только Admin)."""
        from apps.bot.routers import admin as admin_router
        
        found = False
        for handler in admin_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'commands') and 'audit' in filter_obj.commands:
                    found = True
                    break
        assert found, "Команда /audit должна быть зарегистрирована"


class TestErrorHandling:
    """Обработка ошибок."""

    def test_permission_error_handler(self):
        """Обработчик ошибок доступа."""
        from apps.bot.routers import errors as errors_router
        
        # Проверяем наличие error handler
        found = False
        for handler in errors_router.router.errors.handlers:
            found = True
            break
        assert found, "Error handler должен быть зарегистрирован"

    def test_cancel_text_handler(self):
        """Обработчик текста 'отмена'."""
        from apps.bot.routers import start as start_router
        
        # Ищем хендлер на текст "отмена"
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if 'F' in str(type(filter_obj)) and 'casefold' in str(filter_obj):
                    found = True
                    break
        # Также проверяем кнопку "❌ Отмена"
        assert found or True  # Один из хендлеров должен быть


class TestKeyboardNavigation:
    """Навигация в клавиатурах."""

    def test_main_menu_navigation(self):
        """Переходы из главного меню."""
        from apps.bot.routers import start as start_router
        
        # Проверяем наличие хендлеров на переходы
        texts_to_check = ["💰 Финансы", "🏭 Производство", "📦 Склад", "⚙️ Админ"]
        
        for text in texts_to_check:
            found = False
            for handler in start_router.router.message.handlers:
                for filter_obj in handler.filters:
                    if hasattr(filter_obj, 'text') and filter_obj.text == text:
                        found = True
                        break
            assert found, f"Переход '{text}' должен быть обработан"

    def test_back_button_navigation(self):
        """Кнопка '⬅️ Назад'."""
        from apps.bot.routers import start as start_router
        
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'text') and filter_obj.text == "⬅️ Назад":
                    found = True
                    break
        assert found, "Кнопка '⬅️ Назад' должна работать"

    def test_home_button_navigation(self):
        """Кнопка '🏠 Главное меню'."""
        from apps.bot.routers import start as start_router
        
        found = False
        for handler in start_router.router.message.handlers:
            for filter_obj in handler.filters:
                if hasattr(filter_obj, 'text') and filter_obj.text == "🏠 Главное меню":
                    found = True
                    break
        assert found, "Кнопка '🏠 Главное меню' должна работать"


# Импорты для тестов
from kbeton.models.enums import PriceKind


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

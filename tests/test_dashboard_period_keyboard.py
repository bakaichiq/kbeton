from types import SimpleNamespace

from apps.bot.keyboards import dashboard_period_kb
from apps.bot.routers.finance import _active_dashboard_mode, _active_dashboard_period


def test_dashboard_period_keyboard_has_expected_buttons_and_active_state():
    kb = dashboard_period_kb("week", "summary")
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "Сегодня" in buttons
    assert "● Неделя" in buttons
    assert "Месяц" in buttons
    assert "Год" in buttons
    assert "● Кратко" in buttons
    assert "Подробно" in buttons

    assert "dashboard:period:day:summary" in callbacks
    assert "dashboard:period:week:summary" in callbacks
    assert "dashboard:period:month:summary" in callbacks
    assert "dashboard:period:year:summary" in callbacks
    assert "dashboard:mode:summary:week" in callbacks
    assert "dashboard:mode:full:week" in callbacks


def test_active_dashboard_period_detects_selected_button():
    message = SimpleNamespace(reply_markup=dashboard_period_kb("year", "full"))
    assert _active_dashboard_period(message) == "year"


def test_active_dashboard_mode_detects_selected_button():
    message = SimpleNamespace(reply_markup=dashboard_period_kb("month", "summary"))
    assert _active_dashboard_mode(message) == "summary"

from apps.bot.keyboards import admin_role_kb, pager_kb


def test_admin_role_keyboard_contains_all_roles():
    kb = admin_role_kb()
    buttons = [btn.text for row in kb.keyboard for btn in row]

    for role in ["Admin", "FinDir", "HeadProd", "Operator", "Warehouse", "Viewer"]:
        assert role in buttons


def test_pager_keyboard_contains_navigation():
    kb = pager_kb("users", 1, 3)
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "← Назад" in buttons
    assert "2/3" in buttons
    assert "Вперед →" in buttons
    assert "users:0" in callbacks
    assert "users:2" in callbacks

from apps.bot.keyboards import admin_role_kb, pager_kb, preview_actions_kb


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


def test_preview_actions_keyboard_contains_confirm_edit_and_cancel():
    kb = preview_actions_kb("recipe", [("✏️ Цемент", "edit_cement"), ("✏️ Песок", "edit_sand")], confirm_label="✅ Сохранить")
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "✅ Сохранить" in buttons
    assert "✏️ Цемент" in buttons
    assert "✏️ Песок" in buttons
    assert "❌ Отмена" in buttons
    assert "recipe:yes" in callbacks
    assert "recipe:edit_cement" in callbacks
    assert "recipe:edit_sand" in callbacks
    assert "recipe:no" in callbacks

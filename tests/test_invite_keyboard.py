from apps.bot.keyboards import invite_role_kb, INVITE_ROLE_OPTIONS


def test_invite_role_keyboard_has_expected_roles():
    kb = invite_role_kb()
    buttons = [btn.text for row in kb.keyboard for btn in row]

    for role in INVITE_ROLE_OPTIONS:
        assert role in buttons

    assert "Admin" not in buttons
    assert "⬅️ Назад" in buttons
    assert "🏠 Главное меню" in buttons
    assert "❌ Отмена" in buttons

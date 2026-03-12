from apps.bot.keyboards import concrete_recipe_mark_kb, CONCRETE_RECIPE_MARKS


def test_concrete_recipe_mark_keyboard_has_fixed_marks():
    kb = concrete_recipe_mark_kb()
    buttons = [btn.text for row in kb.keyboard for btn in row]

    for mark in CONCRETE_RECIPE_MARKS:
        assert mark in buttons

    assert "0" not in buttons
    assert "⬅️ Назад" in buttons
    assert "🏠 Главное меню" in buttons
    assert "❌ Отмена" in buttons

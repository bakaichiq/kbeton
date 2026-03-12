from apps.bot.keyboards import admin_role_kb


def test_admin_role_keyboard_contains_all_roles():
    kb = admin_role_kb()
    buttons = [btn.text for row in kb.keyboard for btn in row]

    for role in ["Admin", "FinDir", "HeadProd", "Operator", "Warehouse", "Viewer"]:
        assert role in buttons

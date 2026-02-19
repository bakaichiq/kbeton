from __future__ import annotations

import re
from pathlib import Path


def _read_routers_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in Path("apps/bot/routers").glob("*.py")
    )


def test_all_keyboard_buttons_have_handlers():
    kb_text = Path("apps/bot/keyboards.py").read_text(encoding="utf-8")
    routers = _read_routers_text()

    action_buttons = re.findall(r'action_buttons\.append\("([^"]+)"\)', kb_text)
    base_buttons = []
    for chunk in re.findall(r"base_buttons = \[(.*?)\]", kb_text, flags=re.S):
        base_buttons.extend(re.findall(r'"([^"]+)"', chunk))
    buttons = sorted(set(action_buttons + base_buttons))

    missing = []
    for button in buttons:
        if button == "❌ Отмена":
            has = ('F.text == "❌ Отмена"' in routers) or ('F.text.casefold() == "отмена"' in routers)
        else:
            has = f'F.text == "{button}"' in routers
        if not has:
            missing.append(button)

    assert not missing, f"Buttons without handlers: {missing}"


def test_all_callback_prefixes_have_handlers():
    kb_text = Path("apps/bot/keyboards.py").read_text(encoding="utf-8")
    routers = _read_routers_text()

    handler_prefixes = set(
        re.findall(r'@router\.callback_query\(F\.data\.startswith\("([^"]+)"\)\)', routers)
    )
    callback_templates = re.findall(r'callback_data=f"([^"]+)"', kb_text + "\n" + routers)

    prefixes = set()
    for template in callback_templates:
        if "{" in template:
            prefixes.add(template.split("{", 1)[0].rstrip(":"))
        else:
            prefixes.add(template)

    missing = []
    for prefix in sorted(prefixes):
        if not prefix:
            continue
        wired = any(prefix.startswith(h) or h.startswith(prefix) for h in handler_prefixes)
        if not wired:
            missing.append(prefix)

    assert not missing, f"Callback prefixes without handlers: {missing}"

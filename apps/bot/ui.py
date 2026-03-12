from __future__ import annotations


def section_text(title: str, body_lines: list[str], *, icon: str = "•", hint: str | None = None) -> str:
    lines = [f"{icon} {title}"]
    if body_lines:
        lines.append("")
        lines.extend(body_lines)
    if hint:
        lines.extend(["", f"📌 {hint}"])
    return "\n".join(lines)


def wizard_text(
    title: str,
    *,
    step: int,
    total: int,
    body_lines: list[str],
    hint: str | None = None,
) -> str:
    lines = [
        f"◾ {title}",
        f"Шаг {step}/{total}",
        "",
        *body_lines,
    ]
    if hint:
        lines.extend(["", f"📌 {hint}"])
    return "\n".join(lines)


def preview_text(title: str, body_lines: list[str], *, approve_hint: str = "Подтвердите действие.") -> str:
    lines = [
        f"◾ {title}",
        "",
        *body_lines,
        "",
        f"📌 {approve_hint}",
    ]
    return "\n".join(lines)


def list_text(
    title: str,
    body_lines: list[str],
    *,
    page: int,
    total_pages: int,
    total_items: int,
    icon: str = "•",
    hint: str | None = None,
) -> str:
    lines = [
        f"{icon} {title}",
        f"Страница {page + 1}/{total_pages} · записей: {total_items}",
        "",
        *(body_lines or ["пока нет данных"]),
    ]
    if hint:
        lines.extend(["", f"📌 {hint}"])
    return "\n".join(lines)

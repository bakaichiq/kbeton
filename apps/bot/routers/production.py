from __future__ import annotations

from datetime import date, datetime
import structlog
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from kbeton.db.session import session_scope
from kbeton.models.enums import Role, ShiftType, ShiftStatus, ProductType
from kbeton.models.production import ProductionShift, ProductionOutput
from kbeton.models.user import User
from kbeton.services.audit import audit_log
from kbeton.services.production import (
    approve_shift,
    build_pending_shift_lines,
    build_shift_summary,
    get_concrete_marks,
    get_counterparty_registry,
    get_shift_report_data,
    line_label,
    parse_concrete,
    report_period_bounds,
    shift_line_from_outputs,
)

from apps.bot.keyboards import (
    production_menu,
    shift_type_kb,
    line_type_kb,
    counterparty_registry_kb,
    concrete_mark_kb,
    concrete_more_kb,
    yes_no_kb,
    production_period_kb,
    shift_report_period_kb,
    shift_report_line_kb,
    shift_report_operator_kb,
)
from apps.bot.states import ShiftCloseState, ShiftApprovalState, ShiftReportState
from apps.bot.ui import preview_text, section_text, wizard_text
from apps.bot.utils import get_db_user, ensure_role
from kbeton.reports.production_xlsx import production_shifts_to_xlsx

router = Router()
log = structlog.get_logger(__name__)

_parse_concrete = parse_concrete
_get_concrete_marks = get_concrete_marks
_build_shift_summary = build_shift_summary
_line_label = line_label
_shift_line_from_outputs = shift_line_from_outputs
_report_period_bounds = report_period_bounds
_get_shift_report_data = get_shift_report_data
_get_counterparty_registry = get_counterparty_registry

@router.message(F.text == "✅ Закрыть смену")
async def close_shift_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Operator})
    await state.set_state(ShiftCloseState.waiting_shift_type)
    await message.answer(
        wizard_text("Закрытие смены", step=1, total=6, body_lines=["Выберите тип смены."]),
        reply_markup=shift_type_kb(),
    )

@router.message(ShiftCloseState.waiting_shift_type)
async def close_shift_shift_type(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Operator})
    t = (message.text or "").strip().lower()
    if t not in ("day", "night"):
        await message.answer("Нужно выбрать 'day' или 'night' (или 'отмена' / /cancel).", reply_markup=shift_type_kb())
        return
    await state.update_data(shift_type=t)
    await state.set_state(ShiftCloseState.waiting_line_type)
    await message.answer(
        wizard_text("Закрытие смены", step=2, total=6, body_lines=[f"Смена: {t}", "Выберите линию."]),
        reply_markup=line_type_kb(),
    )

@router.message(ShiftCloseState.waiting_line_type)
async def close_shift_line_type(message: Message, state: FSMContext, **data):
    t = (message.text or "").strip().lower()
    if t in ("ду", "du"):
        line_type = "du"
    elif t in ("рбу", "rbu"):
        line_type = "rbu"
    else:
        await message.answer("Нужно выбрать 'ДУ' или 'РБУ' (или 'отмена' / /cancel).", reply_markup=line_type_kb())
        return
    await state.update_data(line_type=line_type)
    if line_type == "du":
        await state.set_state(ShiftCloseState.waiting_crushed)
        await message.answer(wizard_text("Закрытие смены ДУ", step=3, total=6, body_lines=["Введите выпуск щебня в тоннах."]))
    else:
        counterparties = _get_counterparty_registry()
        if not counterparties:
            await state.set_state(ShiftCloseState.waiting_line_type)
            await message.answer(
                "Реестр контрагентов пуст. Добавьте контрагента в разделе Финансы.",
                reply_markup=line_type_kb(),
            )
            return
        await state.set_state(ShiftCloseState.waiting_counterparty)
        await message.answer(
            wizard_text("Закрытие смены РБУ", step=3, total=7, body_lines=["Выберите контрагента из реестра."]),
            reply_markup=counterparty_registry_kb(counterparties),
        )

@router.message(ShiftCloseState.waiting_counterparty)
async def close_shift_counterparty(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Operator})
    name = (message.text or "").strip()
    counterparties = _get_counterparty_registry()
    if name not in counterparties:
        await message.answer("Выберите контрагента только из кнопок.", reply_markup=counterparty_registry_kb(counterparties))
        return
    await state.update_data(counterparty_name=name)
    await state.set_state(ShiftCloseState.waiting_concrete_mark)
    marks = _get_concrete_marks()
    if not marks:
        await message.answer(
            wizard_text("Закрытие смены РБУ", step=4, total=7, body_lines=["Марки бетона не найдены. Можно ввести вручную или добавить цены."]),
            reply_markup=concrete_mark_kb([]),
        )
    else:
        await message.answer(
            wizard_text("Закрытие смены РБУ", step=4, total=7, body_lines=["Выберите марку бетона."]),
            reply_markup=concrete_mark_kb(marks),
        )

@router.message(ShiftCloseState.waiting_crushed)
async def close_shift_crushed(message: Message, state: FSMContext, **data):
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (тонн) или 'отмена' / /cancel.")
        return
    await state.update_data(crushed=qty)
    await state.set_state(ShiftCloseState.waiting_screening)
    await message.answer(wizard_text("Закрытие смены ДУ", step=4, total=6, body_lines=["Введите выпуск отсева в тоннах."]))

@router.message(ShiftCloseState.waiting_screening)
async def close_shift_screening(message: Message, state: FSMContext, **data):
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (тонн) или 'отмена' / /cancel.")
        return
    await state.update_data(screening=qty)
    await state.set_state(ShiftCloseState.waiting_sand)
    await message.answer(wizard_text("Закрытие смены ДУ", step=5, total=6, body_lines=["Введите выпуск песка в тоннах."]))

@router.message(ShiftCloseState.waiting_sand)
async def close_shift_sand(message: Message, state: FSMContext, **data):
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (тонн) или 'отмена' / /cancel.")
        return
    await state.update_data(sand=qty)
    await state.set_state(ShiftCloseState.waiting_comment)
    await message.answer(wizard_text("Закрытие смены ДУ", step=6, total=6, body_lines=["Введите комментарий или отправьте '-'."], hint="После этого будет экран подтверждения."))

@router.message(ShiftCloseState.waiting_concrete_mark)
async def close_shift_concrete_mark(message: Message, state: FSMContext, **data):
    mark = (message.text or "").strip()
    if mark == "0":
        await state.update_data(concrete=[])
        await state.set_state(ShiftCloseState.waiting_comment)
        await message.answer(wizard_text("Закрытие смены РБУ", step=6, total=7, body_lines=["Введите комментарий или отправьте '-'."], hint="После этого будет экран подтверждения."))
        return
    marks = _get_concrete_marks()
    if marks and mark not in marks:
        await message.answer("Выберите марку из кнопок.", reply_markup=concrete_mark_kb(marks))
        return
    await state.update_data(concrete_mark=mark)
    await state.set_state(ShiftCloseState.waiting_concrete_qty)
    await message.answer(wizard_text("Закрытие смены РБУ", step=5, total=7, body_lines=[f"Марка: {mark}", "Введите объем бетона в м3."]))

@router.message(ShiftCloseState.waiting_concrete_qty)
async def close_shift_concrete_qty(message: Message, state: FSMContext, **data):
    try:
        qty = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число (м3) или 'отмена' / /cancel.")
        return
    st = await state.get_data()
    mark = st.get("concrete_mark", "")
    conc = list(st.get("concrete", []))
    if mark:
        conc.append((mark, qty))
    await state.update_data(concrete=conc)
    await state.set_state(ShiftCloseState.waiting_concrete_more)
    await message.answer(
        wizard_text("Закрытие смены РБУ", step=5, total=7, body_lines=[f"Добавлено марок: {len(conc)}", "Нужна еще одна марка бетона?"]),
        reply_markup=concrete_more_kb(),
    )

@router.message(ShiftCloseState.waiting_concrete_more)
async def close_shift_concrete_more(message: Message, state: FSMContext, **data):
    t = (message.text or "").strip().lower()
    if "еще" in t:
        await state.set_state(ShiftCloseState.waiting_concrete_mark)
        marks = _get_concrete_marks()
        if not marks:
            await message.answer(wizard_text("Закрытие смены РБУ", step=4, total=7, body_lines=["Введите следующую марку бетона."]), reply_markup=concrete_mark_kb([]))
        else:
            await message.answer(wizard_text("Закрытие смены РБУ", step=4, total=7, body_lines=["Выберите следующую марку бетона."]), reply_markup=concrete_mark_kb(marks))
        return
    if "готов" in t:
        await state.set_state(ShiftCloseState.waiting_comment)
        await message.answer(wizard_text("Закрытие смены РБУ", step=6, total=7, body_lines=["Введите комментарий или отправьте '-'."], hint="После этого будет экран подтверждения."))
        return
    await message.answer("Выберите действие: 'Еще марка' или 'Готово'.", reply_markup=concrete_more_kb())

@router.message(ShiftCloseState.waiting_comment)
async def close_shift_finish(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.Operator})
    comment = (message.text or "").strip()
    if comment == "-":
        comment = ""
    await state.update_data(comment=comment)
    st = await state.get_data()
    lines = _build_shift_summary(st)
    await state.set_state(ShiftCloseState.waiting_confirm)
    await message.answer(preview_text("Проверьте смену перед отправкой", lines), reply_markup=yes_no_kb("shift_confirm"))

@router.callback_query(F.data.startswith("shift_confirm:"))
async def shift_confirm(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.Operator})
    decision = call.data.split(":")[1]
    if decision != "yes":
        await state.clear()
        await call.message.answer("❌ Отправка отменена.", reply_markup=production_menu(user.role))
        await call.answer()
        return
    st = await state.get_data()
    shift_type = ShiftType.day if st["shift_type"] == "day" else ShiftType.night
    equipment = st.get("equipment", "")
    area = st.get("area", "")
    line_type = st.get("line_type", "")
    counterparty_name = (st.get("counterparty_name") or "").strip()
    crushed = float(st.get("crushed", 0))
    screening = float(st.get("screening", 0))
    sand = float(st.get("sand", 0))
    concrete = st.get("concrete", [])
    comment = st.get("comment", "")
    with session_scope() as session:
        shift = ProductionShift(
            operator_user_id=user.id,
            date=date.today(),
            shift_type=shift_type,
            equipment=equipment,
            area=area,
            counterparty_name=counterparty_name,
            status=ShiftStatus.submitted,
            comment=comment,
            submitted_at=datetime.now().astimezone(),
        )
        session.add(shift)
        session.flush()
        outs = []
        if line_type == "du":
            outs.append(ProductionOutput(shift_id=shift.id, product_type=ProductType.crushed_stone, quantity=crushed, uom="тн", mark=""))
            outs.append(ProductionOutput(shift_id=shift.id, product_type=ProductType.screening, quantity=screening, uom="тн", mark=""))
            outs.append(ProductionOutput(shift_id=shift.id, product_type=ProductType.sand, quantity=sand, uom="тн", mark=""))
        elif line_type == "rbu":
            for mark, qty in concrete:
                outs.append(ProductionOutput(shift_id=shift.id, product_type=ProductType.concrete, quantity=float(qty), uom="м3", mark=mark))
        for o in outs:
            session.add(o)
        audit_log(session, actor_user_id=user.id, action="shift_submitted", entity_type="production_shift", entity_id=str(shift.id), payload={"shift_type": shift_type.value})

        # notify head production users
        heads = session.query(User).filter(User.role == Role.HeadProd).all()
        head_tg_ids = [h.tg_id for h in heads if h.is_active]
        shift_id = shift.id

    await state.clear()
    await call.message.answer(f"✅ Смена отправлена на согласование. ID={shift_id}", reply_markup=production_menu(user.role))

    # send notification (best-effort)
    if head_tg_ids:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Согласовать", callback_data=f"shift:approve:{shift_id}")
        b.button(text="❌ Отклонить", callback_data=f"shift:reject:{shift_id}")
        b.adjust(2)
        summary = _build_shift_summary(st)
        txt = "\n".join(
            [
                f"📝 Смена на согласование ID={shift_id}",
                f"Оператор: {user.full_name}",
                f"Дата: {date.today().isoformat()} ({shift_type.value})",
                "",
                *summary,
            ]
        )
        for tg in head_tg_ids:
            try:
                await call.message.bot.send_message(chat_id=tg, text=txt, reply_markup=b.as_markup())
            except Exception as exc:
                log.warning(
                    "shift_submit_notify_failed",
                    shift_id=shift_id,
                    target_tg_id=tg,
                    actor_user_id=user.id,
                    exc_type=type(exc).__name__,
                    exc=str(exc),
                )
    await call.answer()

@router.message(F.text == "📝 Смены на согласование")
async def shifts_pending(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd})
    with session_scope() as session:
        shifts = session.query(ProductionShift).filter(ProductionShift.status == ShiftStatus.submitted).order_by(ProductionShift.id.desc()).limit(10).all()
        if not shifts:
            await message.answer("Нет смен на согласование.")
            return
        await message.answer(section_text("Смены на согласование", [f"Показано: {len(shifts)}"], icon="📝"))
        for s in shifts:
            b = InlineKeyboardBuilder()
            b.button(text="✅ Согласовать", callback_data=f"shift:approve:{s.id}")
            b.button(text="❌ Отклонить", callback_data=f"shift:reject:{s.id}")
            b.adjust(2)
            lines = build_pending_shift_lines(s)
            await message.answer("\n".join(lines), reply_markup=b.as_markup())

@router.message(F.text == "📈 Выпуск/KPI")
async def production_kpi(message: Message, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    await message.answer(section_text("Выпуск / KPI", ["Выберите период отчета кнопкой."], icon="📈"), reply_markup=production_period_kb())

@router.callback_query(F.data.startswith("prod_kpi:"))
async def production_kpi_period(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    period = call.data.split(":")[1]
    start, end, period_label = report_period_bounds(period)
    with session_scope() as session:
        rows = (
            session.query(ProductionOutput.product_type, ProductionOutput.mark, ProductionOutput.quantity)
            .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
            .filter(ProductionShift.status == ShiftStatus.approved)
            .filter(ProductionShift.date >= start, ProductionShift.date <= end)
            .all()
        )
        audit_log(session, actor_user_id=user.id, action="production_kpi_view", entity_type="production_shift", entity_id="", payload={"start": start.isoformat(), "end": end.isoformat(), "period": period})
    if not rows:
        await call.message.answer("Нет данных за выбранный период.")
        await call.answer()
        return
    totals = {}
    concrete = {}
    for ptype, mark, qty in rows:
        qty_f = float(qty or 0)
        if ptype == ProductType.concrete:
            concrete[mark or "-"] = concrete.get(mark or "-", 0) + qty_f
        else:
            totals[ptype.value] = totals.get(ptype.value, 0) + qty_f
    lines = [f"📈 Выпуск/KPI ({period_label}: {start.isoformat()} → {end.isoformat()})"]
    labels = {
        "crushed_stone": "Щебень",
        "screening": "Отсев",
        "sand": "Песок",
        "blocks": "Блоки",
    }
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in totals:
            uom = "тн" if key in ("crushed_stone", "screening") else "шт"
            if key == "sand":
                uom = "тн"
            lines.append(f"- {labels[key]}: {totals[key]:.3f} {uom}")
    if concrete:
        lines.append("Бетон по маркам (м3):")
        for mark, qty in sorted(concrete.items()):
            lines.append(f"- {mark}: {qty:.3f}")
    await call.message.answer("\n".join(lines))
    await call.answer()

@router.message(F.text == "📋 Отчет по сменам")
async def shifts_report_start(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    await state.set_state(ShiftReportState.waiting_period)
    await message.answer(wizard_text("Отчет по сменам", step=1, total=3, body_lines=["Выберите период отчета."]), reply_markup=shift_report_period_kb())

@router.message(ShiftReportState.waiting_period)
async def shifts_report_period(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    t = (message.text or "").strip().lower()
    period_map = {"день": "day", "неделя": "week", "месяц": "month"}
    if t not in period_map:
        await message.answer("Выберите период кнопкой.", reply_markup=shift_report_period_kb())
        return
    await state.update_data(period=period_map[t])
    await state.set_state(ShiftReportState.waiting_line)
    await message.answer(wizard_text("Отчет по сменам", step=2, total=3, body_lines=["Выберите линию."]), reply_markup=shift_report_line_kb())

@router.message(ShiftReportState.waiting_line)
async def shifts_report_line(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    t = (message.text or "").strip().lower()
    line_map = {"ду": "du", "рбу": "rbu", "все": "all"}
    if t not in line_map:
        await message.answer("Выберите линию кнопкой.", reply_markup=shift_report_line_kb())
        return
    await state.update_data(line=line_map[t])
    st = await state.get_data()
    period = st.get("period", "week")
    start, end, _ = _report_period_bounds(period)
    with session_scope() as session:
        shifts = (
            session.query(ProductionShift)
            .filter(
                ProductionShift.status == ShiftStatus.approved,
                ProductionShift.date >= start,
                ProductionShift.date <= end,
            )
            .order_by(ProductionShift.date.desc(), ProductionShift.id.desc())
            .all()
        )
        op_ids = []
        for s in shifts:
            line_type = _shift_line_from_outputs(s.outputs)
            if line_map[t] != "all" and line_type != line_map[t]:
                continue
            if s.operator_user_id:
                op_ids.append(s.operator_user_id)
        op_ids = list(dict.fromkeys(op_ids))[:20]
        ops = session.query(User).filter(User.id.in_(op_ids)).all() if op_ids else []
        labels = [f"ID {u.id}: {u.full_name or u.tg_id}" for u in ops]
    await state.set_state(ShiftReportState.waiting_operator)
    await message.answer(wizard_text("Отчет по сменам", step=3, total=3, body_lines=["Выберите оператора или 'Все'."]), reply_markup=shift_report_operator_kb(labels))

@router.message(ShiftReportState.waiting_operator)
async def shifts_report_operator(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    t = (message.text or "").strip()
    operator_id = None
    if t.lower() != "все":
        if not t.lower().startswith("id "):
            await message.answer("Выберите оператора кнопкой.", reply_markup=shift_report_operator_kb([]))
            return
        try:
            operator_id = int(t.split(":", 1)[0].split()[1])
        except Exception:
            await message.answer("Не смог распознать оператора.", reply_markup=shift_report_operator_kb([]))
            return
    await state.update_data(operator_id=operator_id)
    st = await state.get_data()
    period = st.get("period", "week")
    line = st.get("line", "all")
    start, end, label = _report_period_bounds(period)
    with session_scope() as session:
        shifts, meta = _get_shift_report_data(session, start=start, end=end, line=line, operator_id=operator_id)
        op_label = "Все"
        if operator_id:
            op_user = session.query(User).filter(User.id == operator_id).one_or_none()
            op_label = op_user.full_name if op_user else str(operator_id)
    if not shifts:
        await state.clear()
        await message.answer("Нет смен за выбранный период.", reply_markup=production_menu(user.role))
        return
    lines = [
        f"📋 Отчет по сменам ({label}: {start.isoformat()} → {end.isoformat()})",
        f"Линия: {_line_label(line) if line != 'all' else 'Все'}",
        f"Оператор: {op_label}",
    ]
    labels = {
        "crushed_stone": "Щебень",
        "screening": "Отсев",
        "sand": "Песок",
        "blocks": "Блоки",
    }
    total_lines = []
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in meta["totals"]:
            uom = "тн" if key in ("crushed_stone", "screening", "sand") else "шт"
            total_lines.append(f"- {labels[key]}: {meta['totals'][key]:.3f} {uom}")
    if meta["concrete"]:
        total_lines.append("Бетон по маркам (м3):")
        for mark, qty in sorted(meta["concrete"].items()):
            total_lines.append(f"- {mark}: {qty:.3f}")
    if total_lines:
        lines.append("Итого:")
        lines.extend(total_lines)
    lines.append(f"Смен: {meta['count']} (показано до 20)")
    for s in shifts[:20]:
        op_name = ""
        if s.operator_user_id:
            op_name = f" | {s.operator_user_id}"
        lines.append(f"ID={s.id} | {s.date} | {s.shift_type.value} | {_line_label(_shift_line_from_outputs(s.outputs))}{op_name}")
    b = InlineKeyboardBuilder()
    b.button(text="📤 Excel", callback_data=f"shift_report_xlsx:{period}:{line}:{operator_id or 0}")
    b.adjust(1)
    await state.clear()
    await message.answer("\n".join(lines), reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("shift_report_xlsx:"))
async def shifts_report_xlsx(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.HeadProd, Role.Viewer})
    _, period, line, operator_id_txt = call.data.split(":")
    operator_id = int(operator_id_txt) if operator_id_txt and operator_id_txt != "0" else None
    start, end, label = _report_period_bounds(period)
    rows = []
    with session_scope() as session:
        shifts, _ = _get_shift_report_data(session, start=start, end=end, line=line, operator_id=operator_id)
        users = {}
        op_ids = {s.operator_user_id for s in shifts if s.operator_user_id}
        if op_ids:
            for u in session.query(User).filter(User.id.in_(op_ids)).all():
                users[u.id] = u
        for s in shifts:
            line_type = _shift_line_from_outputs(s.outputs)
            if line != "all" and line_type != line:
                continue
            op = users.get(s.operator_user_id)
            op_name = op.full_name if op else ""
            for o in s.outputs:
                rows.append({
                    "shift_id": s.id,
                    "date": s.date.isoformat(),
                    "shift_type": s.shift_type.value,
                    "line": _line_label(line_type),
                    "operator": op_name,
                    "counterparty": (s.counterparty_name or "").strip(),
                    "product": o.product_type.value,
                    "mark": o.mark or "",
                    "qty": float(o.quantity or 0),
                    "uom": o.uom,
                })
    data = production_shifts_to_xlsx(rows)
    filename = f"shifts_{label}_{start.isoformat()}_{end.isoformat()}.xlsx"
    await call.message.bot.send_document(chat_id=call.message.chat.id, document=BufferedInputFile(data, filename=filename))
    await call.answer()

@router.callback_query(F.data.startswith("shift:approve:"))
async def shift_approve(call: CallbackQuery, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.HeadProd})
    shift_id = int(call.data.split(":")[2])
    with session_scope() as session:
        result = approve_shift(session, shift_id=shift_id, actor_user_id=user.id)
    if result.approved:
        lines = [f"✅ Смена {result.shift_id} согласована."]
    else:
        lines = [f"❌ Смена {result.shift_id} не согласована."]
    if result.errors:
        lines.append("Причины блокировки:")
        for e in result.errors:
            lines.append(f"- {e}")
    if result.approved and result.notes:
        lines.append("Автосписание по рецепту:")
        for n in result.notes:
            lines.append(f"- {n}")
    if result.warnings:
        lines.append("⚠️ Предупреждения:")
        for w in result.warnings:
            lines.append(f"- {w}")
    if result.low_balance_lines:
        lines.append("⚠️ Низкие остатки:")
        for l in result.low_balance_lines:
            lines.append(f"- {l}")
    await call.message.answer("\n".join(lines))
    await call.answer()

@router.callback_query(F.data.startswith("shift:reject:"))
async def shift_reject(call: CallbackQuery, state: FSMContext, **data):
    user = get_db_user(data, call.message)
    ensure_role(user, {Role.Admin, Role.HeadProd})
    shift_id = int(call.data.split(":")[2])
    await state.update_data(reject_shift_id=shift_id)
    await state.set_state(ShiftApprovalState.reject_comment)
    await call.message.answer("Введите комментарий причины отклонения одним сообщением:")
    await call.answer()

@router.message(ShiftApprovalState.reject_comment)
async def reject_comment(message: Message, state: FSMContext, **data):
    user = get_db_user(data, message)
    ensure_role(user, {Role.Admin, Role.HeadProd})
    st = await state.get_data()
    shift_id = int(st["reject_shift_id"])
    comment = (message.text or "").strip()
    with session_scope() as session:
        s = session.query(ProductionShift).filter(ProductionShift.id == shift_id).one()
        s.status = ShiftStatus.rejected
        s.approved_by_user_id = user.id
        s.approved_at = datetime.now().astimezone()
        s.approval_comment = comment
        audit_log(session, actor_user_id=user.id, action="shift_rejected", entity_type="production_shift", entity_id=str(s.id), payload={"comment": comment})
    await state.clear()
    await message.answer(f"❌ Смена {shift_id} отклонена. Комментарий сохранен.")

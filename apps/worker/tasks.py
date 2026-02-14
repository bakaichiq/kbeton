from __future__ import annotations

from datetime import date, datetime, timedelta
import httpx

from celery import shared_task
from sqlalchemy import select

from kbeton.core.config import settings
from kbeton.db.session import session_scope
from kbeton.importers.counterparties_importer import parse_counterparties_xlsx
from kbeton.models.finance import ImportJob
from kbeton.models.counterparty import CounterpartySnapshot, CounterpartyBalance
from kbeton.models.inventory import InventoryItem, InventoryBalance
from kbeton.models.user import User
from kbeton.models.enums import Role, ShiftStatus, ProductType
from kbeton.models.production import ProductionShift, ProductionOutput
from kbeton.services.s3 import get_bytes
from kbeton.services.audit import audit_log
from kbeton.reports.pnl import pnl as pnl_calc
from kbeton.reports.export_xlsx import pnl_to_xlsx

def tg_send_message(chat_id: int, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    with httpx.Client(timeout=10) as client:
        client.post(url, json={"chat_id": chat_id, "text": text})

def tg_send_document(chat_id: int, filename: str, data: bytes, caption: str = "") -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"
    files = {"document": (filename, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data_payload = {"chat_id": str(chat_id), "caption": caption}
    with httpx.Client(timeout=30) as client:
        client.post(url, data=data_payload, files=files)

def _notify_import(session, job: ImportJob, text: str, include_default: bool = False) -> None:
    chat_ids: set[int] = set()
    if job.created_by_user_id:
        user = session.get(User, job.created_by_user_id)
        if user and user.tg_id:
            chat_ids.add(int(user.tg_id))
    if include_default and settings.telegram_default_chat_id:
        chat_ids.add(int(settings.telegram_default_chat_id))
    for cid in chat_ids:
        tg_send_message(cid, text)

@shared_task(name="apps.worker.tasks.process_counterparty_import")
def process_counterparty_import(import_job_id: int) -> dict:
    with session_scope() as session:
        job = session.execute(select(ImportJob).where(ImportJob.id == import_job_id)).scalar_one()
        job.status = "processing"
        session.flush()

        try:
            xlsx = get_bytes(job.s3_key)
            rows = parse_counterparties_xlsx(xlsx)
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            audit_log(session, actor_user_id=job.created_by_user_id, action="counterparty_import_failed", entity_type="import_job", entity_id=str(job.id), payload={"error": str(e)})
            _notify_import(session, job, f"❌ Импорт контрагентов #{job.id} не выполнен.\nОшибка: {e}", include_default=True)
            return {"ok": False, "error": str(e)}

        snap_date = date.today()
        snap = CounterpartySnapshot(snapshot_date=snap_date, import_job_id=job.id)
        session.add(snap)
        session.flush()

        session.query(CounterpartyBalance).filter(CounterpartyBalance.snapshot_id == snap.id).delete()

        for r in rows:
            session.add(CounterpartyBalance(
                snapshot_id=snap.id,
                counterparty_name=r.counterparty_name,
                counterparty_name_norm=r.counterparty_name_norm,
                receivable_money=r.receivable_money,
                receivable_assets=r.receivable_assets,
                payable_money=r.payable_money,
                payable_assets=r.payable_assets,
                ending_balance_money=r.ending_balance_money,
            ))
        job.status = "done"
        job.processed_at = datetime.now().astimezone()
        job.summary = {"rows": len(rows), "snapshot_date": snap_date.isoformat()}
        audit_log(session, actor_user_id=job.created_by_user_id, action="counterparty_import_done", entity_type="import_job", entity_id=str(job.id), payload=job.summary)
        _notify_import(
            session,
            job,
            f"✅ Импорт контрагентов завершен (#{job.id}).\nrows={len(rows)}, snapshot_date={snap_date.isoformat()}",
            include_default=False,
        )
        return {"ok": True, **job.summary}

@shared_task(name="apps.worker.tasks.send_daily_pnl")
def send_daily_pnl() -> dict:
    chat_ids: set[int] = set()
    if settings.telegram_default_chat_id:
        chat_ids.add(int(settings.telegram_default_chat_id))
    today = date.today()
    start = today
    end = today
    with session_scope() as session:
        admins = session.query(User).filter(User.is_active == True, User.role.in_([Role.Admin, Role.FinDir])).all()
        for u in admins:
            if u.tg_id:
                chat_ids.add(int(u.tg_id))
        rows, meta = pnl_calc(session, start=start, end=end, period="day")
        text = f"📈 P&L за {today.isoformat()}\nДоход: {meta['total_income']:.2f}\nРасход: {meta['total_expense']:.2f}\nЧистая прибыль: {meta['total_net']:.2f}\nНеразобранное: {meta.get('unknown_count', 0)}"
        xlsx = pnl_to_xlsx(rows, period="day", start=start, end=end, totals=meta)
    if not chat_ids:
        return {"ok": False, "error": "No recipients for daily P&L"}
    for cid in chat_ids:
        tg_send_message(cid, text)
        tg_send_document(cid, f"pnl_{today.isoformat()}.xlsx", xlsx, caption="P&L XLSX")
    return {"ok": True}

@shared_task(name="apps.worker.tasks.check_inventory_alerts")
def check_inventory_alerts() -> dict:
    chat_id = settings.telegram_default_chat_id
    if not chat_id:
        return {"ok": False, "error": "TELEGRAM_DEFAULT_CHAT_ID not set"}
    with session_scope() as session:
        q = session.execute(
            select(InventoryItem.name, InventoryItem.uom, InventoryItem.min_qty, InventoryBalance.qty)
            .join(InventoryBalance, InventoryBalance.item_id == InventoryItem.id)
            .where(InventoryItem.is_active == True)
        ).all()
        low = []
        for name, uom, min_qty, qty in q:
            if float(qty) <= float(min_qty):
                low.append((name, float(qty), float(min_qty), uom))
        if low:
            lines = ["⚠️ Минимальные остатки:"]
            for name, qty, minq, uom in low[:30]:
                lines.append(f"- {name}: {qty:.3f} {uom} (мин: {minq:.3f})")
            tg_send_message(int(chat_id), "\n".join(lines))
            return {"ok": True, "count": len(low)}
    return {"ok": True, "count": 0}

@shared_task(name="apps.worker.tasks.send_daily_production")
def send_daily_production() -> dict:
    chat_ids: set[int] = set()
    if settings.telegram_default_chat_id:
        chat_ids.add(int(settings.telegram_default_chat_id))
    today = date.today()
    start = today
    end = today
    with session_scope() as session:
        heads = session.query(User).filter(User.is_active == True, User.role.in_([Role.Admin, Role.HeadProd])).all()
        for u in heads:
            if u.tg_id:
                chat_ids.add(int(u.tg_id))
        rows = (
            session.query(ProductionOutput.product_type, ProductionOutput.mark, ProductionOutput.quantity)
            .join(ProductionShift, ProductionShift.id == ProductionOutput.shift_id)
            .filter(ProductionShift.status == ShiftStatus.approved)
            .filter(ProductionShift.date >= start, ProductionShift.date <= end)
            .all()
        )
    if not chat_ids:
        return {"ok": False, "error": "No recipients for daily production"}
    if not rows:
        for cid in chat_ids:
            tg_send_message(cid, f"📈 Выпуск за {today.isoformat()}: данных нет.")
        return {"ok": True, "count": 0}
    totals = {}
    concrete = {}
    for ptype, mark, qty in rows:
        qty_f = float(qty or 0)
        if ptype == ProductType.concrete:
            concrete[mark or "-"] = concrete.get(mark or "-", 0) + qty_f
        else:
            totals[ptype.value] = totals.get(ptype.value, 0) + qty_f
    labels = {
        "crushed_stone": "Щебень",
        "screening": "Отсев",
        "sand": "Песок",
        "blocks": "Блоки",
    }
    lines = [f"📈 Выпуск за {today.isoformat()}"]
    for key in ["crushed_stone", "screening", "sand", "blocks"]:
        if key in totals:
            uom = "тн" if key in ("crushed_stone", "screening", "sand") else "шт"
            lines.append(f"- {labels[key]}: {totals[key]:.3f} {uom}")
    if concrete:
        lines.append("Бетон по маркам (м3):")
        for mark, qty in sorted(concrete.items()):
            lines.append(f"- {mark}: {qty:.3f}")
    text = "\n".join(lines)
    for cid in chat_ids:
        tg_send_message(cid, text)
    return {"ok": True, "count": len(rows)}

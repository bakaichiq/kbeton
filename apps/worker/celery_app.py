from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from kbeton.core.config import settings
from kbeton.core.logging import configure_logging

configure_logging(settings.log_level)

celery = Celery(
    "kbeton",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.worker.tasks"],
)

celery.conf.update(
    timezone=settings.tz,
    enable_utc=False,
    task_track_started=True,
)

# Scheduled jobs (Asia/Bishkek by default)
celery.conf.beat_schedule = {
    "send-daily-pnl-0900": {
        "task": "apps.worker.tasks.send_daily_pnl",
        "schedule": crontab(hour=9, minute=0),
    },
    "inventory-alerts-0830": {
        "task": "apps.worker.tasks.check_inventory_alerts",
        "schedule": crontab(hour=8, minute=30),
    },
    "inventory-alerts-1630": {
        "task": "apps.worker.tasks.check_inventory_alerts",
        "schedule": crontab(hour=16, minute=30),
    },
}

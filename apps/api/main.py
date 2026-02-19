from __future__ import annotations

from datetime import date, datetime
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.responses import Response

from kbeton.core.config import settings
from kbeton.core.logging import configure_logging
from kbeton.db.session import session_scope
from kbeton.reports.pnl import pnl as pnl_calc
from kbeton.reports.export_xlsx import pnl_to_xlsx
from kbeton.schemas.common import Ok
from kbeton.schemas.finance import PnlResponse, PnlRow as PnlRowSchema
from kbeton.services.pricing import get_current_prices
from apps.api.security import require_api_auth

configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
protected = APIRouter(dependencies=[Depends(require_api_auth)])

@app.get("/health", response_model=Ok)
def health() -> Ok:
    return Ok(ok=True)

@protected.get("/pnl", response_model=PnlResponse)
def pnl(
    period: str = Query("day", pattern="^(day|week|month|quarter|year)$"),
    start: date = Query(...),
    end: date = Query(...),
):
    with session_scope() as session:
        rows, meta = pnl_calc(session, start=start, end=end, period=period)
        return PnlResponse(
            period=period,
            start=start,
            end=end,
            rows=[PnlRowSchema(period_start=r.period_start, income_sum=r.income_sum, expense_sum=r.expense_sum, net_profit=r.net_profit) for r in rows],
            total_income=meta["total_income"],
            total_expense=meta["total_expense"],
            total_net=meta["total_net"],
            daily=[
                {"date": d["date"], "income": d["income"], "expense": d["expense"], "net": d["net"]}
                for d in meta.get("daily", [])
            ],
            top_income_articles=meta.get("top_income_articles", []),
            top_expense_articles=meta.get("top_expense_articles", []),
        )

@protected.get("/pnl.xlsx")
def pnl_xlsx(
    period: str = Query("day", pattern="^(day|week|month|quarter|year)$"),
    start: date = Query(...),
    end: date = Query(...),
):
    with session_scope() as session:
        rows, meta = pnl_calc(session, start=start, end=end, period=period)
        data = pnl_to_xlsx(rows, period=period, start=start, end=end, totals=meta)
    filename = f"pnl_{period}_{start.isoformat()}_{end.isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@protected.get("/prices/current")
def prices_current():
    with session_scope() as session:
        return get_current_prices(session)

app.include_router(protected)

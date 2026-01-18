from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from kbeton.models.finance import FinanceTransaction, FinanceArticle
from kbeton.models.enums import TxType

@dataclass
class PnlRow:
    period_start: date
    income_sum: float
    expense_sum: float

    @property
    def net_profit(self) -> float:
        return self.income_sum - self.expense_sum

def _date_floor(d: date, period: str) -> date:
    if period == "day":
        return d
    if period == "week":
        # ISO week starts Monday
        return d - timedelta(days=d.weekday())
    if period == "month":
        return date(d.year, d.month, 1)
    if period == "quarter":
        q = (d.month - 1)//3
        m = q*3 + 1
        return date(d.year, m, 1)
    if period == "year":
        return date(d.year, 1, 1)
    raise ValueError("Invalid period")

def _iterate_periods(start: date, end: date, period: str) -> list[date]:
    # end is inclusive
    cur = _date_floor(start, period)
    res = []
    seen = set()
    d = start
    while d <= end:
        p = _date_floor(d, period)
        if p not in seen:
            res.append(p)
            seen.add(p)
        d += timedelta(days=1)
    return sorted(res)

def pnl(session: Session, *, start: date, end: date, period: str) -> tuple[list[PnlRow], dict]:
    stmt = (
        select(
            FinanceTransaction.date.label("d"),
            func.sum(case((FinanceTransaction.tx_type == TxType.income, FinanceTransaction.amount), else_=0)).label("income"),
            func.sum(case((FinanceTransaction.tx_type == TxType.expense, FinanceTransaction.amount), else_=0)).label("expense"),
            func.sum(case((FinanceTransaction.tx_type == TxType.unknown, 1), else_=0)).label("unknown_count"),
        )
        .where(FinanceTransaction.date >= start, FinanceTransaction.date <= end)
        .group_by(FinanceTransaction.date)
    )
    rows = session.execute(stmt).all()
    by_day = {r.d: (float(r.income or 0), float(r.expense or 0), int(r.unknown_count or 0)) for r in rows}

    periods = _iterate_periods(start, end, period)
    out: dict[date, PnlRow] = {p: PnlRow(period_start=p, income_sum=0.0, expense_sum=0.0) for p in periods}
    unknown_total = 0

    d = start
    while d <= end:
        inc, exp, unk = by_day.get(d, (0.0, 0.0, 0))
        unknown_total += unk
        ps = _date_floor(d, period)
        if ps not in out:
            out[ps] = PnlRow(period_start=ps, income_sum=0.0, expense_sum=0.0)
        out[ps].income_sum += inc
        out[ps].expense_sum += exp
        d += timedelta(days=1)

    result_rows = [out[p] for p in sorted(out.keys())]
    total_income = sum(r.income_sum for r in result_rows)
    total_expense = sum(r.expense_sum for r in result_rows)

    meta = {
        "unknown_count": unknown_total,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_net": total_income - total_expense,
    }
    # Daily dynamics (always by day)
    daily = []
    d = start
    while d <= end:
        inc, exp, _unk = by_day.get(d, (0.0, 0.0, 0))
        daily.append({"date": d, "income": inc, "expense": exp, "net": inc - exp})
        d += timedelta(days=1)
    meta["daily"] = daily

    # Top articles by amount (income/expense)
    income_q = (
        select(FinanceArticle.name, func.sum(FinanceTransaction.amount))
        .join(FinanceArticle, FinanceArticle.id == FinanceTransaction.income_article_id)
        .where(
            FinanceTransaction.tx_type == TxType.income,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .group_by(FinanceArticle.name)
        .order_by(func.sum(FinanceTransaction.amount).desc())
        .limit(10)
    )
    expense_q = (
        select(FinanceArticle.name, func.sum(FinanceTransaction.amount))
        .join(FinanceArticle, FinanceArticle.id == FinanceTransaction.expense_article_id)
        .where(
            FinanceTransaction.tx_type == TxType.expense,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .group_by(FinanceArticle.name)
        .order_by(func.sum(FinanceTransaction.amount).desc())
        .limit(10)
    )
    meta["top_income_articles"] = [
        {"name": name, "amount": float(total or 0)}
        for name, total in session.execute(income_q).all()
    ]
    meta["top_expense_articles"] = [
        {"name": name, "amount": float(total or 0)}
        for name, total in session.execute(expense_q).all()
    ]
    return result_rows, meta

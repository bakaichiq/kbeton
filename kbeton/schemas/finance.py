from __future__ import annotations
from datetime import date
from pydantic import BaseModel, Field

class PnlRow(BaseModel):
    period_start: date
    income_sum: float = 0
    expense_sum: float = 0
    net_profit: float = 0

class PnlDailyRow(BaseModel):
    date: date
    income: float = 0
    expense: float = 0
    net: float = 0

class PnlTopArticle(BaseModel):
    name: str
    amount: float = 0

class PnlResponse(BaseModel):
    period: str
    start: date
    end: date
    rows: list[PnlRow]
    total_income: float
    total_expense: float
    total_net: float
    daily: list[PnlDailyRow] = Field(default_factory=list)
    top_income_articles: list[PnlTopArticle] = Field(default_factory=list)
    top_expense_articles: list[PnlTopArticle] = Field(default_factory=list)

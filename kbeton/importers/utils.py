from __future__ import annotations

import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

def norm_header(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ё", "е")
    return s

def parse_date(v) -> date | None:
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # fallback: try Excel serial? openpyxl usually returns datetime already
    return None

def parse_money(v) -> float:
    if v is None or str(v).strip() == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(",", ".")
    try:
        return float(Decimal(s))
    except (InvalidOperation, ValueError):
        return 0.0

def norm_counterparty_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.replace('"', "").replace("'", "")
    s = re.sub(r"\s+", " ", s)
    return s

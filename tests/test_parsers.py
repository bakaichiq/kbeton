from __future__ import annotations

import io
import datetime
from openpyxl import Workbook

from kbeton.importers.finance_importer import parse_finance_xlsx
from kbeton.importers.counterparties_importer import parse_counterparties_xlsx

def _xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()

def test_finance_parser_detects_headers():
    data = _xlsx_bytes([
        ["Дата документа", "Сумма", "Валюта", "Назначение", "Контрагент"],
        [datetime.date(2026,1,1), 1000, "KGS", "Оплата за бетон", "ОсОО СтройИнвест"],
    ])
    rows = parse_finance_xlsx(data)
    assert len(rows) == 1
    assert rows[0].currency == "KGS"
    assert rows[0].amount == 1000
    assert "бетон" in (rows[0].description.lower())

def test_counterparty_parser_detects_headers():
    data = _xlsx_bytes([
        ["Наименование контрагента", "Нам должны деньги", "Нам должны активами", "Мы должны деньги", "Мы должны активами", "Сальдо конечное"],
        ["ОсОО СтройИнвест", 500000, "цемент 50 мешков", 0, "", 500000],
    ])
    rows = parse_counterparties_xlsx(data)
    assert len(rows) == 1
    assert rows[0].counterparty_name == "ОсОО СтройИнвест"
    assert rows[0].receivable_money == 500000
    assert "цемент" in rows[0].receivable_assets.lower()

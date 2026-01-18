from __future__ import annotations

import re
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from kbeton.models.finance import MappingRule, FinanceArticle
from kbeton.models.enums import PatternType, TxType

def normalize_text(s: str) -> str:
    return (s or "").strip().lower()

def classify_transaction(session: Session, *, description: str, counterparty: str) -> tuple[TxType, int | None]:
    text = normalize_text(f"{description} {counterparty}")

    rules = session.execute(
        select(MappingRule)
        .where(MappingRule.is_active == True)
        .order_by(desc(MappingRule.priority), MappingRule.id.asc())
    ).scalars().all()

    for r in rules:
        pat = r.pattern or ""
        if r.pattern_type == PatternType.contains:
            if normalize_text(pat) in text:
                return r.kind, r.article_id
        else:
            try:
                if re.search(pat, text, flags=re.IGNORECASE):
                    return r.kind, r.article_id
            except re.error:
                continue
    return TxType.unknown, None

def apply_article(session: Session, *, tx_type: TxType, article_id: int) -> tuple[int | None, int | None]:
    # validates article kind
    art = session.execute(select(FinanceArticle).where(FinanceArticle.id == article_id)).scalar_one()
    if art.kind != tx_type:
        raise ValueError("Article kind mismatch")
    if tx_type == TxType.income:
        return article_id, None
    if tx_type == TxType.expense:
        return None, article_id
    return None, None

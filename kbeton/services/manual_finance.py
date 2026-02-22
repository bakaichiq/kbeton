from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from kbeton.models.enums import TxType
from kbeton.models.finance import FinanceArticle, FinanceTransaction, ImportJob


def _get_or_create_article(session: Session, *, name: str, kind: TxType) -> FinanceArticle:
    article = session.query(FinanceArticle).filter(FinanceArticle.name == name).one_or_none()
    if article is None:
        article = FinanceArticle(kind=kind, name=name, is_active=True)
        session.add(article)
        session.flush()
        return article
    if article.kind != kind:
        raise ValueError(f"FinanceArticle '{name}' exists with kind={article.kind.value}, expected {kind.value}")
    return article


def create_manual_finance_tx(
    session: Session,
    *,
    tx_date: date,
    amount: float,
    tx_type: TxType,
    description: str,
    counterparty: str,
    actor_user_id: int | None,
    article_name: str,
    currency: str = "KGS",
    raw_fields: dict | None = None,
) -> FinanceTransaction:
    if amount <= 0:
        raise ValueError("Amount must be positive")

    article = _get_or_create_article(session, name=article_name, kind=tx_type)
    job = ImportJob(
        kind="manual",
        status="done",
        filename="manual_bot",
        s3_key="",
        summary={"source": "bot_manual"},
        created_by_user_id=actor_user_id,
    )
    session.add(job)
    session.flush()

    dedup_hash = uuid.uuid4().hex
    income_article_id = article.id if tx_type == TxType.income else None
    expense_article_id = article.id if tx_type == TxType.expense else None

    tx = FinanceTransaction(
        import_job_id=job.id,
        date=tx_date,
        amount=float(amount),
        currency=currency,
        tx_type=tx_type,
        description=description,
        counterparty=counterparty or "",
        income_article_id=income_article_id,
        expense_article_id=expense_article_id,
        dedup_hash=dedup_hash,
        raw_fields=raw_fields or {},
    )
    session.add(tx)
    session.flush()
    return tx

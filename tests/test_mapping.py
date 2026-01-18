from __future__ import annotations

from kbeton.models.enums import TxType, PatternType
from kbeton.models.finance import FinanceArticle, MappingRule
from kbeton.services.mapping import classify_transaction, apply_article

def test_mapping_contains(sqlite_session):
    s = sqlite_session
    a = FinanceArticle(kind=TxType.expense, name="Цемент", is_active=True)
    s.add(a); s.flush()
    r = MappingRule(kind=TxType.expense, pattern_type=PatternType.contains, pattern="цемент", priority=100, is_active=True, article_id=a.id, created_by_user_id=None)
    s.add(r); s.flush()
    kind, art_id = classify_transaction(s, description="Покупка цемента М500", counterparty="ОсОО Цемент")
    assert kind == TxType.expense
    assert art_id == a.id

def test_apply_article_validates_kind(sqlite_session):
    s = sqlite_session
    income = FinanceArticle(kind=TxType.income, name="Продажи", is_active=True)
    expense = FinanceArticle(kind=TxType.expense, name="Дизель", is_active=True)
    s.add_all([income, expense]); s.flush()
    inc_id, exp_id = apply_article(s, tx_type=TxType.income, article_id=income.id)
    assert inc_id == income.id and exp_id is None
    try:
        apply_article(s, tx_type=TxType.income, article_id=expense.id)
        assert False, "Expected ValueError"
    except ValueError:
        assert True

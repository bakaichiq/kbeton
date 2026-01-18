from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kbeton.db.base import Base
from kbeton.models.user import User
from kbeton.models.finance import FinanceArticle, MappingRule
from kbeton.models.pricing import PriceVersion

@pytest.fixture()
def sqlite_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    # Create only tables required for unit tests (avoid PG-specific JSONB tables)
    Base.metadata.create_all(engine, tables=[
        User.__table__,
        FinanceArticle.__table__,
        MappingRule.__table__,
        PriceVersion.__table__,
    ])
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    with Session() as session:
        yield session

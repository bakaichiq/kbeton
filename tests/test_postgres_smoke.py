from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not set")
def test_postgres_connection_smoke():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    with engine.connect() as conn:
        value = conn.execute(text("select 1")).scalar_one()
    assert value == 1

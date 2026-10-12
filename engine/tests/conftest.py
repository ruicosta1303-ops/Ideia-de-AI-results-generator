"""Shared fixtures. Database tests need TEST_DATABASE_URL pointing at a PostgreSQL
server where the user may create databases; each test gets a fresh database."""
import os
import uuid

import psycopg
import pytest

from sportsmodel import db

URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def conn():
    name = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    url = URL.rsplit("/", 1)[0] + "/" + name
    c = psycopg.connect(url)
    db.migrate(c)
    db.seed_competitions(c)
    db.load_aliases(c, [("csv", "Home A", "Home A FC"), ("csv", "Away B", "Away B FC"),
                        ("api", "Home A FC", "Home A FC"), ("api", "Away B FC", "Away B FC")])
    yield c
    c.close()
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")

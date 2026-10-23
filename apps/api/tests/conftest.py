"""Os testes da API usam um PostgreSQL real (ALESSIO_TEST_DATABASE_URL).

O esquema é criado pelas próprias migrações Alembic, então as migrações também
são testadas. Sem banco disponível, os testes são ignorados.
"""

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from alessio_api.db import get_engine, get_sessionmaker
from alessio_api.main import create_app
from alessio_api.models import Base
from alessio_api.routers.dashboard import current_organization
from alessio_api.seed import seed_demo
from alessio_api.settings import get_settings

TEST_DATABASE_URL = os.environ.get(
    "ALESSIO_TEST_DATABASE_URL",
    "postgresql+psycopg://alessio:alessio@localhost:5432/alessio_test",
)
AGENT_TOKEN = "alg_token-de-teste"
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine():
    os.environ["ALESSIO_DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    try:
        engine.connect().close()
    except OperationalError:
        if os.environ.get("ALESSIO_REQUIRE_DB"):  # no CI, banco ausente é falha, não "skip"
            raise
        pytest.skip("PostgreSQL de teste indisponível")
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config(str(API_DIR / "alembic.ini")), "head")
    return engine


@pytest.fixture
def session(engine):
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def demo(session):
    return seed_demo(session, uuid.uuid4(), AGENT_TOKEN)


@pytest.fixture
def client(demo):
    app = create_app()
    app.dependency_overrides[current_organization] = lambda: demo.organization_id
    with TestClient(app) as client:
        yield client


@pytest.fixture
def agent_token():
    return AGENT_TOKEN


@pytest.fixture
def agent_headers():
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}

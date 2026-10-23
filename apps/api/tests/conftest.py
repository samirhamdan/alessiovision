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
from alessio_api.models import Base, Membership, User
from alessio_api.security import hash_password
from alessio_api.seed import seed_demo
from alessio_api.settings import get_settings

TEST_DATABASE_URL = os.environ.get(
    "ALESSIO_TEST_DATABASE_URL",
    "postgresql+psycopg://alessio:alessio@localhost:5432/alessio_test",
)
AGENT_TOKEN = "alg_token-de-teste"
OWNER_EMAIL = "dona@example.com"
OWNER_PASSWORD = "senha-forte-de-teste"
WEB = {"X-Alessio-Client": "web"}
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine():
    os.environ["ALESSIO_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["ALESSIO_COOKIE_SECURE"] = "false"  # o TestClient fala HTTP
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
    return seed_demo(session, uuid.uuid4(), AGENT_TOKEN, OWNER_EMAIL, OWNER_PASSWORD)


def login(client: TestClient, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture
def anon_client(engine):
    with TestClient(create_app(), headers=WEB) as client:
        yield client


@pytest.fixture
def client(demo):
    """Cliente do painel autenticado como proprietário da organização demo."""
    with TestClient(create_app(), headers=WEB) as client:
        assert login(client, OWNER_EMAIL, OWNER_PASSWORD).status_code == 200
        yield client


@pytest.fixture
def agent_token():
    return AGENT_TOKEN


@pytest.fixture
def agent_headers():
    return {"Authorization": f"Bearer {AGENT_TOKEN}"}


MEMBER_PASSWORD = "senha-de-membro-123"


@pytest.fixture
def add_member(session):
    """Cria uma pessoa com papel numa organização: add_member(org_id, email, role) -> User."""

    def create(organization_id, email, role):
        user = User(
            email=email, name=email.split("@")[0], password_hash=hash_password(MEMBER_PASSWORD)
        )
        session.add(user)
        session.flush()
        session.add(Membership(organization_id=organization_id, user_id=user.id, role=role))
        session.commit()
        return user

    return create


@pytest.fixture
def client_as(demo, add_member):
    """Cliente logado com um papel na organização demo: client_as("viewer")."""
    clients = []

    def make(role, email=None):
        email = email or f"{role}-{uuid.uuid4().hex[:6]}@example.com"
        add_member(demo.organization_id, email, role)
        client = TestClient(create_app(), headers=WEB)
        client.__enter__()
        clients.append(client)
        assert login(client, email, MEMBER_PASSWORD).status_code == 200
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)

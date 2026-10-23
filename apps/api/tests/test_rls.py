"""O banco isola organizações mesmo quando a aplicação esquece um filtro."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from alessio_api.security import hash_token
from alessio_api.seed import seed_demo

TABLES = ("sites", "agents", "cameras", "zones", "event_rules", "audit_logs")


@pytest.fixture
def two_orgs(session):
    a = seed_demo(session, uuid.uuid4(), "alg_a")
    b = seed_demo(session, uuid.uuid4(), "alg_b")
    session.info.pop("organization_id", None)
    return a, b


def count(connection, table):
    return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_nothing_is_visible_without_an_organization(engine, two_orgs):
    with engine.connect() as connection:
        for table in TABLES:
            if table != "audit_logs":
                assert count(connection, table) == 0, table


def test_only_the_current_organization_is_visible(engine, two_orgs):
    a, b = two_orgs
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(a.organization_id)}
        )
        assert count(connection, "cameras") == 1
        visible = connection.execute(text("SELECT id FROM cameras")).scalar_one()
        assert visible == a.camera_id
        # Nem consultando o ID de outra organização diretamente.
        other = connection.execute(
            text("SELECT id FROM cameras WHERE id = :id"), {"id": b.camera_id}
        )
        assert other.first() is None


def test_writing_into_another_organization_is_refused(engine, two_orgs):
    a, b = two_orgs
    with pytest.raises(ProgrammingError, match="row-level security"), engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(a.organization_id)}
        )
        connection.execute(
            text(
                "INSERT INTO sites (id, organization_id, name, timezone, created_at) "
                "VALUES (:id, :org, 'x', 'UTC', now())"
            ),
            {"id": uuid.uuid4(), "org": b.organization_id},
        )


def test_updates_cannot_touch_other_organizations(engine, two_orgs):
    a, b = two_orgs
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(a.organization_id)}
        )
        changed = connection.execute(text("UPDATE cameras SET name = 'invadida'")).rowcount
        assert changed == 1  # só a câmera da própria organização
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(b.organization_id)}
        )
        assert connection.execute(text("SELECT name FROM cameras")).scalar_one() == "Entrada"


def test_agent_lookup_only_reveals_the_matching_agent(engine, two_orgs):
    a, _ = two_orgs
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.agent_lookup', :h, true)"), {"h": hash_token("alg_a")}
        )
        assert connection.execute(text("SELECT id FROM agents")).scalars().all() == [a.agent_id]
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.agent_lookup', :h, true)"), {"h": hash_token("errado")}
        )
        assert count(connection, "agents") == 0


def test_setting_does_not_leak_to_the_next_transaction(engine, two_orgs):
    a, _ = two_orgs
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("SELECT set_config('app.current_org', :o, true)"),
                {"o": str(a.organization_id)},
            )
            assert count(connection, "cameras") == 1
        with connection.begin():
            assert count(connection, "cameras") == 0

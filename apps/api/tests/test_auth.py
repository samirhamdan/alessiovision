import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from alessio_api.main import create_app
from alessio_api.models import UserSession
from alessio_api.seed import seed_demo
from alessio_api.settings import Settings

OWNER = ("dona@example.com", "senha-forte-de-teste")


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_sets_http_only_cookie_and_returns_permissions(anon_client, demo):
    response = login(anon_client, *OWNER)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "alessio_session=" in cookie
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    me = response.json()
    assert me["role"] == "owner"
    assert me["active_organization_id"] == str(demo.organization_id)
    assert "agents:manage" in me["permissions"]
    assert anon_client.get("/api/v1/me").json()["email"] == OWNER[0]


def test_email_is_case_insensitive(anon_client, demo):
    assert login(anon_client, OWNER[0].upper(), OWNER[1]).status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(anon_client, demo):
    wrong = login(anon_client, OWNER[0], "senha-errada-123")
    unknown = login(anon_client, "ninguem@example.com", "senha-errada-123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "E-mail ou senha incorretos."}


def test_account_locks_after_repeated_failures(anon_client, demo):
    for _ in range(5):
        assert login(anon_client, OWNER[0], "senha-errada-123").status_code == 401
    assert login(anon_client, *OWNER).status_code == 429


def test_panel_requires_session(anon_client, demo):
    for path in ("/api/v1/me", "/api/v1/occurrences", "/api/v1/cameras", "/api/v1/agents"):
        assert anon_client.get(path).status_code == 401, path


def test_logout_invalidates_the_session_on_the_server(anon_client, demo):
    login(anon_client, *OWNER)
    cookie = anon_client.cookies.get("alessio_session")
    assert anon_client.post("/api/v1/auth/logout").status_code == 204
    # Mesmo reapresentando o cookie antigo, a sessão não existe mais.
    anon_client.cookies.set("alessio_session", cookie)
    assert anon_client.get("/api/v1/me").status_code == 401


def test_expired_session_is_refused(anon_client, session, demo):
    login(anon_client, *OWNER)
    session.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    session.commit()
    assert anon_client.get("/api/v1/me").status_code == 401


def test_state_changes_require_the_client_header(demo):
    with TestClient(create_app()) as bare:
        assert login(bare, *OWNER).status_code == 403
        bare.headers["X-Alessio-Client"] = "web"
        assert login(bare, *OWNER).status_code == 200
        del bare.headers["X-Alessio-Client"]
        assert bare.post("/api/v1/sites", json={"name": "Filial"}).status_code == 403


def test_switching_organization_requires_membership(client, session, demo):
    other = seed_demo(session, uuid.uuid4(), "alg_outro", OWNER[0], OWNER[1], org_name="Filial Sul")
    stranger = seed_demo(session, uuid.uuid4(), "alg_estranho", org_name="Outra empresa")

    me = client.get("/api/v1/me").json()
    assert {m["organization_name"] for m in me["memberships"]} == {"Organização Demo", "Filial Sul"}

    denied = client.post(
        "/api/v1/session/organization", json={"organization_id": str(stranger.organization_id)}
    )
    assert denied.status_code == 404

    switched = client.post(
        "/api/v1/session/organization", json={"organization_id": str(other.organization_id)}
    )
    assert switched.status_code == 200
    [camera] = client.get("/api/v1/cameras").json()
    assert camera["id"] == str(other.camera_id)


def test_cookie_is_secure_by_default(monkeypatch):
    monkeypatch.delenv("ALESSIO_COOKIE_SECURE", raising=False)
    assert Settings(_env_file=None).cookie_secure is True


def test_admin_command_creates_organization_and_owner(anon_client, session):
    import pytest

    from alessio_api.admin import create_organization

    with pytest.raises(ValueError, match="10 caracteres"):
        create_organization(session, "Acme", "ana@example.com", "Ana", "curta")
    session.rollback()

    created = create_organization(
        session, "Acme", "Ana@Example.com", "Ana Souza", "senha-da-ana-123"
    )
    assert created.site.timezone == "America/Sao_Paulo"
    me = login(anon_client, "ana@example.com", "senha-da-ana-123").json()
    assert me["role"] == "owner"
    assert me["memberships"][0]["organization_name"] == "Acme"
    assert anon_client.get("/api/v1/sites").json()[0]["name"] == "Matriz"

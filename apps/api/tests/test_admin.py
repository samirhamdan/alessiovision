import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from alessio_api.main import create_app
from alessio_api.models import Agent
from alessio_api.seed import seed_demo
from alessio_api.tenancy import set_tenant

WEB = {"X-Alessio-Client": "web"}
NIGHT = "2026-10-24T02:00:00+00:00"


def enroll(client, code):
    return client.post(
        "/agent/v1/enroll", json={"code": code, "hostname": "mini-pc", "agent_version": "0.2.0"}
    )


def create_agent(client):
    site_id = client.get("/api/v1/sites").json()[0]["id"]
    response = client.post("/api/v1/agents", json={"name": "Recepção", "site_id": site_id})
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- Agentes --------------------------------------------------------------------------------


def test_agent_enrollment_lifecycle(client, anon_client):
    created = create_agent(client)
    assert created["agent"]["status"] == "pending"
    assert created["agent"]["enrollment_pending"] is True
    code = created["enrollment_code"]
    assert len(code) == 19 and code.count("-") == 3

    # O código é aceito sem hífens e em minúsculas, como alguém digitaria.
    result = enroll(anon_client, code.replace("-", "").lower())
    assert result.status_code == 200, result.text
    token = result.json()["token"]
    assert result.json()["organization_name"] == "Organização Demo"
    assert anon_client.get("/agent/v1/config", headers=bearer(token)).status_code == 200

    # Uso único.
    assert enroll(anon_client, code).status_code == 400

    [listed] = [a for a in client.get("/api/v1/agents").json() if a["id"] == created["agent"]["id"]]
    assert listed["status"] == "active"
    assert listed["hostname"] == "mini-pc"
    assert listed["enrollment_pending"] is False


def test_new_code_rotates_the_token_and_revoke_cuts_access(client, anon_client):
    created = create_agent(client)
    old_token = enroll(anon_client, created["enrollment_code"]).json()["token"]

    agent_id = created["agent"]["id"]
    rotated = client.post(f"/api/v1/agents/{agent_id}/enrollment-code").json()
    # Até o novo código ser usado, o token atual continua valendo (sem parar o agente).
    assert anon_client.get("/agent/v1/config", headers=bearer(old_token)).status_code == 200
    new_token = enroll(anon_client, rotated["enrollment_code"]).json()["token"]
    assert anon_client.get("/agent/v1/config", headers=bearer(old_token)).status_code == 401
    assert anon_client.get("/agent/v1/config", headers=bearer(new_token)).status_code == 200

    revoked = client.post(f"/api/v1/agents/{agent_id}/revoke")
    assert revoked.json()["status"] == "revoked"
    assert anon_client.get("/agent/v1/config", headers=bearer(new_token)).status_code == 401


def test_expired_code_is_refused(client, anon_client, session):
    created = create_agent(client)
    set_tenant(session, uuid.UUID(client.get("/api/v1/me").json()["active_organization_id"]))
    session.execute(
        update(Agent)
        .where(Agent.id == uuid.UUID(created["agent"]["id"]))
        .values(enrollment_expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    session.commit()
    response = enroll(anon_client, created["enrollment_code"])
    assert response.status_code == 400
    assert "Gere um novo código" in response.json()["detail"]


def test_agents_of_another_organization_are_invisible(client, session):
    other = seed_demo(session, uuid.uuid4(), "alg_outra")
    ids = {a["id"] for a in client.get("/api/v1/agents").json()}
    assert str(other.agent_id) not in ids
    assert client.post(f"/api/v1/agents/{other.agent_id}/revoke").status_code == 404


# --- Papéis ---------------------------------------------------------------------------------


def test_viewer_reads_but_cannot_manage(client_as, demo):
    viewer = client_as("viewer")
    assert viewer.get("/api/v1/occurrences").status_code == 200
    assert viewer.get("/api/v1/agents").status_code == 403
    assert viewer.post("/api/v1/sites", json={"name": "Filial"}).status_code == 403
    assert viewer.get("/api/v1/members").status_code == 403


def test_operator_can_acknowledge_occurrences(client_as, client, agent_headers, demo):
    occurrence_id = str(uuid.uuid4())
    message = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "agent_session_id": str(uuid.uuid4()),
        "sent_at": NIGHT,
        "type": "occurrence.opened",
        "payload": {
            "occurrence_id": occurrence_id,
            "camera_id": str(demo.camera_id),
            "zone_id": str(demo.zone_id),
            "rule_id": str(demo.rule_id),
            "rule_version": 1,
            "zone_version": 1,
            "event_type": "person.after_hours",
            "started_at": NIGHT,
            "confirmed_at": NIGHT,
            "people_count": 1,
            "max_confidence": 0.8,
        },
    }
    assert (
        client.post(
            "/agent/v1/messages", json={"messages": [message]}, headers=agent_headers
        ).status_code
        == 200
    )

    viewer = client_as("viewer")
    path = f"/api/v1/occurrences/{occurrence_id}/review"
    assert viewer.patch(path, json={"review_status": "acknowledged"}).status_code == 403

    operator = client_as("operator")
    reviewed = operator.patch(path, json={"review_status": "acknowledged"})
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "acknowledged"
    assert reviewed.json()["reviewed_at"] is not None

    actions = [log["action"] for log in client.get("/api/v1/audit-logs").json()]
    assert "occurrence.acknowledged" in actions


def test_review_of_another_organizations_occurrence_is_not_found(client):
    assert (
        client.patch(
            f"/api/v1/occurrences/{uuid.uuid4()}/review", json={"review_status": "resolved"}
        ).status_code
        == 404
    )


# --- Membros e convites ---------------------------------------------------------------------


def test_invite_accept_and_login(client, demo):
    added = client.post(
        "/api/v1/members", json={"email": "Joao@Example.com", "name": "João", "role": "operator"}
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["member"]["status"] == "invited"
    token = body["invite_token"]
    assert token

    with TestClient(create_app(), headers=WEB) as invitee:
        weak = invitee.post(
            "/api/v1/auth/accept-invite", json={"token": token, "name": "João", "password": "curta"}
        )
        assert weak.status_code == 422
        accepted = invitee.post(
            "/api/v1/auth/accept-invite",
            json={"token": token, "name": "João Lima", "password": "uma-senha-boa-123"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["role"] == "operator"
        assert invitee.get("/api/v1/occurrences").status_code == 200
        # O convite é de uso único.
        again = invitee.post(
            "/api/v1/auth/accept-invite",
            json={"token": token, "name": "x", "password": "outra-senha-boa-123"},
        )
        assert again.status_code == 400

    members = {m["email"]: m for m in client.get("/api/v1/members").json()}
    assert members["joao@example.com"]["status"] == "active"
    assert members["joao@example.com"]["name"] == "João Lima"


def test_existing_account_is_added_without_invite(client, session, demo, add_member):
    other = seed_demo(session, uuid.uuid4(), "alg_outra")
    add_member(other.organization_id, "ana@example.com", "admin")
    added = client.post(
        "/api/v1/members", json={"email": "ana@example.com", "name": "Ana", "role": "viewer"}
    ).json()
    assert added["invite_token"] is None
    assert added["member"]["status"] == "active"
    duplicate = client.post(
        "/api/v1/members", json={"email": "ana@example.com", "name": "Ana", "role": "viewer"}
    )
    assert duplicate.status_code == 409


def test_admin_cannot_manage_owners(client_as, demo):
    admin = client_as("admin")
    assert (
        admin.post(
            "/api/v1/members", json={"email": "novo@example.com", "name": "N", "role": "owner"}
        ).status_code
        == 403
    )
    owner_id = next(
        m["user_id"] for m in admin.get("/api/v1/members").json() if m["role"] == "owner"
    )
    assert admin.patch(f"/api/v1/members/{owner_id}", json={"role": "viewer"}).status_code == 403
    assert admin.delete(f"/api/v1/members/{owner_id}").status_code == 403
    created = admin.post(
        "/api/v1/members", json={"email": "op@example.com", "name": "Op", "role": "operator"}
    )
    assert created.status_code == 201


def test_last_owner_cannot_leave_or_be_demoted(client):
    me = client.get("/api/v1/me").json()
    assert client.patch(f"/api/v1/members/{me['id']}", json={"role": "admin"}).status_code == 409
    assert client.delete(f"/api/v1/members/{me['id']}").status_code == 409


def test_removed_member_loses_access_immediately(client, client_as):
    operator = client_as("operator", email="saindo@example.com")
    assert operator.get("/api/v1/occurrences").status_code == 200
    user_id = next(
        m["user_id"]
        for m in client.get("/api/v1/members").json()
        if m["email"] == "saindo@example.com"
    )
    assert client.delete(f"/api/v1/members/{user_id}").status_code == 204
    assert operator.get("/api/v1/occurrences").status_code == 403
    assert operator.get("/api/v1/me").json()["active_organization_id"] is None


def test_audit_log_records_administrative_actions(client):
    create_agent(client)
    client.post(
        "/api/v1/members", json={"email": "aud@example.com", "name": "Aud", "role": "viewer"}
    )
    logs = client.get("/api/v1/audit-logs").json()
    actions = {log["action"] for log in logs}
    assert {"agent.created", "member.added"} <= actions
    assert all("token" not in str(log["details"]).lower() for log in logs)

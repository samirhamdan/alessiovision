import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from alessio_api.models import Camera, CameraService
from alessio_api.tenancy import set_tenant

NIGHT = "2026-10-24T02:00:00+00:00"


def base(org_id):
    return f"/api/v1/platform/organizations/{org_id}"


@pytest.fixture
def camera2(session, demo):
    """Segunda câmera do agente demo, ainda sem nenhum serviço Vision."""
    set_tenant(session, demo.organization_id)
    demo_camera = session.get(Camera, demo.camera_id)
    camera = Camera(
        organization_id=demo.organization_id,
        site_id=demo_camera.site_id,
        agent_id=demo.agent_id,
        name="Estoque",
        source_ref="estoque",
    )
    session.add(camera)
    session.commit()
    return camera.id


@pytest.fixture
def contract(staff_client, demo):
    response = staff_client.post(
        f"{base(demo.organization_id)}/contracts",
        json={"number": "CT-2026-002", "starts_on": "2026-10-01"},
    )
    [created] = [c for c in response.json() if c["number"] == "CT-2026-002"]
    return created


def camera_entry(overview, camera_id):
    [entry] = [c for c in overview["cameras"] if c["camera_id"] == str(camera_id)]
    return entry


def config_cameras(client, agent_headers):
    return {
        c["name"]: c["services"]
        for c in client.get("/agent/v1/config", headers=agent_headers).json()["cameras"]
    }


def test_camera_without_vision_is_not_sent_to_the_agent(client, agent_headers, camera2):
    # A câmera demo tem as duas modalidades pelo seed; a nova não tem nenhuma.
    assert config_cameras(client, agent_headers) == {"Entrada": ["operation", "security"]}


def test_contract_one_service_per_camera_with_negotiated_value(
    staff_client, client, agent_headers, demo, camera2, contract
):
    response = staff_client.post(
        f"{base(demo.organization_id)}/services",
        json={
            "camera_id": str(camera2),
            "service": "operation",
            "contract_id": contract["id"],
            "monthly_fee_cents": 8900,
        },
    )
    assert response.status_code == 201, response.text
    entry = camera_entry(response.json(), camera2)
    assert entry["operation"]["state"] == "active"
    assert entry["operation"]["monthly_fee_cents"] == 8900
    assert entry["security"] is None

    # O agente passa a receber a câmera, só com Operação.
    assert config_cameras(client, agent_headers)["Estoque"] == ["operation"]

    # Contrato soma o serviço; visão geral soma serviços + comodato.
    [ct] = [
        c
        for c in staff_client.get(f"{base(demo.organization_id)}/contracts").json()
        if c["number"] == "CT-2026-002"
    ]
    assert ct["monthly_fee_cents"] == 8900 and ct["service_count"] == 1
    [org] = [
        o
        for o in staff_client.get("/api/v1/platform/organizations").json()
        if o["id"] == str(demo.organization_id)
    ]
    assert org["services_monthly_cents"] == 8900
    assert org["total_monthly_cents"] == 8900
    assert org["cameras_with_vision"] == 2

    # Duas vezes a mesma modalidade na mesma câmera, não.
    again = staff_client.post(
        f"{base(demo.organization_id)}/services",
        json={"camera_id": str(camera2), "service": "operation", "contract_id": contract["id"]},
    )
    assert again.status_code == 409


def test_trial_lasts_three_days_and_only_once(staff_client, demo, camera2):
    started = staff_client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "security"},
    )
    assert started.status_code == 201, started.text
    trial = camera_entry(started.json(), camera2)["security"]
    assert trial["source"] == "trial" and trial["monthly_fee_cents"] is None
    length = datetime.fromisoformat(trial["ends_at"]) - datetime.fromisoformat(trial["starts_at"])
    assert length == timedelta(days=3)

    line_id = trial["id"]
    ended = staff_client.post(f"{base(demo.organization_id)}/services/{line_id}/end", json={})
    assert camera_entry(ended.json(), camera2)["security"] is None
    assert camera_entry(ended.json(), camera2)["trials_used"] == ["security"]

    again = staff_client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "security"},
    )
    assert again.status_code == 409
    assert "já usou o teste" in again.json()["detail"]
    # A outra modalidade ainda pode ser testada.
    other = staff_client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "operation"},
    )
    assert other.status_code == 201


def test_contracting_during_trial_replaces_the_trial(staff_client, demo, camera2, contract):
    staff_client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "security"},
    )
    contracted = staff_client.post(
        f"{base(demo.organization_id)}/services",
        json={
            "camera_id": str(camera2),
            "service": "security",
            "contract_id": contract["id"],
            "monthly_fee_cents": 12000,
        },
    ).json()
    assert camera_entry(contracted, camera2)["security"]["source"] == "contract"
    states = sorted(
        (line["source"], line["state"])
        for line in contracted["history"]
        if line["camera_id"] == str(camera2)
    )
    assert states == [("contract", "active"), ("trial", "ended")]


def test_expired_trial_stops_the_agent(staff_client, client, agent_headers, session, demo, camera2):
    staff_client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "security"},
    )
    assert "Estoque" in config_cameras(client, agent_headers)
    set_tenant(session, demo.organization_id)
    past = datetime.now(UTC) - timedelta(minutes=1)
    session.execute(
        update(CameraService)
        .where(CameraService.camera_id == camera2)
        .values(starts_at=past - timedelta(days=3), ends_at=past)
    )
    session.commit()
    assert "Estoque" not in config_cameras(client, agent_headers)


def test_ending_the_contract_ends_its_services(staff_client, demo, camera2, contract):
    staff_client.post(
        f"{base(demo.organization_id)}/services",
        json={"camera_id": str(camera2), "service": "operation", "contract_id": contract["id"]},
    )
    staff_client.post(
        f"{base(demo.organization_id)}/contracts/{contract['id']}/end",
        json={"ends_on": "2026-10-02"},
    )
    overview = staff_client.get(f"{base(demo.organization_id)}/services").json()
    assert camera_entry(overview, camera2)["operation"] is None
    # E contrato encerrado não aceita serviço novo.
    refused = staff_client.post(
        f"{base(demo.organization_id)}/services",
        json={"camera_id": str(camera2), "service": "security", "contract_id": contract["id"]},
    )
    assert refused.status_code == 422


def test_cloud_refuses_data_from_services_not_contracted(
    client, agent_headers, demo, camera2, session
):
    # A câmera demo perde a Segurança; Operação continua.
    set_tenant(session, demo.organization_id)
    session.execute(
        update(CameraService)
        .where(CameraService.camera_id == demo.camera_id, CameraService.service == "security")
        .values(ends_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    session.commit()

    def envelope(type_, payload):
        return {
            "schema_version": "1.0",
            "message_id": str(uuid.uuid4()),
            "agent_session_id": str(uuid.uuid4()),
            "sent_at": NIGHT,
            "type": type_,
            "payload": payload,
        }

    opened = envelope(
        "occurrence.opened",
        {
            "occurrence_id": str(uuid.uuid4()),
            "camera_id": str(demo.camera_id),
            "zone_id": str(demo.zone_id),
            "rule_id": str(demo.rule_id),
            "rule_version": 1,
            "zone_version": 1,
            "event_type": "person.after_hours",
            "started_at": NIGHT,
            "confirmed_at": NIGHT,
            "people_count": 1,
            "max_confidence": 0.9,
        },
    )
    metric = envelope(
        "metrics.zone_1m",
        {
            "camera_id": str(demo.camera_id),
            "zone_id": str(demo.zone_id),
            "bucket_start": NIGHT,
            "analyzed_seconds": 60,
            "occupancy_avg": 1,
            "occupancy_max": 1,
        },
    )
    results = client.post(
        "/agent/v1/messages", json={"messages": [opened, metric]}, headers=agent_headers
    ).json()["results"]
    assert [r["status"] for r in results] == ["rejected", "accepted"]
    assert "Vision Segurança" in results[0]["reason"]
    assert config_cameras(client, agent_headers)["Entrada"] == ["operation"]


def test_client_sees_services_and_camera_badges(client, client_as, demo):
    overview = client.get("/api/v1/services").json()
    entry = camera_entry(overview, demo.camera_id)
    assert entry["security"]["state"] == "active" and entry["operation"]["state"] == "active"
    [camera] = client.get("/api/v1/cameras").json()
    assert camera["services"] == ["operation", "security"]
    assert client_as("viewer").get("/api/v1/services").status_code == 403


def test_only_staff_manages_services(client, demo, camera2):
    response = client.post(
        f"{base(demo.organization_id)}/services/trial",
        json={"camera_id": str(camera2), "service": "security"},
    )
    assert response.status_code == 403

"""Item 5 da R2: histórico depois do fim do serviço."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from alessio_api.admin import purge_expired_history
from alessio_api.models import CameraService
from alessio_api.tenancy import set_tenant

NIGHT = "2026-10-24T02:00:00+00:00"


def envelope(type_, payload):
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "agent_session_id": str(uuid.uuid4()),
        "sent_at": NIGHT,
        "type": type_,
        "payload": payload,
    }


def record_data(client, agent_headers, demo):
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
    response = client.post(
        "/agent/v1/messages", json={"messages": [opened, metric]}, headers=agent_headers
    )
    assert [r["status"] for r in response.json()["results"]] == ["accepted", "accepted"]


def end_services(session, demo, days_ago):
    set_tenant(session, demo.organization_id)
    ended = datetime.now(UTC) - timedelta(days=days_ago)
    session.execute(
        update(CameraService).where(CameraService.camera_id == demo.camera_id).values(ends_at=ended)
    )
    session.commit()


def metrics(client, demo):
    return client.get(
        f"/api/v1/zones/{demo.zone_id}/metrics",
        params={"from": "2026-10-24T00:00:00Z", "to": "2026-10-25T00:00:00Z"},
    ).json()


def test_history_stays_readable_for_30_days(client, agent_headers, session, demo):
    record_data(client, agent_headers, demo)
    end_services(session, demo, days_ago=10)
    assert len(client.get("/api/v1/occurrences").json()) == 1
    assert len(metrics(client, demo)) == 1
    [camera] = client.get("/api/v1/cameras").json()
    assert camera["services"] == []
    assert set(camera["history_until"]) == {"security", "operation"}


def test_history_is_hidden_after_30_days_and_purged_after_90(client, agent_headers, session, demo):
    record_data(client, agent_headers, demo)
    end_services(session, demo, days_ago=31)
    assert client.get("/api/v1/occurrences").json() == []
    assert metrics(client, demo) == []
    # Ainda não apagou: renovar traria de volta.
    assert purge_expired_history(session) == {"occurrences": 0, "metrics": 0}

    end_services(session, demo, days_ago=91)
    assert purge_expired_history(session) == {"occurrences": 1, "metrics": 1}
    actions = [log["action"] for log in client.get("/api/v1/audit-logs").json()]
    assert actions.count("history.purged") == 2


def test_renewing_within_90_days_brings_history_back(
    client, agent_headers, staff_client, session, demo
):
    record_data(client, agent_headers, demo)
    end_services(session, demo, days_ago=45)
    assert client.get("/api/v1/occurrences").json() == []
    contract = staff_client.post(
        f"/api/v1/platform/organizations/{demo.organization_id}/contracts",
        json={"number": "RENOVA-1", "starts_on": "2026-10-01"},
    ).json()
    [renewal] = [c for c in contract if c["number"] == "RENOVA-1"]
    staff_client.post(
        f"/api/v1/platform/organizations/{demo.organization_id}/services",
        json={
            "camera_id": str(demo.camera_id),
            "service": "security",
            "contract_id": renewal["id"],
        },
    )
    assert len(client.get("/api/v1/occurrences").json()) == 1
    assert purge_expired_history(session)["occurrences"] == 0

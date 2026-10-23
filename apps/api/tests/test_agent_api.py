import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from alessio_api.models import Camera, Occurrence, OccurrenceUpdate, ZoneMetric1m
from alessio_api.seed import seed_demo

NIGHT = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)


def envelope(type_, payload):
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "agent_session_id": str(uuid.uuid4()),
        "sent_at": datetime.now(UTC).isoformat(),
        "type": type_,
        "payload": payload,
    }


def opened(demo, occurrence_id=None, camera_id=None):
    return envelope(
        "occurrence.opened",
        {
            "occurrence_id": str(occurrence_id or uuid.uuid4()),
            "camera_id": str(camera_id or demo.camera_id),
            "zone_id": str(demo.zone_id),
            "rule_id": str(demo.rule_id),
            "rule_version": 1,
            "zone_version": 1,
            "event_type": "person.after_hours",
            "started_at": NIGHT.isoformat(),
            "confirmed_at": (NIGHT + timedelta(seconds=3)).isoformat(),
            "people_count": 1,
            "max_confidence": 0.8,
        },
    )


def post(client, headers, *messages):
    response = client.post("/agent/v1/messages", json={"messages": list(messages)}, headers=headers)
    assert response.status_code == 200, response.text
    return [r["status"] for r in response.json()["results"]]


def test_agent_endpoints_require_valid_token(client):
    assert client.get("/agent/v1/config").status_code == 401
    bad = {"Authorization": "Bearer alg_errado"}
    assert client.get("/agent/v1/config", headers=bad).status_code == 401


def test_revoked_agent_is_refused(client, session, demo, agent_headers):
    from alessio_api.models import Agent

    session.get(Agent, demo.agent_id).status = "revoked"
    session.commit()
    assert client.get("/agent/v1/config", headers=agent_headers).status_code == 401


def test_config_contains_cameras_zones_and_rules_with_etag(client, demo, agent_headers):
    response = client.get("/agent/v1/config", headers=agent_headers)
    assert response.status_code == 200
    config = response.json()
    assert config["agent_id"] == str(demo.agent_id)
    [camera] = config["cameras"]
    assert camera["source_ref"] == "demo"
    assert "rtsp" not in response.text
    assert camera["rules"][0]["schedule"]["timezone"] == "America/Sao_Paulo"
    assert response.headers["ETag"] == f'"{config["config_version"]}"'

    cached = client.get(
        "/agent/v1/config", headers={**agent_headers, "If-None-Match": response.headers["ETag"]}
    )
    assert cached.status_code == 304


def test_occurrence_lifecycle_and_idempotency(client, session, demo, agent_headers):
    occurrence_id = uuid.uuid4()
    first = opened(demo, occurrence_id)
    assert post(client, agent_headers, first) == ["accepted"]
    assert post(client, agent_headers, first) == ["duplicate"]

    update = envelope(
        "occurrence.updated",
        {
            "occurrence_id": str(occurrence_id),
            "observed_at": (NIGHT + timedelta(seconds=10)).isoformat(),
            "people_count": 3,
            "max_people": 3,
        },
    )
    close = envelope(
        "occurrence.closed",
        {
            "occurrence_id": str(occurrence_id),
            "ended_at": (NIGHT + timedelta(seconds=30)).isoformat(),
            "max_people": 3,
            "reason": "cleared",
        },
    )
    assert post(client, agent_headers, update, close) == ["accepted", "accepted"]

    occurrence = session.get(Occurrence, occurrence_id)
    session.refresh(occurrence)
    assert occurrence.state == "closed"
    assert occurrence.max_people == 3
    assert occurrence.ended_at == NIGHT + timedelta(seconds=30)
    assert occurrence.organization_id == demo.organization_id
    history = session.scalars(
        select(OccurrenceUpdate.type).where(OccurrenceUpdate.occurrence_id == occurrence_id)
    ).all()
    assert sorted(history) == ["occurrence.closed", "occurrence.opened", "occurrence.updated"]

    [listed] = client.get("/api/v1/occurrences").json()
    assert listed["id"] == str(occurrence_id)
    assert listed["camera_name"] == "Entrada"
    assert listed["state"] == "closed"


def test_agent_cannot_write_to_another_organization(client, session, demo, agent_headers):
    other = seed_demo(session, uuid.uuid4(), "alg_outro-agente")
    good = opened(demo)
    foreign = opened(demo, camera_id=other.camera_id)
    unknown_close = envelope(
        "occurrence.closed",
        {
            "occurrence_id": str(uuid.uuid4()),
            "ended_at": NIGHT.isoformat(),
            "max_people": 1,
            "reason": "cleared",
        },
    )
    assert post(client, agent_headers, good, foreign, unknown_close) == [
        "accepted",
        "rejected",
        "rejected",
    ]
    assert session.scalar(select(Occurrence).where(Occurrence.camera_id == other.camera_id)) is None

    # Um agente também não consegue encerrar ocorrências de outro agente.
    other_occurrence = opened(other)
    other_headers = {"Authorization": "Bearer alg_outro-agente"}
    assert post(client, other_headers, other_occurrence) == ["accepted"]
    hijack = envelope(
        "occurrence.closed",
        {
            "occurrence_id": other_occurrence["payload"]["occurrence_id"],
            "ended_at": NIGHT.isoformat(),
            "max_people": 1,
            "reason": "cleared",
        },
    )
    assert post(client, agent_headers, hijack) == ["rejected"]


def test_dashboard_only_lists_its_organization(client, session, demo, agent_headers):
    other = seed_demo(session, uuid.uuid4(), "alg_outro-agente")
    post(client, {"Authorization": "Bearer alg_outro-agente"}, opened(other))
    assert client.get("/api/v1/occurrences").json() == []
    post(client, agent_headers, opened(demo))
    assert len(client.get("/api/v1/occurrences").json()) == 1


def test_shadow_occurrences_are_hidden_by_default(client, demo, agent_headers):
    message = opened(demo)
    message["payload"]["shadow"] = True
    post(client, agent_headers, message)
    assert client.get("/api/v1/occurrences").json() == []
    assert len(client.get("/api/v1/occurrences", params={"include_shadow": True}).json()) == 1


def test_partial_minutes_are_merged_with_time_weighting(client, session, demo, agent_headers):
    def metric(seconds, avg, peak):
        return envelope(
            "metrics.zone_1m",
            {
                "camera_id": str(demo.camera_id),
                "zone_id": str(demo.zone_id),
                "bucket_start": NIGHT.isoformat(),
                "analyzed_seconds": seconds,
                "occupancy_avg": avg,
                "occupancy_max": peak,
            },
        )

    # Agente reiniciado no meio do minuto: duas partes do mesmo intervalo.
    assert post(client, agent_headers, metric(20, 1.0, 1), metric(40, 4.0, 5)) == [
        "accepted",
        "accepted",
    ]
    row = session.get(ZoneMetric1m, (demo.zone_id, NIGHT))
    assert row.analyzed_seconds == 60
    assert row.occupancy_avg == 3.0
    assert row.occupancy_max == 5

    series = client.get(
        f"/api/v1/zones/{demo.zone_id}/metrics",
        params={"from": NIGHT.isoformat(), "to": (NIGHT + timedelta(hours=1)).isoformat()},
    ).json()
    assert series == [
        {
            "bucket_start": "2026-10-24T02:00:00Z",
            "analyzed_seconds": 60.0,
            "occupancy_avg": 3.0,
            "occupancy_max": 5,
        }
    ]


def test_heartbeat_updates_camera_freshness(client, session, demo, agent_headers):
    beat = envelope(
        "heartbeat",
        {
            "agent_version": "0.1.0",
            "cameras": [
                {
                    "camera_id": str(demo.camera_id),
                    "status": "disconnected",
                    "last_frame_at": NIGHT.isoformat(),
                    "detail": "stream interrompido",
                }
            ],
        },
    )
    assert post(client, agent_headers, beat) == ["accepted"]
    camera = session.get(Camera, demo.camera_id)
    session.refresh(camera)
    assert camera.status == "disconnected"
    [listed] = client.get("/api/v1/cameras").json()
    assert listed["last_frame_at"] == "2026-10-24T02:00:00Z"
    assert listed["agent_last_seen_at"] is not None


def test_invalid_schema_is_refused_whole(client, demo, agent_headers):
    message = opened(demo)
    message["schema_version"] = "9.9"
    response = client.post(
        "/agent/v1/messages", json={"messages": [message]}, headers=agent_headers
    )
    assert response.status_code == 422

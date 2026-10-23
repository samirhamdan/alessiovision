from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from alessio_contracts import (
    AfterHoursPresenceRule,
    AgentMessage,
    CameraConfig,
    MessageBatch,
    Schedule,
    ScheduleWindow,
    ZoneConfig,
    ZoneMetrics1m,
)

WEEKDAYS = [0, 1, 2, 3, 4]


def business_hours() -> Schedule:
    return Schedule(
        timezone="America/Sao_Paulo",
        windows=[ScheduleWindow(days=WEEKDAYS, start=time(8), end=time(18))],
        holidays=[date(2026, 11, 2)],
    )


def test_schedule_uses_site_timezone():
    schedule = business_hours()
    # Sexta 23/10/2026, 12:00 em São Paulo = 15:00 UTC.
    assert schedule.is_business_time(datetime(2026, 10, 23, 15, 0, tzinfo=UTC))
    # 20:00 em São Paulo = 23:00 UTC: fora do expediente.
    assert not schedule.is_business_time(datetime(2026, 10, 23, 23, 0, tzinfo=UTC))
    # 06:00 UTC de sábado = 03:00 de sábado em São Paulo.
    assert not schedule.is_business_time(datetime(2026, 10, 24, 6, 0, tzinfo=UTC))


def test_schedule_holiday_is_after_hours():
    # Segunda 02/11/2026 (Finados), 12:00 em São Paulo.
    assert not business_hours().is_business_time(datetime(2026, 11, 2, 15, 0, tzinfo=UTC))


def test_overnight_window_spans_midnight():
    schedule = Schedule(
        timezone="UTC",
        windows=[ScheduleWindow(days=[4], start=time(22), end=time(6))],  # sexta 22h-6h
    )
    assert schedule.is_business_time(datetime(2026, 10, 23, 23, 0, tzinfo=UTC))  # sexta
    assert schedule.is_business_time(datetime(2026, 10, 24, 5, 59, tzinfo=UTC))  # sábado
    assert not schedule.is_business_time(datetime(2026, 10, 24, 6, 0, tzinfo=UTC))
    assert not schedule.is_business_time(datetime(2026, 10, 22, 23, 0, tzinfo=UTC))  # quinta


def test_schedule_rejects_unknown_timezone_and_naive_datetimes():
    with pytest.raises(ValidationError):
        Schedule(timezone="Mars/Olympus")
    with pytest.raises(ValueError):
        business_hours().is_business_time(datetime(2026, 10, 23, 12, 0))


def test_zone_polygon_must_be_normalized():
    with pytest.raises(ValidationError):
        ZoneConfig(id=uuid4(), name="z", version=1, polygon=[(0, 0), (1.2, 0), (1, 1)])
    with pytest.raises(ValidationError):
        ZoneConfig(id=uuid4(), name="z", version=1, polygon=[(0, 0), (1, 1)])


def test_camera_rejects_rule_for_foreign_zone():
    zone = ZoneConfig(id=uuid4(), name="z", version=1, polygon=[(0, 0), (1, 0), (1, 1)])
    rule = AfterHoursPresenceRule(id=uuid4(), version=1, zone_id=uuid4(), schedule=business_hours())
    with pytest.raises(ValidationError, match="zona de outra câmera"):
        CameraConfig(id=uuid4(), name="c", source_ref="cam", zones=[zone], rules=[rule])


def test_metrics_bucket_must_be_aligned():
    with pytest.raises(ValidationError):
        ZoneMetrics1m(
            camera_id=uuid4(),
            zone_id=uuid4(),
            bucket_start=datetime(2026, 10, 23, 12, 0, 30, tzinfo=UTC),
            analyzed_seconds=10,
            occupancy_avg=1,
            occupancy_max=1,
        )


def test_message_union_dispatches_on_type_and_round_trips():
    raw = {
        "schema_version": "1.0",
        "message_id": str(uuid4()),
        "agent_session_id": str(uuid4()),
        "sent_at": "2026-10-23T23:00:00Z",
        "type": "occurrence.closed",
        "payload": {
            "occurrence_id": str(uuid4()),
            "ended_at": "2026-10-23T23:00:00Z",
            "max_people": 2,
            "reason": "cleared",
        },
    }
    adapter = TypeAdapter(AgentMessage)
    message = adapter.validate_python(raw)
    assert type(message).__name__ == "OccurrenceClosedMessage"
    assert adapter.validate_json(adapter.dump_json(message)) == message


def test_batch_rejects_unknown_schema_version_and_extra_fields():
    base = {
        "message_id": str(uuid4()),
        "agent_session_id": str(uuid4()),
        "sent_at": "2026-10-23T23:00:00Z",
        "type": "heartbeat",
        "payload": {"agent_version": "0.1.0"},
    }
    MessageBatch.model_validate({"messages": [{**base, "schema_version": "1.0"}]})
    with pytest.raises(ValidationError):
        MessageBatch.model_validate({"messages": [{**base, "schema_version": "2.0"}]})
    with pytest.raises(ValidationError):
        MessageBatch.model_validate({"messages": [{**base, "organization_id": str(uuid4())}]})

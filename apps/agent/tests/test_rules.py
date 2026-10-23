from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from alessio_agent.rules import AfterHoursPresenceEngine
from alessio_contracts import (
    AfterHoursPresenceRule,
    OccurrenceClosed,
    OccurrenceOpened,
    OccurrenceUpdated,
    Schedule,
    ScheduleWindow,
    ZoneConfig,
)

# Sexta 23/10/2026 às 23:00 em São Paulo (02:00 UTC de sábado): fora do expediente.
NIGHT = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)
# Expediente de segunda a sexta, 08:00-18:00.
SCHEDULE = Schedule(
    timezone="America/Sao_Paulo",
    windows=[ScheduleWindow(days=[0, 1, 2, 3, 4], start=time(8), end=time(18))],
)
ZONE = ZoneConfig(id=uuid4(), name="z", version=3, polygon=[(0, 0), (1, 0), (1, 1), (0, 1)])


def engine(**overrides) -> AfterHoursPresenceEngine:
    params = dict(
        id=uuid4(),
        version=2,
        zone_id=ZONE.id,
        schedule=SCHEDULE,
        min_duration_seconds=3,
        gap_tolerance_seconds=2,
        clear_after_seconds=10,
    )
    params.update(overrides)
    return AfterHoursPresenceEngine(uuid4(), ZONE, AfterHoursPresenceRule(**params))


def feed(eng, start, seconds, people, fps=5):
    out = []
    for i in range(int(seconds * fps)):
        out += eng.observe(start + timedelta(seconds=i / fps), people, 0.8)
    return out


def test_presence_lifecycle_produces_one_occurrence():
    eng = engine()
    out = feed(eng, NIGHT, 5, people=1)
    opened = [m for m in out if isinstance(m, OccurrenceOpened)]
    assert len(opened) == 1
    assert opened[0].started_at == NIGHT
    assert opened[0].confirmed_at == NIGHT + timedelta(seconds=3)
    assert opened[0].rule_version == 2 and opened[0].zone_version == 3

    out = feed(eng, NIGHT + timedelta(seconds=5), 5, people=2)
    assert [type(m) for m in out] == [OccurrenceUpdated]
    assert out[0].max_people == 2

    last_seen = NIGHT + timedelta(seconds=9.8)
    out = feed(eng, NIGHT + timedelta(seconds=10), 15, people=0)
    assert [type(m) for m in out] == [OccurrenceClosed]
    closed = out[0]
    assert closed.occurrence_id == opened[0].occurrence_id
    assert closed.reason == "cleared"
    assert closed.ended_at == last_seen
    assert closed.max_people == 2
    assert eng.active_occurrence_id is None


def test_short_presence_does_not_open():
    eng = engine()
    out = feed(eng, NIGHT, 2, people=1)
    out += feed(eng, NIGHT + timedelta(seconds=2), 5, people=0)
    out += feed(eng, NIGHT + timedelta(seconds=7), 2, people=1)
    assert out == []


def test_detection_flicker_within_tolerance_still_opens():
    eng = engine()
    out = []
    for i in range(25):  # 5 s a 5 fps, com um quadro sim e outro não
        out += eng.observe(NIGHT + timedelta(seconds=i / 5), i % 2, 0.8)
    assert any(isinstance(m, OccurrenceOpened) for m in out)


def test_business_hours_presence_is_ignored():
    noon_friday = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
    assert feed(engine(), noon_friday, 30, people=3) == []


def test_occurrence_closes_when_business_hours_start():
    eng = engine()
    before_open = datetime(2026, 10, 26, 10, 59, 50, tzinfo=UTC)  # segunda 07:59:50 em SP
    out = feed(eng, before_open, 20, people=1)
    closed = [m for m in out if isinstance(m, OccurrenceClosed)]
    assert len(closed) == 1 and closed[0].reason == "schedule"
    assert closed[0].ended_at == datetime(2026, 10, 26, 11, 0, tzinfo=UTC)


def test_disabled_rule_is_silent_and_shadow_is_propagated():
    assert feed(engine(enabled=False), NIGHT, 10, people=1) == []
    out = feed(engine(shadow=True), NIGHT, 5, people=1)
    assert out[0].shadow is True


def test_close_on_signal_loss_uses_last_observation():
    eng = engine()
    feed(eng, NIGHT, 5, people=1)
    out = eng.close(NIGHT + timedelta(minutes=5), "signal_lost")
    assert len(out) == 1 and out[0].reason == "signal_lost"
    assert out[0].ended_at == NIGHT + timedelta(seconds=4.8)
    assert eng.close(NIGHT + timedelta(minutes=6), "shutdown") == []


def test_zero_min_duration_opens_on_first_frame():
    out = engine(min_duration_seconds=0).observe(NIGHT, 1, 0.5)
    assert len(out) == 1 and isinstance(out[0], OccurrenceOpened)

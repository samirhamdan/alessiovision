from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import numpy as np
import pytest

from alessio_agent.pipeline import CameraPipeline
from alessio_agent.sources import Frame
from alessio_agent.testing import CENTER_PERSON, ScriptedDetector
from alessio_contracts import (
    AfterHoursPresenceRule,
    CameraConfig,
    OccurrenceClosed,
    OccurrenceOpened,
    Schedule,
    ScheduleWindow,
    ZoneConfig,
    ZoneMetrics1m,
)

NIGHT = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)


def camera(services):
    zone = ZoneConfig(id=uuid4(), name="z", version=1, polygon=[(0, 0), (1, 0), (1, 1), (0, 1)])
    rule = AfterHoursPresenceRule(
        id=uuid4(),
        version=1,
        zone_id=zone.id,
        min_duration_seconds=1,
        schedule=Schedule(
            timezone="America/Sao_Paulo",
            windows=[ScheduleWindow(days=[0, 1, 2, 3, 4], start=time(8), end=time(18))],
        ),
    )
    return CameraConfig(
        id=uuid4(), name="c", source_ref="c", zones=[zone], rules=[rule], services=services
    )


@pytest.mark.parametrize(
    "services, expected",
    [
        (["security", "operation"], {OccurrenceOpened, ZoneMetrics1m}),
        (["security"], {OccurrenceOpened}),
        (["operation"], {ZoneMetrics1m}),
    ],
)
def test_pipeline_runs_only_contracted_services(services, expected):
    emitted = []
    pipeline = CameraPipeline(
        camera(services), ScriptedDetector(lambda i: [CENTER_PERSON]), emitted.append
    )
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    for i in range(25):  # 5 s a 5 fps
        pipeline.process(Frame(NIGHT + timedelta(seconds=i / 5), image))
    pipeline.finish(NIGHT + timedelta(seconds=5), "shutdown")
    kinds = {type(p) for p in emitted} - {OccurrenceClosed}
    assert kinds == expected

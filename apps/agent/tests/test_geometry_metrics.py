import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np

from alessio_agent.detection import Detection, HogPersonDetector
from alessio_agent.geometry import count_in_zone, point_in_polygon
from alessio_agent.metrics import OccupancyAggregator
from alessio_agent.sources import FileSource, redact
from alessio_agent.testing import write_test_video

LEFT_HALF = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]


def test_point_in_polygon():
    triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert point_in_polygon(0.2, 0.2, triangle)
    assert not point_in_polygon(0.8, 0.8, triangle)


def test_count_uses_feet_anchor_and_confidence():
    # Caixa atravessa as duas metades, mas os pés (centro inferior) estão na esquerda.
    straddling = Detection(0.9, x1=0.2, y1=0.1, x2=0.7, y2=0.9)  # âncora x=0.45
    right = Detection(0.9, x1=0.6, y1=0.1, x2=0.9, y2=0.9)
    weak = Detection(0.2, x1=0.1, y1=0.1, x2=0.3, y2=0.9)
    assert count_in_zone([straddling, right, weak], LEFT_HALF, 0.35) == (1, 0.9)
    assert count_in_zone([straddling, right, weak], LEFT_HALF, 0.1)[0] == 2


def test_occupancy_is_time_weighted_per_minute():
    agg = OccupancyAggregator(uuid4(), uuid4())
    start = datetime(2026, 10, 24, 2, 0, 0, tzinfo=UTC)
    out = []
    for i in range(300):  # 60 s a 5 fps: 1 pessoa nos primeiros 30 s, 3 nos últimos 30 s
        out += agg.observe(start + timedelta(seconds=i / 5), 1 if i < 150 else 3, 0.2)
    assert out == []  # o minuto só fecha quando o próximo começa
    out = agg.observe(start + timedelta(minutes=1), 0, 0.2)
    assert len(out) == 1
    metric = out[0]
    assert metric.bucket_start == start
    assert metric.analyzed_seconds == 60.0
    assert metric.occupancy_avg == 2.0
    assert metric.occupancy_max == 3


def test_partial_minute_reports_coverage():
    agg = OccupancyAggregator(uuid4(), uuid4())
    start = datetime(2026, 10, 24, 2, 0, 0, tzinfo=UTC)
    for i in range(50):  # só 10 s analisados
        agg.observe(start + timedelta(seconds=i / 5), 1, 0.2)
    [metric] = agg.flush()
    assert metric.analyzed_seconds == 10.0
    assert metric.occupancy_avg == 1.0
    assert agg.flush() == []


def test_file_source_samples_and_stamps_frames(tmp_path):
    video = write_test_video(tmp_path / "v.avi", seconds=3, fps=10)
    start = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)
    frames = list(FileSource(str(video), analysis_fps=5, start_at=start).frames(threading.Event()))
    assert len(frames) == 15
    assert frames[1].timestamp - frames[0].timestamp == timedelta(seconds=0.2)
    assert frames[0].timestamp == start


def test_hog_detector_runs_on_empty_frame():
    assert HogPersonDetector().detect(np.zeros((240, 320, 3), dtype=np.uint8)) == []


def test_redact_hides_credentials():
    assert redact("rtsp://admin:s3nh4@10.0.0.5:554/stream") == "rtsp://***@10.0.0.5:554/stream"
    assert redact("/data/demo.mp4") == "/data/demo.mp4"

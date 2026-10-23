"""Processamento de uma câmera: detecção → zonas → regras e métricas → mensagens."""

from collections.abc import Callable
from datetime import datetime

from alessio_agent.detection import Detector
from alessio_agent.geometry import count_in_zone
from alessio_agent.metrics import OccupancyAggregator
from alessio_agent.outbox import Payload
from alessio_agent.rules import AfterHoursPresenceEngine, CloseReason
from alessio_agent.sources import Frame, SignalLost, SourceItem
from alessio_contracts import CameraConfig, CameraStatus

Emit = Callable[[Payload], None]


class CameraPipeline:
    def __init__(self, camera: CameraConfig, detector: Detector, emit: Emit) -> None:
        self.camera = camera
        self._detector = detector
        self._emit = emit
        zones = {zone.id: zone for zone in camera.zones}
        self._aggregators = [OccupancyAggregator(camera.id, zone.id) for zone in camera.zones]
        self._engines = [
            AfterHoursPresenceEngine(camera.id, zones[rule.zone_id], rule) for rule in camera.rules
        ]
        self._frame_seconds = 1.0 / camera.analysis_fps
        self._previous_timestamp: datetime | None = None
        self.last_frame_at: datetime | None = None
        self.measured_fps: float | None = None

    def handle(self, item: SourceItem) -> None:
        if isinstance(item, SignalLost):
            self.finish(item.timestamp, "signal_lost")
        else:
            self.process(item)

    def process(self, frame: Frame) -> None:
        detections = self._detector.detect(frame.image)
        frame_seconds = self._frame_seconds
        if self._previous_timestamp is not None:
            delta = (frame.timestamp - self._previous_timestamp).total_seconds()
            if delta > 0:
                # Um quadro nunca representa mais que dois intervalos: lacunas maiores
                # aparecem como redução de analyzed_seconds, não como ocupação inventada.
                frame_seconds = min(delta, 2 * self._frame_seconds)
                rate = 1.0 / delta
                self.measured_fps = (
                    rate if self.measured_fps is None else 0.9 * self.measured_fps + 0.1 * rate
                )
        self._previous_timestamp = self.last_frame_at = frame.timestamp

        for zone, aggregator in zip(self.camera.zones, self._aggregators, strict=True):
            count, _ = count_in_zone(detections, zone.polygon, self.camera.min_confidence)
            for payload in aggregator.observe(frame.timestamp, count, frame_seconds):
                self._emit(payload)

        for engine in self._engines:
            count, confidence = count_in_zone(
                detections, engine.zone.polygon, engine.rule.min_confidence
            )
            for payload in engine.observe(frame.timestamp, count, confidence):
                self._emit(payload)

    def finish(self, moment: datetime, reason: CloseReason) -> None:
        """Fecha ocorrências abertas e envia o minuto parcial das métricas."""
        for engine in self._engines:
            for payload in engine.close(moment, reason):
                self._emit(payload)
        for aggregator in self._aggregators:
            for payload in aggregator.flush():
                self._emit(payload)
        self._previous_timestamp = None

    def status(self, source_status: str, detail: str | None) -> CameraStatus:
        return CameraStatus(
            camera_id=self.camera.id,
            status=source_status,
            last_frame_at=self.last_frame_at,
            analysis_fps=round(self.measured_fps, 2) if self.measured_fps else None,
            detail=detail,
        )

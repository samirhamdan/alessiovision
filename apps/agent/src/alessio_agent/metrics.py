"""Agregação de ocupação por zona em intervalos de um minuto."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from alessio_contracts import ZoneMetrics1m


def minute_floor(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(second=0, microsecond=0)


@dataclass
class _Bucket:
    start: datetime
    analyzed_seconds: float = 0.0
    weighted_occupancy: float = 0.0
    occupancy_max: int = 0


class OccupancyAggregator:
    """Cada quadro analisado representa ``frame_seconds`` de vídeo.

    A média é ponderada pelo tempo, e ``analyzed_seconds`` registra quanto do
    minuto teve análise de fato, para distinguir "ninguém na zona" de "câmera
    sem sinal".
    """

    def __init__(self, camera_id: UUID, zone_id: UUID) -> None:
        self.camera_id = camera_id
        self.zone_id = zone_id
        self._bucket: _Bucket | None = None

    def observe(
        self, moment: datetime, people_count: int, frame_seconds: float
    ) -> list[ZoneMetrics1m]:
        start = minute_floor(moment)
        closed: list[ZoneMetrics1m] = []
        if self._bucket is not None and self._bucket.start != start:
            closed = self.flush()
        if self._bucket is None:
            self._bucket = _Bucket(start)
        bucket = self._bucket
        bucket.analyzed_seconds += frame_seconds
        bucket.weighted_occupancy += people_count * frame_seconds
        bucket.occupancy_max = max(bucket.occupancy_max, people_count)
        return closed

    def flush(self) -> list[ZoneMetrics1m]:
        bucket, self._bucket = self._bucket, None
        if bucket is None or bucket.analyzed_seconds <= 0:
            return []
        return [
            ZoneMetrics1m(
                camera_id=self.camera_id,
                zone_id=self.zone_id,
                bucket_start=bucket.start,
                analyzed_seconds=round(min(bucket.analyzed_seconds, 60.0), 3),
                occupancy_avg=round(bucket.weighted_occupancy / bucket.analyzed_seconds, 4),
                occupancy_max=bucket.occupancy_max,
            )
        ]

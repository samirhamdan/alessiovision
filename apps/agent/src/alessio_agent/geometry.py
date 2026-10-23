"""Geometria em coordenadas normalizadas (0-1)."""

from collections.abc import Sequence

from alessio_agent.detection import Detection


def point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray casting. Pontos exatamente sobre a borda podem cair de qualquer lado."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def count_in_zone(
    detections: Sequence[Detection],
    polygon: Sequence[tuple[float, float]],
    min_confidence: float,
) -> tuple[int, float]:
    """Pessoas cujo ponto de apoio (centro inferior da caixa, os pés) está na zona.

    Retorna a contagem e a maior confiança entre as pessoas contadas.
    """
    count = 0
    best = 0.0
    for detection in detections:
        if detection.confidence < min_confidence:
            continue
        x, y = detection.anchor
        if point_in_polygon(x, y, polygon):
            count += 1
            best = max(best, detection.confidence)
    return count, best

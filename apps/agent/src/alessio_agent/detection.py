"""Detectores de pessoas intercambiáveis.

O restante do agente depende apenas do protocolo ``Detector``. Trocar o modelo
(por licença, custo ou precisão) não afeta regras, métricas nem o protocolo.
"""

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    """Pessoa detectada, com a caixa em coordenadas normalizadas (0-1)."""

    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def anchor(self) -> tuple[float, float]:
        """Centro inferior da caixa: representa os pés e funciona melhor em câmeras inclinadas."""
        return ((self.x1 + self.x2) / 2, self.y2)


class Detector(Protocol):
    name: str

    def detect(self, image: np.ndarray) -> list[Detection]: ...


class HogPersonDetector:
    """Detector HOG + SVM do OpenCV (licença Apache-2.0, sem download de modelo).

    Precisão baixa: serve para a Fase 0 e testes sem risco de licença. A
    "confiança" é derivada do score do SVM e não é calibrada.
    """

    name = "hog"

    def __init__(self, max_width: int = 640, nms_threshold: float = 0.4) -> None:
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._max_width = max_width
        self._nms_threshold = nms_threshold

    def detect(self, image: np.ndarray) -> list[Detection]:
        height, width = image.shape[:2]
        scale = min(1.0, self._max_width / width)
        if scale < 1.0:
            image = cv2.resize(image, (int(width * scale), int(height * scale)))
        h, w = image.shape[:2]
        rects, weights = self._hog.detectMultiScale(
            image, winStride=(8, 8), padding=(8, 8), scale=1.05
        )
        if len(rects) == 0:
            return []
        scores = [float(s) / (1.0 + float(s)) if s > 0 else 0.0 for s in np.ravel(weights)]
        boxes = [[int(x), int(y), int(bw), int(bh)] for x, y, bw, bh in rects]
        keep = cv2.dnn.NMSBoxes(boxes, scores, 0.0, self._nms_threshold)
        detections = []
        for index in np.ravel(keep):
            x, y, bw, bh = boxes[int(index)]
            detections.append(
                Detection(
                    confidence=scores[int(index)],
                    x1=max(0.0, x / w),
                    y1=max(0.0, y / h),
                    x2=min(1.0, (x + bw) / w),
                    y2=min(1.0, (y + bh) / h),
                )
            )
        return detections


class UltralyticsDetector:
    """YOLO via Ultralytics. AGPL-3.0: apenas para avaliação interna até a decisão D1."""

    name = "ultralytics"

    def __init__(self, model: str = "yolo11n.pt") -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - dependência opcional
            raise RuntimeError("instale o extra 'ultralytics' para usar este detector") from exc
        self._model = YOLO(model)

    def detect(self, image: np.ndarray) -> list[Detection]:  # pragma: no cover - requer modelo
        result = self._model(image, classes=[0], verbose=False)[0]
        detections = []
        for (x1, y1, x2, y2), confidence in zip(
            result.boxes.xyxyn.tolist(), result.boxes.conf.tolist(), strict=True
        ):
            detections.append(Detection(float(confidence), x1, y1, x2, y2))
        return detections


def build_detector(name: str, model: str | None = None) -> Detector:
    if name == "hog":
        return HogPersonDetector()
    if name == "ultralytics":
        return UltralyticsDetector(model or "yolo11n.pt")
    raise ValueError(f"detector desconhecido: {name}")

"""Utilitários para testes e replays determinísticos (sem modelo de detecção real)."""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from alessio_agent.detection import Detection

CENTER_PERSON = Detection(confidence=0.9, x1=0.4, y1=0.3, x2=0.6, y2=0.8)


class ScriptedDetector:
    """Devolve detecções conforme o número do quadro analisado (0, 1, 2...)."""

    name = "scripted"

    def __init__(self, script: Callable[[int], list[Detection]]) -> None:
        self._script = script
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[Detection]:
        detections = self._script(self.calls)
        self.calls += 1
        return detections


def write_test_video(path: Path, seconds: float, fps: int = 10, size=(64, 48)) -> Path:
    """Grava um vídeo sintético (quadros cinza) para testar a leitura de arquivos."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    if not writer.isOpened():
        raise RuntimeError("OpenCV sem codec MJPG disponível")
    frame = np.full((size[1], size[0], 3), 128, dtype=np.uint8)
    for _ in range(int(seconds * fps)):
        writer.write(frame)
    writer.release()
    return path

"""Gera as variações do logo a partir do arquivo original (fundo branco).

Uso: uv run python apps/web/design-system/scripts/build_logo_assets.py <logo-original> <saida>

Nada é redesenhado: os pixels vêm do original. O fundo branco vira transparência
("color to alpha") e a versão para fundo escuro troca apenas a tinta navy por
uma tinta clara, preservando o azul da marca e o antisserrilhado.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

WHITE = 254.0  # fundo medido no original
BLUE = np.array([0x00, 0x59, 0xE2], float)  # brand-blue
NAVY = np.array([0x0D, 0x26, 0x52], float)  # brand-navy
NAVY_ON_DARK = np.array([0xE8, 0xED, 0xF7], float)  # ink do tema escuro
BLUE_ON_DARK = np.array([0x3D, 0x84, 0xFF], float)  # brand-blue clareado para fundo escuro

# Regiões medidas no original 1254 x 1254: (linha inicial, linha final, coluna inicial, final).
MARK = (130, 681, 375, 878)
NAME = (694, 1033, 152, 1102)  # "Alessio" + "VISION"
FULL = (130, 1133, 151, 1102)  # marca empilhada completa


def to_rgba(rgb: np.ndarray) -> np.ndarray:
    """Remove o fundo branco: alpha pela distância ao branco, cor despré-multiplicada."""
    rgb = rgb.astype(float)
    alpha = np.clip((WHITE - rgb.min(axis=2)) / WHITE, 0, 1)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    color = np.clip((rgb - WHITE * (1 - alpha[..., None])) / safe, 0, 255)
    return np.dstack([color, alpha * 255])


def on_dark(rgba: np.ndarray) -> np.ndarray:
    """Mapeia cada cor na reta navy→azul para a reta equivalente do tema escuro."""
    color = rgba[..., :3]
    axis = BLUE - NAVY
    t = np.clip(((color - NAVY) @ axis) / (axis @ axis), 0, 1)[..., None]
    mapped = NAVY_ON_DARK + (BLUE_ON_DARK - NAVY_ON_DARK) * t
    return np.dstack([mapped, rgba[..., 3]])


def crop(rgba: np.ndarray, box, pad: int = 8) -> np.ndarray:
    r0, r1, c0, c1 = box
    return rgba[max(r0 - pad, 0) : r1 + pad + 1, max(c0 - pad, 0) : c1 + pad + 1]


def square(rgba: np.ndarray) -> np.ndarray:
    h, w = rgba.shape[:2]
    size = max(h, w)
    out = np.zeros((size, size, 4), float)
    y, x = (size - h) // 2, (size - w) // 2
    out[y : y + h, x : x + w] = rgba
    return out


def horizontal(mark: np.ndarray, name: np.ndarray) -> np.ndarray:
    """Símbolo à esquerda, nome à direita, alinhados ao centro com espaço de meio símbolo."""
    target = name.shape[0]
    scale = target / mark.shape[0]
    mark = resize(mark, int(mark.shape[1] * scale), target)
    gap = target // 4
    out = np.zeros((target, mark.shape[1] + gap + name.shape[1], 4), float)
    out[:, : mark.shape[1]] = mark
    out[:, mark.shape[1] + gap :] = name
    return out


def resize(rgba: np.ndarray, width: int, height: int) -> np.ndarray:
    # Redimensiona em cor pré-multiplicada para não criar halos nas bordas.
    premult = rgba.copy()
    premult[..., :3] *= rgba[..., 3:4] / 255
    small = cv2.resize(premult, (width, height), interpolation=cv2.INTER_AREA)
    alpha = small[..., 3:4]
    small[..., :3] = np.where(alpha > 0, small[..., :3] * 255 / np.maximum(alpha, 1e-6), 0)
    return small


def save(path: Path, rgba: np.ndarray) -> None:
    bgra = np.clip(rgba, 0, 255).round().astype(np.uint8)[..., [2, 1, 0, 3]]
    cv2.imwrite(str(path), bgra, [cv2.IMWRITE_PNG_COMPRESSION, 9])


def main(source: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    original = cv2.imread(source, cv2.IMREAD_COLOR)[..., ::-1]
    light = to_rgba(original)
    dark = on_dark(light)

    for suffix, rgba in (("", light), ("-on-dark", dark)):
        mark = square(crop(rgba, MARK))
        name = crop(rgba, NAME)
        save(out / f"alessio-vision-logo{suffix}.png", crop(rgba, FULL, pad=16))
        save(out / f"alessio-vision-mark{suffix}.png", resize(mark, 512, 512))
        save(out / f"alessio-vision-horizontal{suffix}.png", horizontal(mark, name))

    mark = square(crop(light, MARK))
    for size in (32, 180, 192):
        save(out / f"favicon-{size}.png", resize(mark, size, size))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

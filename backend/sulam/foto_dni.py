"""Foto de la persona recortada de la imagen de su DNI.

Todo corre en el servidor propio. La detección de la cara usa el detector clásico de OpenCV (sin red ni modelos
descargados) y solo SUGIERE un recorte: quien carga lo mira y lo confirma, o lo ajusta a mano. Todavía no se calibró
con DNI reales, por eso el ajuste manual es parte normal del uso.
"""

from __future__ import annotations

import io
import threading
from functools import lru_cache

from PIL import Image

_cerrojo = threading.Lock()  # OpenCV se importa y se usa de a un pedido por vez
LADO_MAXIMO = 360  # la foto se guarda chica: alcanza para reconocer a la persona y pesa poco


@lru_cache(maxsize=1)
def _detector():
    try:
        import cv2
    except Exception:
        return None
    clasificador = getattr(cv2, "CascadeClassifier", None)  # OpenCV 5 lo quitó: sin él se recorta a mano
    if clasificador is None:
        return None
    try:
        d = clasificador(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        return None
    return None if d.empty() else d


def disponible() -> bool:
    with _cerrojo:
        return _detector() is not None


def _caras(img: Image.Image) -> list[tuple[float, float, float, float]]:
    """Cajas (x, y, ancho, alto) en fracción de la imagen, de mayor a menor."""
    with _cerrojo:
        det = _detector()
        if det is None:
            return []
        import cv2
        import numpy as np

        gris = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        gris = cv2.equalizeHist(gris)
        alto, ancho = gris.shape
        lado_min = max(40, int(min(ancho, alto) * 0.05))
        cajas = det.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(lado_min, lado_min))
    orden = sorted(cajas, key=lambda c: c[2] * c[3], reverse=True)
    return [(x / ancho, y / alto, w / ancho, h / alto) for x, y, w, h in orden]


def sugerir_recorte(img: Image.Image) -> dict | None:
    """La cara más grande (la del frente del DNI, no la marca de agua chica), con margen para pelo, mentón y hombros."""
    caras = _caras(img)
    if not caras:
        return None
    x, y, w, h = caras[0]
    return ampliar({"x": x, "y": y, "w": w, "h": h})


def ampliar(caja: dict, margen_x: float = 0.45, margen_arriba: float = 0.55, margen_abajo: float = 0.35) -> dict:
    """Agranda la caja de la cara para que quede un retrato, sin salirse de la imagen."""
    x0 = max(0.0, caja["x"] - caja["w"] * margen_x)
    x1 = min(1.0, caja["x"] + caja["w"] * (1 + margen_x))
    y0 = max(0.0, caja["y"] - caja["h"] * margen_arriba)
    y1 = min(1.0, caja["y"] + caja["h"] * (1 + margen_abajo))
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def recortar(img: Image.Image, caja: dict) -> bytes:
    """JPEG del recorte (la caja va en fracción de la imagen), reducido a un tamaño chico."""
    ancho, alto = img.size
    x0, y0 = int(round(caja["x"] * ancho)), int(round(caja["y"] * alto))
    x1, y1 = int(round((caja["x"] + caja["w"]) * ancho)), int(round((caja["y"] + caja["h"]) * alto))
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(ancho, x1), min(alto, y1)
    if x1 - x0 < 20 or y1 - y0 < 20:
        raise ValueError("El recorte es demasiado chico.")
    corte = img.convert("RGB").crop((x0, y0, x1, y1))
    corte.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = io.BytesIO()
    corte.save(salida, "JPEG", quality=85)
    return salida.getvalue()

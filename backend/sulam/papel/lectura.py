"""Lectura de fichas SULAM fotografiadas o escaneadas.

Pasos:
1. Ubicar las cuatro marcas negras de las esquinas.
2. Enderezar la imagen a la medida exacta de la hoja (corrige perspectiva,
   giro y escala) y leer el QR para saber qué ficha, versión y hoja es. Si el QR
   no se lee, se prueba la hoja girada (foto al revés o de costado).
3. Con la plantilla de esa ficha, medir cada casilla (proporción de tinta) y
   recortar cada celda de dígitos y cada recuadro de texto.

Nada se guarda automáticamente: el resultado alimenta la pantalla de revisión,
donde una persona confirma o corrige cada valor junto al recorte.

Requiere OpenCV (`opencv-python-headless`) y NumPy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .fichas import ficha

PX_MM = 8.0  # resolución de trabajo: 8 px por mm (~203 ppp)
UMBRAL_MARCADA = 0.10  # proporción de tinta a partir de la cual una casilla está marcada
UMBRAL_DUDA = 0.045  # entre este valor y el anterior, la casilla se manda a revisar
UMBRAL_VACIO = 0.015  # celdas y recuadros por debajo de esto se consideran vacíos


class ErrorLectura(Exception):
    pass


@dataclass
class Resultado:
    ficha: str
    version: int
    pagina: int
    casillas: dict[str, dict] = field(default_factory=dict)  # id -> {campo, valor, tinta, marcada, dudosa}
    campos: dict[str, dict] = field(default_factory=dict)  # id -> {tipo, campo, vacio, recorte(s)}
    avisos: list[str] = field(default_factory=list)
    imagen: np.ndarray | None = None  # hoja enderezada (gris)

    def marcadas(self, campo: str) -> list[str]:
        return [c["valor"] for c in self.casillas.values() if c["campo"] == campo and c["marcada"]]


# ---------------------------------------------------------------------- marcas


def _candidatos_marca(gris: np.ndarray) -> list[tuple[float, float, float]]:
    """Manchas negras casi cuadradas y macizas: (cx, cy, lado)."""
    h, w = gris.shape
    _, bin_ = cv2.threshold(cv2.GaussianBlur(gris, (5, 5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(bin_, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    lado_min = min(h, w) * 0.012
    lado_max = min(h, w) * 0.09
    candidatos = []
    for c in contornos:
        x, y, cw, ch = cv2.boundingRect(c)
        if not (lado_min <= cw <= lado_max and lado_min <= ch <= lado_max):
            continue
        if not 0.6 <= cw / ch <= 1.6:
            continue
        area = cv2.contourArea(c)
        hull = cv2.contourArea(cv2.convexHull(c))
        if hull == 0 or area / hull < 0.85 or area / (cw * ch) < 0.6:
            continue
        # Una marca es maciza; descarta, por ejemplo, los cuadros de posición del QR.
        if np.count_nonzero(bin_[y:y + ch, x:x + cw]) / (cw * ch) < 0.8:
            continue
        m = cv2.moments(c)
        candidatos.append((m["m10"] / m["m00"], m["m01"] / m["m00"], (cw + ch) / 2))
    return candidatos


def _marcas(gris: np.ndarray) -> np.ndarray:
    h, w = gris.shape
    cand = _candidatos_marca(gris)
    if len(cand) < 4:
        raise ErrorLectura("No se encontraron las cuatro marcas de las esquinas. ¿La foto muestra la hoja completa?")
    esquinas = [(0, 0), (w, 0), (w, h), (0, h)]
    elegidas = []
    for ex, ey in esquinas:
        mejor = min(cand, key=lambda c: (c[0] - ex) ** 2 + (c[1] - ey) ** 2)
        elegidas.append(mejor)
    if len({(round(c[0]), round(c[1])) for c in elegidas}) < 4:
        raise ErrorLectura("Las marcas de las esquinas no se distinguen bien.")
    lados = [c[2] for c in elegidas]
    if max(lados) > 2.5 * min(lados):
        raise ErrorLectura("Las marcas detectadas no son consistentes; vuelva a sacar la foto con la hoja completa.")
    return np.array([[c[0], c[1]] for c in elegidas], dtype=np.float32)


def _enderezar(gris: np.ndarray, puntos: np.ndarray, plantilla: dict) -> np.ndarray:
    ancho, alto = plantilla["tamano_mm"]
    destino = np.array([[x * PX_MM, y * PX_MM] for x, y in plantilla["marcas_mm"]], dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(puntos, destino)
    return cv2.warpPerspective(gris, matriz, (int(ancho * PX_MM), int(alto * PX_MM)), flags=cv2.INTER_AREA,
                               borderValue=255)


def _leer_qr(hoja: np.ndarray, plantilla_ref: dict) -> str | None:
    qr = next(e for e in plantilla_ref["paginas"][0]["elementos"] if e["tipo"] == "qr")
    m = 5.0
    x0, y0 = int((qr["x"] - m) * PX_MM), int((qr["y"] - m) * PX_MM)
    x1, y1 = int((qr["x"] + qr["w"] + m) * PX_MM), int((qr["y"] + qr["h"] + m) * PX_MM)
    recorte = hoja[max(y0, 0):y1, max(x0, 0):x1]
    detector = cv2.QRCodeDetector()
    for img in (recorte, cv2.resize(recorte, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)):
        texto, _, _ = detector.detectAndDecode(img)
        if texto:
            return texto
    return None


def _identificar(texto_qr: str) -> tuple[str, int, int]:
    partes = texto_qr.split("|")
    if len(partes) != 4 or partes[0] != "SULAM":
        raise ErrorLectura("El código QR no corresponde a una ficha SULAM.")
    return partes[1], int(partes[2].lstrip("v")), int(partes[3].lstrip("p"))


# ---------------------------------------------------------------------- medición


def _binaria(hoja: np.ndarray) -> np.ndarray:
    # Umbral adaptativo: tolera sombras e iluminación despareja de una foto.
    return cv2.adaptiveThreshold(hoja, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 15)


def _region(img: np.ndarray, e: dict, margen_mm: float = 0.0) -> np.ndarray:
    x0 = int(round((e["x"] + margen_mm) * PX_MM))
    y0 = int(round((e["y"] + margen_mm) * PX_MM))
    x1 = int(round((e["x"] + e["w"] - margen_mm) * PX_MM))
    y1 = int(round((e["y"] + e["h"] - margen_mm) * PX_MM))
    return img[y0:y1, x0:x1]


def _tinta(binaria: np.ndarray, e: dict, margen_mm: float) -> float:
    r = _region(binaria, e, margen_mm)
    return float(np.count_nonzero(r)) / r.size if r.size else 0.0


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes() if ok else b""


def leer(imagen: bytes | np.ndarray) -> Resultado:
    if isinstance(imagen, (bytes, bytearray)):
        datos = np.frombuffer(imagen, dtype=np.uint8)
        img = cv2.imdecode(datos, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ErrorLectura("No se pudo abrir la imagen.")
    else:
        img = imagen if imagen.ndim == 2 else cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

    # Las fotos muy grandes se reducen para trabajar más rápido sin perder detalle útil.
    lado = max(img.shape)
    if lado > 3600:
        f = 3600 / lado
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)

    puntos = _marcas(img)
    _, referencia = ficha("CAR")  # todas las fichas comparten tamaño, marcas y posición del QR

    hoja = texto_qr = None
    for giro in range(4):  # 0°, 90°, 180°, 270°: se rotan las esquinas hasta que el QR se lea
        p = np.roll(puntos, -giro, axis=0)
        candidata = _enderezar(img, p, referencia)
        texto_qr = _leer_qr(candidata, referencia)
        if texto_qr:
            hoja = candidata
            break
    if hoja is None:
        raise ErrorLectura("No se pudo leer el código QR de la ficha. Saque la foto con más luz y sin reflejos.")

    codigo, version, pagina = _identificar(texto_qr)
    _, plantilla = ficha(codigo)
    if version != plantilla["version"]:
        raise ErrorLectura(f"Versión de ficha no reconocida: {codigo} v{version}.")
    elementos = plantilla["paginas"][pagina - 1]["elementos"]

    binaria = _binaria(hoja)
    res = Resultado(ficha=codigo, version=version, pagina=pagina, imagen=hoja)

    for e in elementos:
        if e["tipo"] == "casilla":
            t = _tinta(binaria, e, margen_mm=0.75)
            res.casillas[e["id"]] = {
                "campo": e["campo"],
                "valor": e["valor"],
                "unica": e.get("unica", False),
                "tinta": round(t, 3),
                "marcada": t >= UMBRAL_MARCADA,
                "dudosa": UMBRAL_DUDA <= t < UMBRAL_MARCADA,
            }
        elif e["tipo"] == "digitos":
            celdas = []
            for celda in e["celdas"]:
                t = _tinta(binaria, celda, margen_mm=0.7)
                celdas.append({
                    "vacia": t < UMBRAL_VACIO,
                    "recorte": _png(_region(hoja, celda, margen_mm=0.3)),
                })
            res.campos[e["id"]] = {
                "tipo": "digitos",
                "campo": e["campo"],
                "vacio": all(c["vacia"] for c in celdas),
                "celdas": celdas,
                "recorte": _png(_region(hoja, e, margen_mm=-1.0)),
            }
        elif e["tipo"] == "texto":
            t = _tinta(binaria, e, margen_mm=1.0)
            res.campos[e["id"]] = {
                "tipo": "texto",
                "campo": e["campo"],
                "vacio": t < UMBRAL_VACIO,
                "recorte": _png(_region(hoja, e, margen_mm=-1.0)),
            }

    # Grupos de opción única con más de una marca: a revisión.
    por_campo: dict[str, list[dict]] = {}
    for c in res.casillas.values():
        if c["unica"]:
            por_campo.setdefault(c["campo"], []).append(c)
    for campo, lista in por_campo.items():
        marcadas = [c for c in lista if c["marcada"]]
        if len(marcadas) > 1:
            res.avisos.append(f"Más de una opción marcada en «{campo}».")
            for c in marcadas:
                c["dudosa"] = True
    return res

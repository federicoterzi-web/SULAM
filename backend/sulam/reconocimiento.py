"""Lectura automática de fotos de documentos (OCR local con Tesseract) y sugerencias.

Todo corre en el servidor propio: ninguna imagen sale de la red. Lo que se obtiene son SUGERENCIAS:
quien clasifica siempre las revisa y confirma.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from functools import lru_cache

from .textutil import normalizar, normalizar_documento

_PALABRAS_VACIAS = {"de", "del", "la", "el", "las", "los", "y", "en", "a", "para", "por", "con", "o", "un", "una"}


@lru_cache(maxsize=1)
def _idioma() -> str | None:
    """'spa' si está instalado; si no, 'eng' (se lee peor); None si no hay Tesseract."""
    exe = shutil.which("tesseract")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    langs = set(r.stdout.split())
    return "spa" if "spa" in langs else ("eng" if "eng" in langs else None)


def disponible() -> bool:
    return _idioma() is not None


def leer_texto(jpeg: bytes) -> str:
    """Texto de una foto. Vacío si Tesseract no está o falla."""
    idioma = _idioma()
    if idioma is None:
        return ""
    try:
        r = subprocess.run(
            [shutil.which("tesseract") or "tesseract", "stdin", "stdout", "-l", idioma, "--psm", "3"],
            input=jpeg, capture_output=True, timeout=90,
        )
    except Exception:
        return ""
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


# --- análisis del texto ---------------------------------------------------------------------

def documentos_en(texto: str) -> list[str]:
    """Números de documento (DNI) y CUIL/CUIT que aparecen en el texto, normalizados."""
    halladas: list[str] = []
    for m in re.finditer(r"\b(\d{2})[-\s.]?(\d{8})[-\s.]?(\d)\b", texto):
        halladas.append(m.group(1) + m.group(2) + m.group(3))
        halladas.append(m.group(2))  # el DNI va dentro del CUIL
    for m in re.finditer(r"(?<![\d.])(\d{1,2}\.?\d{3}\.?\d{3})(?![\d.])", texto):
        n = normalizar_documento(m.group(1))
        if n and 7 <= len(n) <= 8:
            halladas.append(n)
    vistas: list[str] = []
    for n in halladas:
        if n not in vistas:
            vistas.append(n)
    return vistas


def _a_fecha(s: str) -> date | None:
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s.strip())
    if not m:
        return None
    d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if a < 100:
        a += 2000 if a < 70 else 1900
    try:
        return date(a, mes, d)
    except ValueError:
        return None


_FECHA = r"(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4})"


def _fecha_tras(texto: str, claves: list[str]) -> str | None:
    for c in claves:
        m = re.search(c + r"[^\d\n]{0,25}" + _FECHA, texto, re.IGNORECASE)
        if m:
            f = _a_fecha(re.sub(r"\s+", "", m.group(1)))
            if f and 1950 <= f.year <= 2100:
                return f.isoformat()
    return None


def fechas_en(texto: str) -> dict[str, str | None]:
    return {
        "vence": _fecha_tras(texto, [r"v[aá]lid[oa]\s+hasta", r"vencimiento", r"vence", r"vigente\s+hasta", r"caduca"]),
        "fecha_emision": _fecha_tras(texto, [r"fecha\s+de\s+emisi[oó]n", r"emitid[oa]", r"emisi[oó]n", r"expedid[oa]", r"fecha\s+de\s+expedici[oó]n"]),
    }


def numero_en(texto: str) -> str | None:
    m = re.search(r"\b(?:n[úu]mero|nro|n[°º]|n\.º|cert(?:ificado)?\.?\s*n[°º]?)\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/.]{3,24})", texto, re.IGNORECASE)
    if m:
        v = m.group(1).strip(".-/")
        if any(c.isdigit() for c in v):
            return v
    return None


def pagina_de(texto: str) -> tuple[int, int] | None:
    m = re.search(r"\b(?:p[áa]gina|p[áa]g\.?|hoja)\s*(\d{1,3})\s*(?:de|/)\s*(\d{1,3})\b", texto, re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= int(m.group(2)) <= 200:
        return int(m.group(1)), int(m.group(2))
    return None


def agrupar(marcas: list[tuple[int, int] | None]) -> list[list[int]]:
    """Posiciones de las hojas agrupadas: una hoja «n de N» con n>1 sigue a la anterior si era la «n-1»."""
    grupos: list[list[int]] = []
    ultima: tuple[int, int] | None = None
    for i, m in enumerate(marcas):
        if m and m[0] > 1 and grupos and ultima and ultima[1] == m[1] and ultima[0] == m[0] - 1:
            grupos[-1].append(i)
        else:
            grupos.append([i])
        ultima = m
    return grupos


def _significativas(texto: str) -> list[str]:
    return [w for w in normalizar(texto).split() if w not in _PALABRAS_VACIAS and len(w) > 2]


def tipos_probables(texto: str, tipos: list[tuple[int, str, str | None]]) -> list[tuple[int, float]]:
    """Tipos ordenados por parecido: fracción de las palabras del nombre (y peso menor de la descripción) halladas."""
    palabras = set(normalizar(texto).split())
    puntajes = []
    for tid, nombre, desc in tipos:
        pn = _significativas(nombre)
        if not pn:
            continue
        p = sum(1 for w in pn if w in palabras) / len(pn)
        pd = _significativas(desc or "")
        if pd:
            p += 0.3 * sum(1 for w in pd if w in palabras) / len(pd)
        if p >= 0.5:
            puntajes.append((tid, round(p, 2)))
    return sorted(puntajes, key=lambda x: -x[1])


def leer_palabras(jpeg: bytes) -> tuple[int, int, list[dict]]:
    """(ancho, alto, palabras con su caja en píxeles) de una foto, con la salida TSV de Tesseract."""
    from PIL import Image

    ancho, alto = Image.open(__import__("io").BytesIO(jpeg)).size
    idioma = _idioma()
    if idioma is None:
        return ancho, alto, []
    try:
        r = subprocess.run(
            [shutil.which("tesseract") or "tesseract", "stdin", "stdout", "-l", idioma, "--psm", "3", "tsv"],
            input=jpeg, capture_output=True, timeout=90,
        )
    except Exception:
        return ancho, alto, []
    palabras = []
    for linea in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = linea.split("\t")
        if len(c) < 12 or c[0] != "5" or not c[11].strip():
            continue
        try:
            palabras.append({"t": c[11].strip(), "x": int(c[6]), "y": int(c[7]), "w": int(c[8]), "h": int(c[9])})
        except ValueError:
            continue
    return ancho, alto, palabras

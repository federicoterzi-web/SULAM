"""Texto de los documentos: lectura (PDF con texto, u OCR local), búsqueda y resaltado.

El texto se guarda en la base de datos propia. Se muestra solo a quien ya puede abrir el documento.
"""

from __future__ import annotations

import io
import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone

from . import reconocimiento
from .textutil import normalizar

MAX_HOJAS_OCR = 25
SALTO = "\f"  # separa las hojas dentro de Documento.texto


def activa() -> bool:
    return os.environ.get("SULAM_INDEXAR_TEXTO", "1").strip().lower() not in {"0", "no", "false"}


def extraer_texto(datos: bytes, mime: str) -> str:
    """Texto de un PDF (de su capa de texto; las hojas sin texto se leen con OCR) o de una foto."""
    if mime in ("image/jpeg", "image/png"):
        return reconocimiento.leer_texto(datos)
    if mime != "application/pdf":
        return ""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(datos)
    hojas: list[str] = []
    ocr_usado = 0
    for i in range(len(pdf)):
        pagina = pdf[i]
        t = (pagina.get_textpage().get_text_range() or "").strip()
        if len(t) < 30 and ocr_usado < MAX_HOJAS_OCR and reconocimiento.disponible():
            ocr_usado += 1
            b = io.BytesIO()
            pagina.render(scale=2).to_pil().convert("RGB").save(b, "JPEG", quality=85)
            t = reconocimiento.leer_texto(b.getvalue()).strip() or t
        hojas.append(t)
    return SALTO.join(hojas)


def indexar_documento(doc_id: uuid.UUID) -> str:
    """Lee el archivo y guarda su texto. Devuelve el estado final: listo / sin_texto / error."""
    from .db import session_factory
    from .models import Documento
    from .storage import almacenamiento_por_nombre

    with session_factory()() as db:
        d = db.get(Documento, doc_id)
        if d is None:
            return "error"
        try:
            with almacenamiento_por_nombre(d.almacenamiento).abrir(d.clave_almacenamiento) as f:
                texto = extraer_texto(f.read(), d.mime)
            d.texto = texto if texto.strip(SALTO + " \n\t") else None
            d.texto_busqueda = normalizar(texto.replace(SALTO, " ")) or None
            d.texto_estado = "listo" if d.texto else "sin_texto"
        except Exception:
            d.texto, d.texto_busqueda, d.texto_estado = None, None, "error"
        d.texto_leido_en = datetime.now(timezone.utc)
        db.commit()
        return d.texto_estado


def lanzar(doc_id: uuid.UUID) -> None:
    """Lee el texto en segundo plano para no hacer esperar a quien carga el documento."""
    if activa():
        threading.Thread(target=indexar_documento, args=(doc_id,), daemon=True, name="indexar-texto").start()


# --- búsqueda -------------------------------------------------------------------------------

def consulta_tsquery(q: str) -> str | None:
    """'resolucion 245' → 'resolucion:* & 245:*' (todas las palabras, por prefijo)."""
    palabras = [w for w in normalizar(q).split() if w]
    return " & ".join(f"{w}:*" for w in palabras[:8]) or None


def fragmento(texto: str | None, q: str, ancho: int = 70) -> str:
    """Trozo del texto alrededor de la primera palabra buscada."""
    if not texto:
        return ""
    plano = re.sub(r"\s+", " ", texto.replace(SALTO, " "))
    base = _plano(plano)
    for w in normalizar(q).split():
        i = base.find(w)
        if i >= 0:
            a, b = max(0, i - ancho), min(len(plano), i + len(w) + ancho)
            return ("…" if a else "") + plano[a:b].strip() + ("…" if b < len(plano) else "")
    return plano[: 2 * ancho].strip()


# --- resaltado ------------------------------------------------------------------------------

def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, letra por letra: conserva el largo para ubicar las coincidencias."""
    salida = []
    for c in texto:
        d = unicodedata.normalize("NFD", c)
        salida.append((d[0] if d else c).lower() if len(c) == 1 else c)
    return "".join(salida)


def _con_separadores(digitos: str) -> str:
    return r"(?<!\d)" + r"[.\-\s]?".join(re.escape(x) for x in digitos) + r"(?!\d)"


def menciones_institucion() -> list[str]:
    crudo = os.environ.get("SULAM_MENCIONES", "Dirección de Adultos Mayores;Adultos Mayores")
    return [m.strip() for m in crudo.split(";") if m.strip()]


def patrones_persona(persona) -> list[tuple[str, str]]:
    """(clase, expresión regular sobre el texto sin tildes y en minúsculas)."""
    pats: list[tuple[str, str]] = []
    for campo in (persona.apellidos, persona.nombres):
        for w in normalizar(campo).split():
            if len(w) >= 3:
                pats.append(("nombre", r"\b" + re.escape(w) + r"\b"))
    for num in (persona.numero_documento, persona.cuil):
        d = re.sub(r"\D", "", num or "")
        if len(d) >= 7:
            pats.append(("documento", _con_separadores(d)))
    return pats


def patrones_institucion() -> list[tuple[str, str]]:
    pats = []
    for m in menciones_institucion():
        palabras = normalizar(m).split()
        if palabras:
            pats.append(("institucion", r"\b" + r"\s+".join(re.escape(w) for w in palabras) + r"\b"))
    return pats


def resaltar(texto: str, patrones: list[tuple[str, str]]) -> list[dict]:
    """Parte el texto en trozos [{t, k}] donde k es la clase de la marca (o None). No se solapan."""
    base = _plano(texto)
    marcas: list[tuple[int, int, str]] = []
    for clase, rx in patrones:
        for m in re.finditer(rx, base):
            if m.end() > m.start():
                marcas.append((m.start(), m.end(), clase))
    marcas.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    trozos: list[dict] = []
    pos = 0
    for a, b, k in marcas:
        if a < pos:
            continue
        if a > pos:
            trozos.append({"t": texto[pos:a], "k": None})
        trozos.append({"t": texto[a:b], "k": k})
        pos = b
    if pos < len(texto):
        trozos.append({"t": texto[pos:], "k": None})
    return trozos


# --- marcas sobre la imagen de la hoja ---------------------------------------------------------

def imagen_de_hoja(datos: bytes, mime: str, n: int) -> tuple[bytes, int] | None:
    """JPEG de la hoja n (desde 1) y la cantidad de hojas del archivo. None si la hoja no existe."""
    if mime in ("image/jpeg", "image/png"):
        if n != 1:
            return None
        from PIL import Image

        b = io.BytesIO()
        Image.open(io.BytesIO(datos)).convert("RGB").save(b, "JPEG", quality=88)
        return b.getvalue(), 1
    if mime != "application/pdf":
        return None
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(datos)
    if not 1 <= n <= len(pdf):
        return None
    b = io.BytesIO()
    pdf[n - 1].render(scale=2).to_pil().convert("RGB").save(b, "JPEG", quality=88)
    return b.getvalue(), len(pdf)


def cantidad_de_hojas(datos: bytes, mime: str) -> int:
    if mime == "application/pdf":
        import pypdfium2 as pdfium

        return len(pdfium.PdfDocument(datos))
    return 1 if mime in ("image/jpeg", "image/png") else 0


def marcar_palabras(palabras: list[dict], persona, menciones: list[str]) -> list[dict]:
    """Cajas (en fracción de la hoja) de las palabras que son del nombre o documento de la persona, o menciones a la Dirección."""
    nombres = set()
    digitos_persona: list[str] = []
    if persona is not None:
        for campo in (persona.apellidos, persona.nombres):
            nombres |= {w for w in normalizar(campo).split() if len(w) >= 3}
        digitos_persona = [d for d in (re.sub(r"\D", "", x or "") for x in (persona.numero_documento, persona.cuil)) if len(d) >= 7]
    norm = [normalizar(p["t"]) for p in palabras]
    clases: list[str | None] = [None] * len(palabras)
    for i, (p, n) in enumerate(zip(palabras, norm)):
        d = re.sub(r"\D", "", p["t"])
        if n and n in nombres:
            clases[i] = "nombre"
        elif len(d) >= 7 and any(d in x for x in digitos_persona):
            clases[i] = "documento"
    for m in menciones:
        seq = normalizar(m).split()
        for i in range(len(palabras) - len(seq) + 1):
            if seq and norm[i:i + len(seq)] == seq:
                for j in range(i, i + len(seq)):
                    clases[j] = "institucion"
    return [(p, c) for p, c in zip(palabras, clases) if c]  # type: ignore[misc]

from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin tildes ni signos, espacios simples. Para búsqueda y duplicados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9ñ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalizar_documento(numero: str | None) -> str | None:
    """Quita puntos, espacios y guiones de un número de documento."""
    if numero is None:
        return None
    limpio = re.sub(r"[^0-9A-Za-z]", "", numero).upper()
    return limpio or None


def escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

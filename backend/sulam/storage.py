"""Almacenamiento de archivos independiente del proveedor.

El resto del sistema solo conoce el identificador interno del documento y la
pareja (almacenamiento, clave). Cambiar de proveedor implica escribir otra
clase que cumpla `Almacenamiento` y migrar con `sulam migrar-archivos`.

Implementación incluida en la 0.1: `AlmacenamientoLocal` (carpeta en disco,
direccionada por contenido: la clave es el SHA-256 del archivo, lo que
detecta archivos idénticos y permite verificar integridad).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol

from .config import get_settings

BLOQUE = 1024 * 1024


@dataclass
class ArchivoGuardado:
    clave: str
    sha256: str
    tamano: int


class Almacenamiento(Protocol):
    nombre: str

    def guardar(self, origen: BinaryIO) -> ArchivoGuardado: ...

    def abrir(self, clave: str) -> BinaryIO: ...

    def existe(self, clave: str) -> bool: ...

    def verificar(self, clave: str, sha256: str) -> bool: ...

    def eliminar(self, clave: str) -> None: ...

    def claves(self) -> Iterator[str]: ...


class AlmacenamientoLocal:
    nombre = "local"

    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _ruta(self, clave: str) -> Path:
        if len(clave) != 64 or not all(c in "0123456789abcdef" for c in clave):
            raise ValueError("Clave de almacenamiento inválida")
        return self.raiz / clave[:2] / clave[2:4] / clave

    def guardar(self, origen: BinaryIO) -> ArchivoGuardado:
        h = hashlib.sha256()
        tamano = 0
        tmp_dir = self.raiz / "_tmp"
        tmp_dir.mkdir(exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir)
        try:
            with os.fdopen(fd, "wb") as destino:
                while bloque := origen.read(BLOQUE):
                    h.update(bloque)
                    tamano += len(bloque)
                    destino.write(bloque)
                destino.flush()
                os.fsync(destino.fileno())
            digest = h.hexdigest()
            final = self._ruta(digest)
            if final.exists():
                os.unlink(tmp_path)
            else:
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp_path, final)
            return ArchivoGuardado(clave=digest, sha256=digest, tamano=tamano)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def abrir(self, clave: str) -> BinaryIO:
        return open(self._ruta(clave), "rb")

    def existe(self, clave: str) -> bool:
        return self._ruta(clave).is_file()

    def verificar(self, clave: str, sha256: str) -> bool:
        if not self.existe(clave):
            return False
        h = hashlib.sha256()
        with self.abrir(clave) as f:
            while bloque := f.read(BLOQUE):
                h.update(bloque)
        return h.hexdigest() == sha256

    def eliminar(self, clave: str) -> None:
        ruta = self._ruta(clave)
        if ruta.exists():
            ruta.unlink()

    def claves(self) -> Iterator[str]:
        for ruta in self.raiz.glob("??/??/*"):
            if ruta.is_file() and len(ruta.name) == 64:
                yield ruta.name


def almacenamiento_por_nombre(nombre: str, raiz: Path | None = None) -> Almacenamiento:
    if nombre == "local":
        return AlmacenamientoLocal(raiz or get_settings().storage_dir)
    raise ValueError(
        f"Proveedor de almacenamiento '{nombre}' no disponible. "
        "Ver DECISIONS.md (D-008) para agregar Google Drive u otro proveedor."
    )


def almacenamiento_actual() -> Almacenamiento:
    return almacenamiento_por_nombre("local")


def copiar(origen: Almacenamiento, clave: str, destino: Almacenamiento) -> ArchivoGuardado:
    with origen.abrir(clave) as f:
        return destino.guardar(f)


# Firmas de archivo ("magic numbers") para validar el tipo real del contenido.
FIRMAS = {
    b"%PDF-": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def detectar_mime(cabecera: bytes) -> str | None:
    for firma, mime in FIRMAS.items():
        if cabecera.startswith(firma):
            return mime
    return None


def copiar_a_temporal(origen: BinaryIO, limite: int) -> tuple[tempfile.SpooledTemporaryFile, int]:
    """Copia el upload a un temporal controlando el tamaño máximo."""
    tmp = tempfile.SpooledTemporaryFile(max_size=4 * BLOQUE)
    total = 0
    while bloque := origen.read(BLOQUE):
        total += len(bloque)
        if total > limite:
            tmp.close()
            raise ValueError("El archivo supera el tamaño máximo permitido.")
        tmp.write(bloque)
    tmp.seek(0)
    return tmp, total


"""Calibración del reconocimiento automático (solo administrador).

Cuando está activada, cada vez que se clasifican hojas desde la bandeja se compara lo que sugirió la lectura con lo
que se confirmó. Se guardan únicamente las diferencias, sin nombres, números ni imágenes. Opcionalmente, un fragmento
del texto con los números y las palabras en mayúscula tapados, para ver por qué falló una regla.
"""

from __future__ import annotations

import re
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Ajuste, CasoCalibracion
from .textutil import normalizar

CLAVE = "calibracion"
_TTL = 2 * 3600
_cache: dict[frozenset, tuple[float, dict]] = {}

_CLAVES_DE_FECHA = ("vence", "vencimiento", "valido", "valida", "vigente", "vigencia", "caduca", "emision", "emitido", "emitida", "expedido",
                    "numero", "nro", "pagina", "hoja", "certificado", "fecha")
_VISIBLES = {"direccion", "adultos", "mayores", "dni", "cuil", "cuit", "cud"}


def config(db: Session) -> dict:
    a = db.get(Ajuste, CLAVE)
    v = a.valor if a and isinstance(a.valor, dict) else {}
    return {"activo": bool(v.get("activo")), "fragmentos": bool(v.get("fragmentos"))}


def guardar_config(db: Session, activo: bool, fragmentos: bool) -> dict:
    a = db.get(Ajuste, CLAVE)
    if a is None:
        a = Ajuste(clave=CLAVE, valor={})
        db.add(a)
    a.valor = {"activo": activo, "fragmentos": fragmentos}
    db.flush()
    return config(db)


def recordar_lectura(paginas: list[uuid.UUID], sugerencia: dict, texto: str) -> None:
    ahora = time.time()
    for k in [k for k, (t, _) in _cache.items() if ahora - t > _TTL]:
        _cache.pop(k, None)
    _cache[frozenset(paginas)] = (ahora, {"sugerencia": sugerencia, "texto": texto})


def lectura_de(paginas: list[uuid.UUID]) -> dict | None:
    r = _cache.get(frozenset(paginas))
    return r[1] if r else None


def enmascarar(texto: str, nombres: set[str] | None = None) -> str:
    """Tapa números y palabras que empiezan con mayúscula (nombres, apellidos, lugares), salvo claves conocidas."""
    nombres = nombres or set()

    def palabra(m: re.Match) -> str:
        w = m.group(0)
        n = normalizar(w)
        if n in _VISIBLES or n in _CLAVES_DE_FECHA:
            return w
        if n in nombres or w[0].isupper():
            return "[…]"
        return w

    t = re.sub(r"\d", "#", texto)
    return re.sub(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}", palabra, t)


def fragmentos_clave(texto: str, ancho: int = 60) -> str:
    """Líneas del texto con números o con palabras de fechas, números o páginas (se enmascaran después)."""
    lineas = []
    for linea in re.split(r"[\n\f]+", texto):
        base = normalizar(linea)
        if linea.strip() and (re.search(r"\d", linea) or any(c in base for c in _CLAVES_DE_FECHA)):
            lineas.append(linea.strip()[: 2 * ancho])
        if len(lineas) >= 8:
            break
    return "\n".join(lineas)


def registrar(db: Session, *, paginas: list[uuid.UUID], final: dict, tipo_nombre: str | None, nombres_persona: set[str]) -> int:
    """Compara lo sugerido por la lectura (si la hay en memoria) con lo confirmado y guarda las diferencias. Devuelve cuántos casos."""
    cfg = config(db)
    if not cfg["activo"]:
        return 0
    lectura = lectura_de(paginas)
    if lectura is None:
        return 0
    sug = lectura["sugerencia"]
    texto = lectura["texto"] or ""
    cuenta = 0
    casos: list[CasoCalibracion] = []
    for campo in ("persona", "tipo", "fecha_emision", "vence", "numero"):
        s, f = sug.get(campo), final.get(campo)
        if s is None and f is None:
            continue  # nada que sugerir ni nada confirmado: no dice nada sobre la lectura
        if s is not None and f is not None:
            res = "acierto" if str(s) == str(f) else "corregido"
        elif s is None:
            res = "faltante"  # había un dato y no lo sugirió
        else:
            res = "sobrante"  # sugirió algo y quedó vacío
        frag = None
        if cfg["fragmentos"] and res != "acierto" and campo in ("fecha_emision", "vence", "numero"):
            frag = enmascarar(fragmentos_clave(texto), nombres_persona) or None
        casos.append(CasoCalibracion(campo=campo, resultado=res, tipo_documental=tipo_nombre, detalle={}, fragmento=frag))
    hojas_final, grupo = len(paginas), sug.get("grupos") or []
    casos.append(CasoCalibracion(
        campo="hojas", resultado="acierto" if any(set(g) == set(map(str, paginas)) for g in grupo) else "corregido",
        tipo_documental=tipo_nombre, detalle={"hojas": hojas_final}, fragmento=None,
    ))
    if not texto.strip():
        casos.append(CasoCalibracion(campo="lectura", resultado="faltante", tipo_documental=tipo_nombre, detalle={"texto_vacio": True}))
    for c in casos:
        db.add(c)
        cuenta += 1
    return cuenta


def resumen(db: Session) -> dict:
    filas = db.execute(select(CasoCalibracion.campo, CasoCalibracion.resultado, CasoCalibracion.tipo_documental)).all()
    por_campo: dict[str, dict[str, int]] = {}
    por_tipo: dict[str, dict[str, dict[str, int]]] = {}
    for campo, res, tipo in filas:
        por_campo.setdefault(campo, {}).setdefault(res, 0)
        por_campo[campo][res] += 1
        t = por_tipo.setdefault(tipo or "(sin tipo)", {}).setdefault(campo, {})
        t[res] = t.get(res, 0) + 1
    return {"total": len(filas), "por_campo": por_campo, "por_tipo": por_tipo}

"""Importación de personal desde un archivo local (fichas, horarios y cuentas de usuario).

El archivo NO forma parte del repositorio: lo prepara y lo guarda la Dirección en su
propia computadora o servidor. Formato (JSON):

    {"agentes": [{
        "nombre": "Apellido Nombre",
        "area": "Departamento Admisión de Casos y Recepción de Denuncias",   # nombre exacto del área en SULAM
        "rol": "Técnico",                  # opcional, por defecto «Técnico»
        "usuario": "apellido.nombre",      # opcional; por defecto primera palabra del apellido . última palabra
        "id_reloj": "58", "boleta": "978", # opcionales
        "desde": "2026-10-05",             # inicio del período de trabajo y del horario
        "horario": {"0": ["08:00", "13:00"], "1": ["08:00", "13:00"]},   # 0 = lunes
        "fuente": "texto libre"            # opcional
    }]}

Es idempotente: no repite a quien ya tiene ficha (mismo id de reloj) ni cuenta (mismo usuario).
"""

from __future__ import annotations

import csv
import json
import secrets
import unicodedata
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Agente, Area, Horario, Rol, Usuario
from .security import hash_password

ALFABETO = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ErrorImportacion(Exception):
    pass


def _ascii(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if c.isalnum() and ord(c) < 128)


def usuario_sugerido(nombre: str) -> str:
    partes = nombre.split()
    if len(partes) == 1:
        return _ascii(partes[0])
    return f"{_ascii(partes[0])}.{_ascii(partes[-1])}"


def clave_temporal() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(5)) + "-" + "".join(secrets.choice("23456789") for _ in range(3)) + secrets.choice(ALFABETO)


def importar(db: Session, ruta: Path, *, crear_usuarios: bool, password_comun: str | None = None) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        filas = datos["agentes"]
    except (OSError, ValueError, KeyError) as e:
        raise ErrorImportacion(f"No se pudo leer el archivo: {e}") from e

    areas = {a.nombre: a for a in db.execute(select(Area)).scalars()}
    roles = {r.nombre: r for r in db.execute(select(Rol)).scalars()}
    usuarios_existentes = {u for (u,) in db.execute(select(Usuario.usuario))}
    relojes = {r for (r,) in db.execute(select(Agente.id_reloj)) if r}
    resumen = {"fichas": 0, "cuentas": 0, "omitidos": [], "credenciales": []}

    for n, f in enumerate(filas, start=1):
        nombre = (f.get("nombre") or "").strip()
        if not nombre:
            raise ErrorImportacion(f"Fila {n}: falta el nombre.")
        area = areas.get(f.get("area") or "")
        if f.get("area") and area is None:
            raise ErrorImportacion(f"Fila {n} ({nombre}): el área «{f['area']}» no existe en SULAM.")
        rol_nombre = f.get("rol") or "Técnico"
        if crear_usuarios and rol_nombre not in roles:
            raise ErrorImportacion(f"Fila {n} ({nombre}): el rol «{rol_nombre}» no existe en SULAM.")
        id_reloj = str(f["id_reloj"]) if f.get("id_reloj") not in (None, "") else None
        if id_reloj and id_reloj in relojes:
            resumen["omitidos"].append(f"{nombre} (id de reloj {id_reloj} ya cargado)")
            continue
        desde = date.fromisoformat(f["desde"]) if f.get("desde") else date.today()

        usuario = None
        if crear_usuarios:
            base = f.get("usuario") or usuario_sugerido(nombre)
            login, k = base, 1
            while login in usuarios_existentes:
                k += 1
                login = f"{base}{k}"
            clave = password_comun or clave_temporal()
            usuario = Usuario(
                usuario=login, nombre_completo=nombre, area_id=area.id if area else None,
                password_hash=hash_password(clave), debe_cambiar_password=True,
            )
            usuario.roles = [roles[rol_nombre]]
            db.add(usuario)
            db.flush()
            usuarios_existentes.add(login)
            resumen["cuentas"] += 1
            resumen["credenciales"].append((login, nombre, rol_nombre, clave))

        agente = Agente(
            nombre=nombre, usuario_id=usuario.id if usuario else None, area_id=area.id if area else None,
            cargo=rol_nombre if crear_usuarios else None, id_reloj=id_reloj, boleta=(str(f["boleta"]) if f.get("boleta") else None),
            periodos=[{"desde": desde.isoformat(), "hasta": None}],
        )
        db.add(agente)
        db.flush()
        if f.get("horario"):
            db.add(Horario(
                agente_id=agente.id, vigente_desde=desde, semana=f["horario"], confirmado=False,
                fuente=f.get("fuente") or "Importado desde archivo local; pendiente de confirmar",
            ))
        if id_reloj:
            relojes.add(id_reloj)
        resumen["fichas"] += 1
    return resumen


def guardar_credenciales(resumen: dict, destino: Path) -> None:
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["usuario", "nombre", "rol", "contraseña temporal (se cambia al primer ingreso)"])
        w.writerows(resumen["credenciales"])

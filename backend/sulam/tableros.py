"""Diseño de los tableros de inicio: qué bloques (widgets) ve cada perfil, en qué orden y de qué ancho.

El catálogo de bloques es de código (cada uno sabe dibujarse en la interfaz); lo que se guarda, desde Administración, es el
diseño de cada perfil: orden, ancho (en doceavos de la fila) y visibilidad. Un bloque nuevo que aparezca en una versión
futura se suma solo al final del diseño guardado.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Ajuste

CLAVE = "tableros"
ANCHO_MIN, ANCHO_MAX = 3, 12

# Bloques que puede mostrar cualquier perfil (avisos de cosas pendientes).
COMUNES = [
    {"id": "novedades", "titulo": "Novedades para confirmar", "ancho": 12},
    {"id": "pases", "titulo": "Carpetas para entregar o recibir", "ancho": 12},
    {"id": "pedidos", "titulo": "Pedidos de personal para aprobar", "ancho": 12},
]

# Bloques propios de cada perfil, en su orden original. La interfaz tiene un dibujo por cada ``id``.
WIDGETS: dict[str, list[dict]] = {
    "tecnico": [
        {"id": "indicadores", "titulo": "Indicadores de mis casos", "ancho": 12},
        {"id": "para_terminar", "titulo": "Para terminar (informes en borrador, registros que faltan)", "ancho": 12},
        {"id": "mis_casos", "titulo": "Mis casos, por urgencia", "ancho": 12},
    ],
    "jefatura": [
        {"id": "indicadores", "titulo": "Indicadores del departamento", "ancho": 12},
        {"id": "equipo", "titulo": "Equipo y carga de casos", "ancho": 6},
        {"id": "para_asignar", "titulo": "Casos para asignar", "ancho": 6},
        {"id": "sin_movimiento", "titulo": "Casos sin movimiento", "ancho": 12},
    ],
    "direccion": [
        {"id": "indicadores", "titulo": "Indicadores del año", "ancho": 12},
        {"id": "participacion", "titulo": "Participación y Sensibilización · resumen semanal", "ancho": 12},
        {"id": "por_departamento", "titulo": "Casos por departamento", "ancho": 6},
        {"id": "maltrato", "titulo": "Maltrato del mes", "ancho": 6},
        {"id": "para_seguir", "titulo": "Para seguir", "ancho": 12},
        {"id": "actividad_reciente", "titulo": "Actividad reciente", "ancho": 12},
    ],
    "mesa": [
        {"id": "indicadores", "titulo": "Indicadores de ingresos", "ancho": 12},
        {"id": "accesos", "titulo": "Accesos rápidos", "ancho": 12},
        {"id": "para_vincular", "titulo": "Ingresos para vincular", "ancho": 6},
        {"id": "mis_ingresos", "titulo": "Mis últimos ingresos", "ancho": 6},
    ],
    "carga": [
        {"id": "indicadores", "titulo": "Indicadores de carga", "ancho": 12},
        {"id": "accesos", "titulo": "Accesos rápidos", "ancho": 12},
        {"id": "sin_registro", "titulo": "Falta cargar el registro de demanda", "ancho": 12},
        {"id": "sin_escaneo", "titulo": "Falta adjuntar el escaneo del original", "ancho": 12},
    ],
    "administrativo_area": [
        {"id": "indicadores", "titulo": "Indicadores del área", "ancho": 12},
        {"id": "casos_area", "titulo": "Casos del área", "ancho": 12},
        {"id": "expedientes", "titulo": "Expedientes recientes", "ancho": 6},
        {"id": "documentos", "titulo": "Documentos que cargué", "ancho": 6},
    ],
    "personal": [
        {"id": "indicadores", "titulo": "Indicadores de personal", "ancho": 12},
        {"id": "hoy_no_estan", "titulo": "Hoy no están", "ancho": 12},
    ],
    "participacion": [
        {"id": "indicadores", "titulo": "Indicadores de la semana", "ancho": 12},
        {"id": "resumen_semana", "titulo": "Resumen de la semana", "ancho": 6},
        {"id": "para_completar", "titulo": "Para completar (asistentes y fotos)", "ancho": 6},
        {"id": "campanias", "titulo": "Campañas activas", "ancho": 12},
    ],
}


def catalogo(perfil: str) -> list[dict]:
    """Todos los bloques que puede tener el tablero de un perfil, en su orden original."""
    return [*COMUNES, *WIDGETS.get(perfil, [])]


def _guardados(db: Session) -> dict:
    a = db.get(Ajuste, CLAVE)
    return a.valor if a is not None and isinstance(a.valor, dict) else {}


def _ancho(valor, defecto: int) -> int:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and ANCHO_MIN <= valor <= ANCHO_MAX else defecto


def diseno(db: Session, perfil: str) -> list[dict]:
    """Diseño vigente del perfil: ``[{id, ancho, visible}]`` en orden. Sin diseño guardado, el original (los bloques propios
    primero y los avisos comunes arriba, como siempre)."""
    cat = {w["id"]: w for w in catalogo(perfil)}
    guardado = _guardados(db).get(perfil)
    if not isinstance(guardado, list):
        return [{"id": w["id"], "ancho": w["ancho"], "visible": True} for w in catalogo(perfil)]
    salida, vistos = [], set()
    for g in guardado:
        if isinstance(g, dict) and g.get("id") in cat and g["id"] not in vistos:
            vistos.add(g["id"])
            salida.append({"id": g["id"], "ancho": _ancho(g.get("ancho"), cat[g["id"]]["ancho"]), "visible": bool(g.get("visible", True))})
    # Bloques que se agregaron al sistema después de guardar el diseño: quedan al final y visibles.
    salida += [{"id": w["id"], "ancho": w["ancho"], "visible": True} for w in catalogo(perfil) if w["id"] not in vistos]
    return salida


def personalizado(db: Session, perfil: str) -> bool:
    return isinstance(_guardados(db).get(perfil), list)


def guardar(db: Session, perfil: str, items: list[dict]) -> list[dict]:
    a = db.get(Ajuste, CLAVE)
    if a is None:
        a = Ajuste(clave=CLAVE, valor={})
        db.add(a)
    todo = dict(a.valor) if isinstance(a.valor, dict) else {}
    todo[perfil] = [{"id": i["id"], "ancho": i["ancho"], "visible": i["visible"]} for i in items]
    a.valor = todo  # se reasigna: SQLAlchemy no detecta cambios dentro del JSON
    db.flush()
    return diseno(db, perfil)


def restablecer(db: Session, perfil: str) -> None:
    a = db.get(Ajuste, CLAVE)
    if a is not None and isinstance(a.valor, dict) and perfil in a.valor:
        todo = dict(a.valor)
        todo.pop(perfil)
        a.valor = todo
        db.flush()

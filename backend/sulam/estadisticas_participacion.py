"""Estadísticas de Participación y Sensibilización Ciudadana: eventos, asistentes, campañas e instituciones."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import estadisticas as E
from .models import EventoAgenda, EventoParticipacion
from .permissions import Contexto
from .security import ahora


def preparar(ctx: Contexto, desde: date | None, hasta: date | None, area_id: int | None) -> E.Consulta:
    """Alcance: el de Participación o, si no lo tiene, el de Estadísticas (todos o el área propia)."""
    orden = {"propios": 0, "asignados": 1, "area": 2, "todos": 3}
    alcances = [a for a in (ctx.alcance("participacion", "consultar"), ctx.alcance("estadisticas", "consultar")) if a]
    if not alcances:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permiso para ver las estadísticas de Participación.")
    alcance = max(alcances, key=lambda a: orden[a])
    if alcance != "todos":
        if ctx.usuario.area_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Su usuario no tiene área asignada.")
        if area_id not in (None, ctx.usuario.area_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede ver las estadísticas de su área.")
        area_id = ctx.usuario.area_id
    hoy = date.today()
    hasta = hasta or hoy
    desde = desde or hasta.replace(month=1, day=1)
    if hasta < desde:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha «hasta» es anterior a «desde».")
    if (hasta - desde).days > 3660:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El período no puede superar diez años.")
    return E.Consulta(desde, hasta, area_id, alcance, [], False)


def participacion(db: Session, q: E.Consulta) -> dict:
    ini, fin = E._inicio(q.desde), E._fin(q.hasta)
    consulta = (
        select(EventoAgenda, EventoParticipacion)
        .join(EventoParticipacion, EventoParticipacion.evento_id == EventoAgenda.id)
        .where(EventoAgenda.inicio >= ini, EventoAgenda.inicio < fin)
        .order_by(EventoAgenda.inicio)
    )
    if q.area_id is not None:
        consulta = consulta.where(EventoAgenda.area_id == q.area_id)
    filas = db.execute(consulta).all()
    ahora_ = ahora()
    vigentes = [(e, x) for e, x in filas if e.estado != "cancelado"]
    realizados = [(e, x) for e, x in vigentes if e.estado == "realizado"]
    con_dato = [x.asistentes for _, x in realizados if x.asistentes is not None]
    asistentes = sum(con_dato)
    pasados_sin_resultado = [1 for e, _ in vigentes if e.estado == "programado" and e.inicio < ahora_]

    def agrupar(clave, filtro=lambda e, x: True) -> list[dict]:
        acc: dict[str, dict] = defaultdict(lambda: {"cantidad": 0, "realizados": 0, "asistentes": 0})
        for e, x in vigentes:
            if not filtro(e, x):
                continue
            k = clave(e, x)
            acc[k]["cantidad"] += 1
            if e.estado == "realizado":
                acc[k]["realizados"] += 1
                acc[k]["asistentes"] += x.asistentes or 0
        return [{"etiqueta": k, **v} for k, v in sorted(acc.items(), key=lambda kv: (-kv[1]["cantidad"], kv[0]))]

    columnas = ["cantidad", "realizados", "asistentes"]
    mensual = []
    for y, m in E._meses(q.desde, q.hasta):
        del_mes = [(e, x) for e, x in vigentes if E._local(e.inicio).year == y and E._local(e.inicio).month == m]
        mensual.append({
            "etiqueta": E._texto_mes(y, m), "cantidad": len(del_mes),
            "realizados": len([1 for e, _ in del_mes if e.estado == "realizado"]),
            "asistentes": sum(x.asistentes or 0 for e, x in del_mes if e.estado == "realizado"),
        })
    instituciones = Counter(i for _, x in vigentes for i in x.todas_las_instituciones)
    por_estado = Counter(e.estado for e, _ in filas)
    etiquetas_estado = {"programado": "Por realizar", "realizado": "Realizados", "no_realizado": "No realizados", "cancelado": "Cancelados"}
    return {
        "periodo": {"desde": q.desde.isoformat(), "hasta": q.hasta.isoformat()},
        "resumen": [
            {"clave": "eventos", "etiqueta": "Eventos planificados", "valor": len(vigentes), "nota": "sin contar los cancelados"},
            {"clave": "realizados", "etiqueta": "Eventos realizados", "valor": len(realizados), "pct": E._pct(len(realizados), len(vigentes))},
            {"clave": "asistentes", "etiqueta": "Asistentes en total", "valor": asistentes, "nota": f"{len(con_dato)} de {len(realizados)} eventos con asistentes cargados"},
            {"clave": "promedio", "etiqueta": "Asistentes por evento (promedio)", "valor": round(asistentes / len(con_dato), 1) if con_dato else None},
            {"clave": "en_campania", "etiqueta": "Eventos de campañas", "valor": len([1 for _, x in vigentes if x.campania_id]), "pct": E._pct(len([1 for _, x in vigentes if x.campania_id]), len(vigentes))},
            {"clave": "otras", "etiqueta": "A cargo de otras organizaciones", "valor": len([1 for _, x in vigentes if x.organiza_otra])},
            {"clave": "presencia", "etiqueta": "Con presencia de la Dirección sugerida", "valor": len([1 for _, x in vigentes if x.sugerir_directora])},
            {"clave": "sin_resultado", "etiqueta": "Pasaron sin registrar el resultado", "valor": len(pasados_sin_resultado)},
        ],
        "tablas": [
            E.tabla("mensual", "Eventos por mes", mensual, columnas=columnas),
            E.tabla("estados", "Estado de los eventos", [{"etiqueta": etiquetas_estado[k], "cantidad": por_estado[k]} for k in etiquetas_estado if por_estado[k]]),
            E.tabla("por_tipo", "Por tipo de evento", agrupar(lambda e, x: x.tipo.nombre), columnas=columnas),
            E.tabla("por_campania", "Por campaña", agrupar(lambda e, x: x.campania.nombre if x.campania else "Sin campaña"), columnas=columnas),
            E.tabla("organiza", "Quién organiza", agrupar(lambda e, x: x.organiza_otra or "La propia Dirección"), columnas=columnas),
            E.tabla("instituciones", "Instituciones con las que se coordina (las más frecuentes)", [{"etiqueta": k, "cantidad": v} for k, v in instituciones.most_common(15)]),
        ],
    }

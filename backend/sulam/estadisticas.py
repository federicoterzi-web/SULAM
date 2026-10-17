"""Estadísticas de SULAM: casos y funcionamiento interno.

Todo se calcula sobre la base, con el alcance de quien consulta:
- alcance «todos» (Dirección, Directora): toda la Dirección o el área elegida;
- alcance «área» (jefaturas): solo su área.

Cada tabla de casos trae, por fila, el filtro que la reproduce en la lista de
casos (mismo catálogo que sulam/filtros.py), para «tocar un número y ver los casos».
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import median
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from . import filtros as FL
from . import formularios as F
from .models import (
    Agente,
    Area,
    Caso,
    CasoAsignacion,
    CasoEvolucion,
    Documento,
    Informe,
    Ingreso,
    Justificativo,
    Novedad,
    NovedadLectura,
    Pase,
    Persona,
    PlantillaInforme,
    RegistroDemanda,
    Reiteracion,
    SolicitudPersonal,
    TipoDocumental,
    UbicacionFisica,
    Usuario,
)
from .permissions import Contexto

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS_SIN_ACTIVIDAD = 30
MAX_DIAS_ASISTENCIA = 370


# ---------------------------------------------------------------- alcance y período


@dataclass
class Consulta:
    desde: date
    hasta: date
    area_id: int | None  # área efectiva (forzada para jefaturas)
    alcance: str | None  # «todos», «area» o None (sin estadísticas: solo asistencia)
    filtros: list[dict]
    asistencia: bool  # puede ver la asistencia del personal

    @property
    def filtros_base(self) -> list[dict]:
        """Filtros de la lista de casos que reproducen el universo (sin el período)."""
        base = list(self.filtros)
        if self.area_id is not None:
            base.append({"c": "caso.area", "o": "es", "v": [str(self.area_id)]})
        return base

    @property
    def filtro_periodo(self) -> dict:
        return {"c": "caso.fecha_ingreso", "o": "entre", "v": {"desde": self.desde.isoformat(), "hasta": self.hasta.isoformat()}}


def preparar(ctx: Contexto, desde: date | None, hasta: date | None, area_id: int | None, f: str | None, *, para: str) -> Consulta:
    alcance = ctx.alcance("estadisticas", "consultar")
    asistencia = ctx.tiene("personal", "consultar") or alcance is not None
    if alcance is None and not (para == "interno" and ctx.tiene("personal", "consultar")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permiso para ver estadísticas.")
    if alcance not in (None, "todos"):
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
    return Consulta(desde, hasta, area_id, alcance, FL.leer(f), asistencia)


def _inicio(d: date) -> datetime:
    return datetime.combine(d, time.min).astimezone()


def _fin(d: date) -> datetime:
    return _inicio(d + timedelta(days=1))


def _local(dt: datetime | None) -> date | None:
    return dt.astimezone().date() if dt else None


def _meses(desde: date, hasta: date) -> list[tuple[int, int]]:
    salida, y, m = [], desde.year, desde.month
    while (y, m) <= (hasta.year, hasta.month):
        salida.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return salida


def _texto_mes(y: int, m: int) -> str:
    return f"{MESES[m - 1]} {y}"


def _mediana(valores: list[float]) -> float | None:
    return round(median(valores), 1) if valores else None


def _pct(parte: int, total: int) -> float | None:
    return round(100 * parte / total, 1) if total else None


def tabla(clave: str, titulo: str, filas: list[dict], *, base: int | None = None, nota: str | None = None, columnas: list[str] | None = None) -> dict:
    """Una tabla de la página: filas {etiqueta, cantidad, filtro?, extra…}."""
    return {"clave": clave, "titulo": titulo, "filas": filas, "base": base, "nota": nota, "columnas": columnas}


# ---------------------------------------------------------------- casos


def _universo(db: Session, q: Consulta):
    """Casos del alcance que cumplen los filtros (sin período)."""
    cond = [FL.condicion("casos", q.filtros)]
    if q.area_id is not None:
        cond.append(Caso.area_id == q.area_id)
    return and_(*cond)


def _rango_edad(nac: date | None, hoy: date) -> tuple[str, dict | None, str]:
    if nac is None:
        return "sin", None, "Sin dato"
    e = hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
    if e < 60:
        return "a", {"hasta": 59}, "Menos de 60"
    if e >= 90:
        return "z", {"desde": 90}, "90 o más"
    a = 60 + 5 * ((e - 60) // 5)
    return f"b{a}", {"desde": a, "hasta": a + 4}, f"{a} a {a + 4}"


def _contar(
    clave: str,
    titulo: str,
    valores: Iterable[Any],
    etiquetas: dict[str, str],
    campo: str,
    *,
    multiple: bool = False,
    total: int,
    orden: list[str] | None = None,
    op: str | None = None,
    nota: str | None = None,
    convertir=str,
    sin_fila: bool = False,
) -> dict:
    """Cuenta casos por valor. ``valores``: un valor (o una lista, si ``multiple``) por caso."""
    cuenta: Counter = Counter()
    sin = 0
    for v in valores:
        lista = (v or []) if multiple else ([] if v in (None, "") else [v])
        if not lista:
            sin += 1
        for x in set(lista):
            cuenta[x] += 1
    claves = [k for k in (orden or []) if k in cuenta] + sorted((k for k in cuenta if k not in (orden or [])), key=lambda k: -cuenta[k])
    operador = op or ("alguno" if multiple else "es")
    filas = [
        {"etiqueta": etiquetas.get(str(k), str(k)), "cantidad": cuenta[k], "pct": _pct(cuenta[k], total),
         "filtro": [{"c": campo, "o": operador, "v": [convertir(k)]}]}
        for k in claves
    ]
    if sin and not sin_fila:
        filas.append({"etiqueta": "Sin dato", "cantidad": sin, "pct": _pct(sin, total), "filtro": [{"c": campo, "o": "vacio"}], "sin_dato": True})
    return tabla(clave, titulo, filas, base=total, nota=nota)


def casos(db: Session, q: Consulta) -> dict:
    hoy = date.today()
    universo = _universo(db, q)
    fecha_ingreso = Caso.fecha_ingreso
    filas = db.execute(
        select(Caso, Persona).join(Persona, Persona.id == Caso.persona_id).where(universo, fecha_ingreso >= q.desde, fecha_ingreso <= q.hasta)
    ).all()
    total = len(filas)
    ids = [c.id for c, _ in filas]

    # Resumen
    cerrados = db.execute(
        select(func.count(Caso.id)).select_from(Caso).join(Persona, Persona.id == Caso.persona_id)
        .where(universo, Caso.estado == "cerrado", Caso.cerrado_en >= _inicio(q.desde), Caso.cerrado_en < _fin(q.hasta))
    ).scalar_one()
    activos_hoy = db.execute(
        select(func.count(Caso.id)).select_from(Caso).join(Persona, Persona.id == Caso.persona_id).where(universo, Caso.estado != "cerrado")
    ).scalar_one()
    reiteraciones = db.execute(
        select(func.count(Reiteracion.id)).select_from(Reiteracion).join(Caso, Caso.id == Reiteracion.caso_id).join(Persona, Persona.id == Caso.persona_id)
        .where(universo, Reiteracion.fecha >= q.desde, Reiteracion.fecha <= q.hasta)
    ).scalar_one()
    maltrato = sum(1 for c, _ in filas if any(str(i).startswith("maltrato") for i in c.indicadores or []))
    personas = len({p.id for _, p in filas})
    resumen = [
        {"clave": "ingresados", "etiqueta": "Casos ingresados", "valor": total, "filtro": [q.filtro_periodo]},
        {"clave": "personas", "etiqueta": "Personas distintas", "valor": personas},
        {"clave": "maltrato", "etiqueta": "Con indicadores de maltrato", "valor": maltrato, "pct": _pct(maltrato, total),
         "filtro": [q.filtro_periodo, {"c": "caso.indicadores", "o": "alguno", "v": ["maltrato"]}]},
        {"clave": "cerrados", "etiqueta": "Casos cerrados en el período", "valor": cerrados,
         "filtro": [{"c": "caso.cerrado_en", "o": "entre", "v": {"desde": q.desde.isoformat(), "hasta": q.hasta.isoformat()}}]},
        {"clave": "activos", "etiqueta": "Casos activos hoy", "valor": activos_hoy, "filtro": [{"c": "caso.estado", "o": "no_es", "v": ["cerrado"]}],
         "nota": "Sin importar cuándo ingresaron."},
        {"clave": "reiteraciones", "etiqueta": "Reiteraciones registradas", "valor": reiteraciones,
         "filtro": [{"c": "caso.reiteracion", "o": "entre", "v": {"desde": q.desde.isoformat(), "hasta": q.hasta.isoformat()}}]},
    ]

    # Evolución mensual: ingresos y cierres
    por_mes_ing = Counter((c.fecha_ingreso.year, c.fecha_ingreso.month) for c, _ in filas if c.fecha_ingreso)
    por_mes_cer: Counter = Counter()
    for (cer,) in db.execute(
        select(Caso.cerrado_en).join(Persona, Persona.id == Caso.persona_id)
        .where(universo, Caso.estado == "cerrado", Caso.cerrado_en >= _inicio(q.desde), Caso.cerrado_en < _fin(q.hasta))
    ).all():
        d = _local(cer)
        por_mes_cer[(d.year, d.month)] += 1
    mensual = []
    for y, m in _meses(q.desde, q.hasta):
        ini = max(q.desde, date(y, m, 1))
        fin = min(q.hasta, (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)))
        mensual.append({
            "etiqueta": _texto_mes(y, m), "ingresados": por_mes_ing[(y, m)], "cerrados": por_mes_cer[(y, m)],
            "filtro": [{"c": "caso.fecha_ingreso", "o": "entre", "v": {"desde": ini.isoformat(), "hasta": fin.isoformat()}}],
        })

    # Asignaciones activas y registros de demanda de esos casos
    responsables: dict = defaultdict(list)
    for a in db.execute(select(CasoAsignacion).where(CasoAsignacion.caso_id.in_(ids), CasoAsignacion.hasta.is_(None))).scalars():
        responsables[a.caso_id].append(str(a.usuario_id))
    demandas: dict = defaultdict(list)
    for r in db.execute(select(RegistroDemanda).where(RegistroDemanda.caso_id.in_(ids)).order_by(RegistroDemanda.fecha)).scalars():
        demandas[r.caso_id].append(r)
    ultima = {k: v[-1] for k, v in demandas.items()}
    areas = {str(a.id): a.nombre for a in db.execute(select(Area)).scalars()}
    usuarios = {str(u.id): u.nombre_completo for u in db.execute(select(Usuario)).scalars()}

    def jer(cat: dict, sub: bool) -> dict[str, str]:
        if not sub:
            return {g: t for g, (t, _) in cat.items()}
        return {f"{g}.{s}": f"{t}: {st}" for g, (t, subs) in cat.items() for s, st in subs.items()}

    def solo(nivel: str, lista):
        return [x for x in (lista or []) if ("." in x) == (nivel == "sub")]

    rangos = [_rango_edad(p.fecha_nacimiento, hoy) for _, p in filas]
    etiquetas_edad = {k: t for k, _, t in rangos}
    edad_filas = Counter(k for k, _, _ in rangos)
    edad_valor = {k: v for k, v, _ in rangos}
    tabla_edad = tabla(
        "edad", "Edad (hoy)",
        [
            {"etiqueta": etiquetas_edad[k], "cantidad": edad_filas[k], "pct": _pct(edad_filas[k], total),
             "filtro": [{"c": "persona.edad", "o": "entre", "v": edad_valor[k]}] if edad_valor[k] else [{"c": "persona.edad", "o": "vacio"}],
             **({"sin_dato": True} if k == "sin" else {})}
            for k in sorted(edad_filas)
        ],
        base=total,
    )

    dem = lambda attr: [getattr(ultima[c.id], attr) if c.id in ultima else None for c, _ in filas]  # noqa: E731
    nota_dem = "Según el último registro de demanda de cada caso."
    si_no = {"True": "Sí", "False": "No"}
    secciones = [
        {"titulo": "El caso", "tablas": [
            _contar("estado", "Estado actual", [c.estado for c, _ in filas], {e["valor"]: e["texto"] for e in FL.ESTADOS}, "caso.estado", total=total,
                    orden=["abierto", "en_seguimiento", "pausado", "cerrado"]),
            _contar("area", "Área", [str(c.area_id) if c.area_id else None for c, _ in filas], areas, "caso.area", total=total),
            _contar("responsable", "Técnico/a a cargo", [responsables.get(c.id) for c, _ in filas], usuarios, "caso.responsable", multiple=True, total=total, op="es",
                    nota="Un caso con varios técnicos cuenta para cada uno."),
            _contar("tipo_ingreso", "Tipo de ingreso", [c.tipo_ingreso for c, _ in filas], jer(F.TIPOS_INGRESO, False), "caso.tipo_ingreso", total=total),
            _contar("derivado_por", "Derivado por", [c.derivado_por for c, _ in filas], F.DERIVADO_POR, "caso.derivado_por", total=total),
        ]},
        {"titulo": "Indicadores e intervenciones", "tablas": [
            _contar("indicadores", "Indicadores", [solo("grupo", c.indicadores) for c, _ in filas], jer(F.INDICADORES, False), "caso.indicadores",
                    multiple=True, total=total, nota="Un caso puede tener varios indicadores."),
            _contar("indicadores_detalle", "Indicadores en detalle", [solo("sub", c.indicadores) for c, _ in filas], jer(F.INDICADORES, True), "caso.indicadores",
                    multiple=True, total=total, sin_fila=True),
            _contar("intervenciones", "Intervenciones", [solo("grupo", c.intervenciones) for c, _ in filas], jer(F.INTERVENCIONES, False), "caso.intervenciones",
                    multiple=True, total=total),
            _contar("intervenciones_detalle", "Intervenciones en detalle", [solo("sub", c.intervenciones) for c, _ in filas], jer(F.INTERVENCIONES, True),
                    "caso.intervenciones", multiple=True, total=total, sin_fila=True),
        ]},
        {"titulo": "Las personas", "tablas": [
            tabla_edad,
            _contar("genero", "Género", [p.genero for _, p in filas], F.GENEROS, "persona.genero", total=total),
            _contar("departamento", "Departamento", [p.departamento for _, p in filas], {}, "persona.departamento", total=total),
            _contar("cobertura_salud", "Cobertura de salud", [p.cobertura_salud for _, p in filas], F.COBERTURA_SALUD, "persona.cobertura_salud", multiple=True, total=total),
            _contar("cobertura_previsional", "Cobertura previsional", [p.cobertura_previsional for _, p in filas], F.COBERTURA_PREVISIONAL,
                    "persona.cobertura_previsional", multiple=True, total=total),
            _contar("cud", "CUD", [p.cud for _, p in filas], F.CUD, "persona.cud", total=total),
            _contar("discapacidades", "Discapacidad", [p.discapacidades for _, p in filas], F.DISCAPACIDAD, "persona.discapacidades", multiple=True, total=total),
        ]},
        {"titulo": "Situación según el registro de demanda", "tablas": [
            _contar("tipo_vivienda", "Tipo de vivienda", dem("tipo_vivienda"), F.TIPO_VIVIENDA, "demanda.tipo_vivienda", total=total, nota=nota_dem),
            _contar("estado_funcional", "Estado funcional", dem("estado_funcional"), F.ESTADO_FUNCIONAL, "demanda.estado_funcional", total=total, nota=nota_dem),
            _contar("tiene_autonomia", "Tiene autonomía", [None if x is None else str(x) for x in dem("tiene_autonomia")], si_no, "demanda.tiene_autonomia",
                    total=total, nota=nota_dem, convertir=lambda k: k == "True"),
            _contar("estado_civil", "Estado civil", dem("estado_civil"), F.ESTADO_CIVIL, "demanda.estado_civil", total=total, nota=nota_dem),
            _contar("tiene_hijos", "Tiene hijos", [None if x is None else str(x) for x in dem("tiene_hijos")], si_no, "demanda.tiene_hijos",
                    total=total, nota=nota_dem, convertir=lambda k: k == "True"),
        ]},
    ]
    # Los «sí/no» se filtran con «es» y valor booleano, no con lista.
    for s in secciones:
        for t in s["tablas"]:
            if t["clave"] in ("tiene_autonomia", "tiene_hijos"):
                for fila in t["filas"]:
                    if not fila.get("sin_dato"):
                        fila["filtro"] = [{"c": fila["filtro"][0]["c"], "o": "es", "v": fila["filtro"][0]["v"][0]}]
                    else:
                        fila["filtro"] = None  # «sin registro» no tiene filtro equivalente exacto
    return {
        "periodo": {"desde": q.desde.isoformat(), "hasta": q.hasta.isoformat()},
        "base": q.filtros_base,
        "periodo_filtro": q.filtro_periodo,
        "total": total,
        "resumen": resumen,
        "mensual": mensual,
        "secciones": secciones,
    }


def detalle_casos(db: Session, q: Consulta) -> list[dict]:
    """Una fila por caso del período, para el Excel."""
    hoy = date.today()
    filas = db.execute(
        select(Caso, Persona).join(Persona, Persona.id == Caso.persona_id)
        .where(_universo(db, q), Caso.fecha_ingreso >= q.desde, Caso.fecha_ingreso <= q.hasta).order_by(Caso.fecha_ingreso, Caso.numero)
    ).all()
    ids = [c.id for c, _ in filas]
    responsables: dict = defaultdict(list)
    for a in db.execute(select(CasoAsignacion).where(CasoAsignacion.caso_id.in_(ids), CasoAsignacion.hasta.is_(None))).scalars():
        responsables[a.caso_id].append(a.usuario.nombre_completo)
    areas = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}

    def textos(codigos, cat):
        salida = []
        for x in codigos or []:
            g, _, s = x.partition(".")
            nombre, subs = cat.get(g, (g, {}))
            if s:
                salida.append(f"{nombre}: {subs.get(s, s)}")
            elif not any(y.startswith(g + ".") for y in codigos):
                salida.append(nombre)
        return "; ".join(salida)

    salida = []
    for c, p in filas:
        _, _, rango = _rango_edad(p.fecha_nacimiento, hoy)
        salida.append({
            "Caso": c.numero, "Fecha de ingreso": c.fecha_ingreso, "Estado": c.estado.replace("_", " "), "Área": areas.get(c.area_id, ""),
            "Técnicos a cargo": ", ".join(responsables.get(c.id, [])), "Legajo": p.numero_legajo,
            "Apellidos y nombres": f"{p.apellidos}, {p.nombres}", "Rango de edad": rango, "Género": F.GENEROS.get(p.genero or "", ""),
            "Departamento": p.departamento or "", "Localidad": p.localidad or "",
            "Tipo de ingreso": F.TIPOS_INGRESO.get(c.tipo_ingreso or "", ("",))[0], "Derivado por": F.DERIVADO_POR.get(c.derivado_por or "", ""),
            "Indicadores": textos(c.indicadores, F.INDICADORES), "Intervenciones": textos(c.intervenciones, F.INTERVENCIONES),
            "Cierre": _local(c.cerrado_en),
        })
    return salida


# ---------------------------------------------------------------- funcionamiento interno


def _usuarios_en_alcance(db: Session, q: Consulta) -> list[Usuario]:
    consulta = select(Usuario).where(Usuario.activo.is_(True))
    if q.area_id is not None:
        consulta = consulta.where(Usuario.area_id == q.area_id)
    return list(db.execute(consulta.order_by(Usuario.nombre_completo)).scalars())


def carga(db: Session, q: Consulta) -> dict:
    hoy = date.today()
    limite = datetime.now().astimezone() - timedelta(days=DIAS_SIN_ACTIVIDAD)
    alcance = [] if q.area_id is None else [Caso.area_id == q.area_id]
    activos = list(db.execute(select(Caso).where(Caso.estado != "cerrado", *alcance)).scalars())
    ids_activos = [c.id for c in activos]
    asign = list(db.execute(select(CasoAsignacion).where(CasoAsignacion.caso_id.in_(ids_activos), CasoAsignacion.hasta.is_(None))).scalars())
    por_caso: dict = defaultdict(list)
    for a in asign:
        por_caso[a.caso_id].append(a.usuario_id)
    usuarios = {u.id: u for u in db.execute(select(Usuario)).scalars()}
    areas = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}

    # Por técnico/a
    tec: dict = defaultdict(lambda: {"activos": 0, "sin_actividad": 0, "asignados": 0, "cerrados": 0, "evoluciones": 0})
    for c in activos:
        for u in por_caso.get(c.id, []):
            tec[u]["activos"] += 1
            if c.ultima_actividad < limite:
                tec[u]["sin_actividad"] += 1
    for a in db.execute(
        select(CasoAsignacion).join(Caso, Caso.id == CasoAsignacion.caso_id)
        .where(CasoAsignacion.desde >= _inicio(q.desde), CasoAsignacion.desde < _fin(q.hasta), *alcance)
    ).scalars():
        tec[a.usuario_id]["asignados"] += 1
    for c in db.execute(
        select(Caso).where(Caso.estado == "cerrado", Caso.cerrado_en >= _inicio(q.desde), Caso.cerrado_en < _fin(q.hasta), *alcance)
    ).scalars():
        ult = db.execute(select(CasoAsignacion.usuario_id).where(CasoAsignacion.caso_id == c.id).order_by(CasoAsignacion.desde.desc()).limit(1)).scalar()
        if ult:
            tec[ult]["cerrados"] += 1
    evol_mes: Counter = Counter()
    for e in db.execute(
        select(CasoEvolucion).join(Caso, Caso.id == CasoEvolucion.caso_id).where(CasoEvolucion.en >= _inicio(q.desde), CasoEvolucion.en < _fin(q.hasta), *alcance)
    ).scalars():
        quien = e.usuario_id or e.autor_id
        if quien:
            tec[quien]["evoluciones"] += 1
        d = _local(e.en)
        evol_mes[(d.year, d.month)] += 1
    filas_tec = sorted(
        (
            {"etiqueta": usuarios[u].nombre_completo if u in usuarios else "—", "area": areas.get(usuarios[u].area_id, "") if u in usuarios else "", **v,
             "filtro": [{"c": "caso.responsable", "o": "es", "v": [str(u)]}, {"c": "caso.estado", "o": "no_es", "v": ["cerrado"]}]}
            for u, v in tec.items()
        ),
        key=lambda x: (-x["activos"], x["etiqueta"]),
    )

    # Por área
    por_area: dict = defaultdict(lambda: {"activos": 0, "sin_responsable": 0, "sin_actividad": 0})
    for c in activos:
        k = c.area_id
        por_area[k]["activos"] += 1
        if not por_caso.get(c.id):
            por_area[k]["sin_responsable"] += 1
        if c.ultima_actividad < limite:
            por_area[k]["sin_actividad"] += 1
    filas_area = sorted(
        ({"etiqueta": areas.get(k, "Sin área"), **v, "filtro": [{"c": "caso.area", "o": "es", "v": [str(k)]}, {"c": "caso.estado", "o": "no_es", "v": ["cerrado"]}] if k else None}
         for k, v in por_area.items()),
        key=lambda x: -x["activos"],
    )

    # Tiempos
    dias_asignar = []
    for ingreso, abierto, primera in db.execute(
        select(Caso.fecha_ingreso, Caso.abierto_en, func.min(CasoAsignacion.desde)).join(CasoAsignacion, CasoAsignacion.caso_id == Caso.id)
        .where(Caso.fecha_ingreso >= q.desde, Caso.fecha_ingreso <= q.hasta, *alcance).group_by(Caso.id)
    ).all():
        dias_asignar.append(max(0, (_local(primera) - (ingreso or _local(abierto))).days))
    duraciones = [
        max(0, (_local(c.cerrado_en) - (c.fecha_ingreso or _local(c.abierto_en))).days)
        for c in db.execute(select(Caso).where(Caso.estado == "cerrado", Caso.cerrado_en >= _inicio(q.desde), Caso.cerrado_en < _fin(q.hasta), *alcance)).scalars()
    ]
    quietud = [(hoy - _local(c.ultima_actividad)).days for c in activos]
    sin_resp = sum(1 for c in activos if not por_caso.get(c.id))
    resumen = [
        {"clave": "activos", "etiqueta": "Casos activos", "valor": len(activos), "filtro": [{"c": "caso.estado", "o": "no_es", "v": ["cerrado"]}]},
        {"clave": "sin_responsable", "etiqueta": "Activos sin técnico/a a cargo", "valor": sin_resp,
         "filtro": [{"c": "caso.estado", "o": "no_es", "v": ["cerrado"]}, {"c": "caso.responsable", "o": "vacio"}]},
        {"clave": "sin_actividad", "etiqueta": f"Activos sin movimiento hace más de {DIAS_SIN_ACTIVIDAD} días",
         "valor": sum(1 for c in activos if c.ultima_actividad < limite),
         "filtro": [{"c": "caso.estado", "o": "no_es", "v": ["cerrado"]},
                    {"c": "caso.ultima_actividad", "o": "entre", "v": {"hasta": (hoy - timedelta(days=DIAS_SIN_ACTIVIDAD + 1)).isoformat()}}]},
        {"clave": "dias_asignar", "etiqueta": "Días hasta asignar (mediana)", "valor": _mediana(dias_asignar), "nota": f"{len(dias_asignar)} casos ingresados en el período"},
        {"clave": "duracion", "etiqueta": "Duración de los casos cerrados (mediana, días)", "valor": _mediana(duraciones), "nota": f"{len(duraciones)} casos"},
        {"clave": "quietud", "etiqueta": "Días desde el último movimiento (mediana de los activos)", "valor": _mediana(quietud)},
    ]
    return {
        "resumen": resumen,
        "tablas": [
            tabla("tecnicos", "Carga por técnico/a", filas_tec, columnas=["activos", "sin_actividad", "asignados", "cerrados", "evoluciones"],
                  nota="Activos y sin movimiento: hoy. Asignados, cerrados y evoluciones: en el período."),
            tabla("areas", "Casos activos por área", filas_area, columnas=["activos", "sin_responsable", "sin_actividad"]),
            tabla("evoluciones_mes", "Evoluciones registradas por mes",
                  [{"etiqueta": _texto_mes(y, m), "cantidad": evol_mes[(y, m)]} for y, m in _meses(q.desde, q.hasta)]),
        ],
    }


def asistencia(db: Session, q: Consulta) -> dict | None:
    if not q.asistencia:
        return None
    from .asistencia import INCIDENCIAS
    from .routers.personal import CLASES_LICENCIA, TIPOS_SOLICITUD, _informe

    desde = max(q.desde, q.hasta - timedelta(days=MAX_DIAS_ASISTENCIA))
    agentes = list(db.execute(select(Agente)).scalars())
    if q.area_id is not None:
        agentes = [a for a in agentes if a.area_id == q.area_id]
    ids = {a.id for a in agentes}
    areas = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}
    filas = [f for f in _informe(db, desde, q.hasta, None) if f["agente_id"] in ids]
    evaluadas = [f for f in filas if f["estado"] != "sin_datos"]
    con_inc = [f for f in evaluadas if f["incidencias"] or f["incidencias_justificadas"]]
    por_tipo: Counter = Counter(i for f in evaluadas for i in f["incidencias"] + f["incidencias_justificadas"])
    por_estado: Counter = Counter(f["estado"] for f in evaluadas)
    minutos = sum(f["minutos_diferencia"] for f in evaluadas if f["estado"] in ("pendiente", "revisado"))
    nombre = {a.id: a for a in agentes}
    por_persona: dict = defaultdict(lambda: {"jornadas": 0, "con_incidencias": 0, "pendientes": 0, "minutos": 0})
    por_area: dict = defaultdict(lambda: {"personas": set(), "jornadas": 0, "con_incidencias": 0, "minutos": 0})
    for f in evaluadas:
        a = nombre[f["agente_id"]]
        p, ar = por_persona[a.id], por_area[a.area_id]
        p["jornadas"] += 1
        ar["jornadas"] += 1
        ar["personas"].add(a.id)
        if f["incidencias"] or f["incidencias_justificadas"]:
            p["con_incidencias"] += 1
            ar["con_incidencias"] += 1
        if f["estado"] == "pendiente":
            p["pendientes"] += 1
        if f["estado"] in ("pendiente", "revisado"):
            p["minutos"] += round(f["minutos_diferencia"])
            ar["minutos"] += round(f["minutos_diferencia"])

    # Pedidos que se superponen con el período
    pedidos = [
        s for s in db.execute(select(SolicitudPersonal).where(SolicitudPersonal.desde <= q.hasta, SolicitudPersonal.hasta >= desde)).scalars()
        if s.agente_id in ids
    ]

    def dias(s) -> int:
        return (min(s.hasta, q.hasta) - max(s.desde, desde)).days + 1

    vigentes = [s for s in pedidos if s.estado in ("aprobada", "registrada")]
    por_clase: Counter = Counter()
    dias_clase: Counter = Counter()
    for s in vigentes:
        k = f"{s.tipo}:{s.clase or ''}"
        por_clase[k] += 1
        dias_clase[k] += dias(s)

    def texto_clase(k: str) -> str:
        tipo, clase = k.split(":")
        return f"{TIPOS_SOLICITUD[tipo]}" + (f" · {CLASES_LICENCIA.get(clase, clase)}" if clase else "")

    justif: Counter = Counter(
        j.codigo for j in db.execute(select(Justificativo).where(Justificativo.desde <= q.hasta, Justificativo.hasta >= desde, Justificativo.estado == "aprobado")).scalars()
        if j.agente_id in ids
    )
    return {
        "periodo": {"desde": desde.isoformat(), "hasta": q.hasta.isoformat()},
        "recortado": desde != q.desde,
        "resumen": [
            {"clave": "personas", "etiqueta": "Personas en planta", "valor": len(agentes)},
            {"clave": "jornadas", "etiqueta": "Jornadas con marcas evaluadas", "valor": len(evaluadas)},
            {"clave": "con_incidencias", "etiqueta": "Jornadas con alguna incidencia", "valor": len(con_inc), "pct": _pct(len(con_inc), len(evaluadas))},
            {"clave": "pendientes", "etiqueta": "Pendientes de revisión", "valor": por_estado["pendiente"]},
            {"clave": "minutos", "etiqueta": "Horas de diferencia sin justificar", "valor": round(minutos / 60, 1)},
            {"clave": "pedidos", "etiqueta": "Pedidos esperando a la jefatura", "valor": sum(1 for s in pedidos if s.estado == "pendiente")},
        ],
        "tablas": [
            tabla("incidencias", "Incidencias por tipo",
                  [{"etiqueta": INCIDENCIAS.get(k, k), "cantidad": v} for k, v in por_tipo.most_common()],
                  nota="Incluye las ya justificadas. Una jornada puede tener más de una."),
            tabla("estado_jornadas", "Estado de las jornadas",
                  [{"etiqueta": t, "cantidad": por_estado[k]} for k, t in (("pendiente", "Pendiente"), ("revisado", "Revisado"), ("justificado", "Justificado"),
                                                                         ("auto_aprobado", "Aprobado automáticamente")) if por_estado[k]]),
            tabla("asistencia_areas", "Por área",
                  [{"etiqueta": areas.get(k, "Sin área"), "personas": len(v["personas"]), "jornadas": v["jornadas"], "con_incidencias": v["con_incidencias"],
                    "horas": round(v["minutos"] / 60, 1)} for k, v in sorted(por_area.items(), key=lambda x: -x[1]["con_incidencias"])],
                  columnas=["personas", "jornadas", "con_incidencias", "horas"]),
            tabla("asistencia_personas", "Por persona",
                  [{"etiqueta": nombre[k].nombre, "area": areas.get(nombre[k].area_id, ""), "jornadas": v["jornadas"], "con_incidencias": v["con_incidencias"],
                    "pendientes": v["pendientes"], "horas": round(v["minutos"] / 60, 1)}
                   for k, v in sorted(por_persona.items(), key=lambda x: (-x[1]["con_incidencias"], nombre[x[0]].nombre))],
                  columnas=["jornadas", "con_incidencias", "pendientes", "horas"]),
            tabla("licencias", "Licencias y comisiones (aprobadas)",
                  [{"etiqueta": texto_clase(k), "pedidos": v, "dias": dias_clase[k]} for k, v in por_clase.most_common()],
                  columnas=["pedidos", "dias"], nota="Días corridos dentro del período."),
            tabla("justificativos", "Justificativos aprobados por código", [{"etiqueta": k, "cantidad": v} for k, v in justif.most_common()]),
        ],
    }


def circuitos(db: Session, q: Consulta) -> dict:
    ini, fin = _inicio(q.desde), _fin(q.hasta)
    areas = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}
    alcance_caso = [] if q.area_id is None else [Caso.area_id == q.area_id]

    # Mesa de Entrada
    ingresos_q = select(Ingreso).where(Ingreso.fecha_ingreso >= ini, Ingreso.fecha_ingreso < fin)
    if q.area_id is not None:
        ingresos_q = ingresos_q.join(Caso, Caso.id == Ingreso.caso_id).where(*alcance_caso)
    ingresos = list(db.execute(ingresos_q).scalars())
    vinculados = [i for i in ingresos if i.persona_id]
    horas_vincular = [(i.vinculado_en - i.fecha_ingreso).total_seconds() / 3600 for i in vinculados if i.vinculado_en]
    por_mes: Counter = Counter((_local(i.fecha_ingreso).year, _local(i.fecha_ingreso).month) for i in ingresos)
    tipos = {t.id: t.nombre for t in db.execute(select(TipoDocumental)).scalars()}
    pendientes_hoy = db.execute(select(func.count(Ingreso.id)).where(Ingreso.persona_id.is_(None))).scalar_one() if q.area_id is None else None

    # Pases de carpetas
    pases_q = select(Pase).where(Pase.iniciado_en >= ini, Pase.iniciado_en < fin)
    if q.area_id is not None:
        pases_q = pases_q.where(or_(Pase.desde_area_id == q.area_id, Pase.hacia_area_id == q.area_id))
    pases = list(db.execute(pases_q).scalars())
    horas_pase = [(p.resuelto_en - p.iniciado_en).total_seconds() / 3600 for p in pases if p.estado == "hecho" and p.resuelto_en]
    hace2 = datetime.now().astimezone() - timedelta(days=2)
    pend_q = select(func.count(Pase.id)).where(Pase.estado == "pendiente", Pase.iniciado_en < hace2)
    if q.area_id is not None:
        pend_q = pend_q.where(or_(Pase.desde_area_id == q.area_id, Pase.hacia_area_id == q.area_id))
    ubic: Counter = Counter(u.area_id for u in db.execute(select(UbicacionFisica)).scalars())

    # Informes firmados y documentos
    inf_q = select(Informe, Caso).outerjoin(Caso, Caso.id == Informe.caso_id).where(Informe.estado == "firmado", Informe.firmado_en >= ini, Informe.firmado_en < fin)
    if q.area_id is not None:
        inf_q = inf_q.where(*alcance_caso)
    informes = db.execute(inf_q).all()
    plantillas = {p.id: p.nombre for p in db.execute(select(PlantillaInforme)).scalars()}
    docs_q = select(Documento).where(Documento.cargado_en >= ini, Documento.cargado_en < fin, Documento.eliminado_en.is_(None))
    if q.area_id is not None:
        docs_q = docs_q.join(Caso, Caso.id == Documento.caso_id).where(*alcance_caso)
    documentos = list(db.execute(docs_q).scalars())

    estados_pase = {"pendiente": "Pendiente", "hecho": "Entregado / recibido", "rechazado": "Rechazado", "cancelado": "Cancelado"}
    return {
        "resumen": [
            {"clave": "ingresos", "etiqueta": "Ingresos en Mesa de Entrada", "valor": len(ingresos)},
            {"clave": "vinculados", "etiqueta": "Vinculados a un legajo", "valor": len(vinculados), "pct": _pct(len(vinculados), len(ingresos))},
            {"clave": "horas_vincular", "etiqueta": "Horas hasta vincular (mediana)", "valor": _mediana(horas_vincular)},
            *([{"clave": "sin_vincular", "etiqueta": "Ingresos sin legajo hoy", "valor": pendientes_hoy}] if pendientes_hoy is not None else []),
            {"clave": "pases", "etiqueta": "Pases de carpetas", "valor": len(pases)},
            {"clave": "horas_pase", "etiqueta": "Horas hasta confirmar un pase (mediana)", "valor": _mediana(horas_pase)},
            {"clave": "pases_demorados", "etiqueta": "Pases pendientes hace más de 2 días", "valor": db.execute(pend_q).scalar_one()},
            {"clave": "informes", "etiqueta": "Informes firmados", "valor": len(informes)},
            {"clave": "documentos", "etiqueta": "Documentos digitalizados", "valor": len(documentos)},
        ],
        "tablas": [
            tabla("ingresos_mes", "Ingresos de Mesa de Entrada por mes", [{"etiqueta": _texto_mes(y, m), "cantidad": por_mes[(y, m)]} for y, m in _meses(q.desde, q.hasta)]),
            tabla("ingresos_tipo", "Ingresos por tipo de documento",
                  [{"etiqueta": tipos.get(k, "Sin tipo"), "cantidad": v} for k, v in Counter(i.tipo_documental_id for i in ingresos).most_common()]),
            tabla("pases_estado", "Pases por estado", [{"etiqueta": estados_pase.get(k, k), "cantidad": v} for k, v in Counter(p.estado for p in pases).most_common()]),
            tabla("pases_tipo", "Pases por tipo",
                  [{"etiqueta": {"pedido": "Pedido de carpeta", "envio": "Envío o devolución"}.get(k, k), "cantidad": v} for k, v in Counter(p.tipo for p in pases).most_common()]),
            tabla("carpetas_area", "Dónde están hoy las carpetas en papel",
                  [{"etiqueta": areas.get(k, "—"), "cantidad": v} for k, v in ubic.most_common() if q.area_id is None or k == q.area_id]),
            tabla("informes_plantilla", "Informes firmados por modelo",
                  [{"etiqueta": plantillas.get(k, "Sin modelo"), "cantidad": v} for k, v in Counter(i.plantilla_id for i, _ in informes).most_common()]),
            tabla("informes_area", "Informes firmados por área",
                  [{"etiqueta": areas.get(k, "Sin caso"), "cantidad": v} for k, v in Counter(c.area_id if c else None for _, c in informes).most_common()]),
            tabla("documentos_tipo", "Documentos digitalizados por tipo",
                  [{"etiqueta": tipos.get(k, "—"), "cantidad": v} for k, v in Counter(d.tipo_documental_id for d in documentos).most_common()]),
        ],
    }


def comunicacion(db: Session, q: Consulta) -> dict:
    ini, fin = _inicio(q.desde), _fin(q.hasta)
    nq = select(Novedad).where(Novedad.publicada_en >= ini, Novedad.publicada_en < fin)
    if q.area_id is not None:
        nq = nq.where(or_(Novedad.area_id.is_(None), Novedad.area_id == q.area_id))
    novedades = list(db.execute(nq.order_by(Novedad.publicada_en.desc())).scalars())
    usuarios = [u for u in db.execute(select(Usuario).where(Usuario.activo.is_(True))).scalars()]
    lecturas: dict = defaultdict(set)
    for l in db.execute(select(NovedadLectura).where(NovedadLectura.novedad_id.in_([n.id for n in novedades]))).scalars():
        lecturas[l.novedad_id].add(l.usuario_id)
    areas = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}
    filas, pend_area = [], Counter()
    total_dest = total_leidas = 0
    for n in novedades:
        dest = [u for u in usuarios if (n.area_id is None or u.area_id == n.area_id) and u.id != n.autor_id]
        if q.area_id is not None:
            dest = [u for u in dest if u.area_id == q.area_id]
        leidas = sum(1 for u in dest if u.id in lecturas[n.id])
        if n.requiere_confirmacion:
            total_dest += len(dest)
            total_leidas += leidas
            for u in dest:
                if u.id not in lecturas[n.id]:
                    pend_area[u.area_id] += 1
        filas.append({
            "etiqueta": n.titulo, "fecha": _local(n.publicada_en).isoformat(), "para": areas.get(n.area_id, "Toda la Dirección"),
            "destinatarios": len(dest), "confirmaron": leidas if n.requiere_confirmacion else None,
            "pct": _pct(leidas, len(dest)) if n.requiere_confirmacion else None, "retirada": n.retirada_en is not None,
        })
    return {
        "resumen": [
            {"clave": "novedades", "etiqueta": "Novedades publicadas", "valor": len(novedades)},
            {"clave": "de_direccion", "etiqueta": "De la Dirección (para todos)", "valor": sum(1 for n in novedades if n.area_id is None)},
            {"clave": "lectura", "etiqueta": "Lectura confirmada", "valor": _pct(total_leidas, total_dest), "unidad": "%",
             "nota": f"{total_leidas} de {total_dest} confirmaciones esperadas"},
        ],
        "tablas": [
            tabla("novedades", "Novedades y su lectura", filas, columnas=["fecha", "para", "destinatarios", "confirmaron", "pct"]),
            tabla("sin_confirmar_area", "Confirmaciones pendientes por área", [{"etiqueta": areas.get(k, "Sin área"), "cantidad": v} for k, v in pend_area.most_common()]),
        ],
    }


def interno(db: Session, q: Consulta) -> dict:
    solo_asistencia = q.alcance is None
    return {
        "periodo": {"desde": q.desde.isoformat(), "hasta": q.hasta.isoformat()},
        "carga": None if solo_asistencia else carga(db, q),
        "asistencia": asistencia(db, q),
        "circuitos": None if solo_asistencia else circuitos(db, q),
        "comunicacion": None if solo_asistencia else comunicacion(db, q),
    }

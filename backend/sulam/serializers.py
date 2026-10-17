"""Conversión de entidades a JSON."""

from __future__ import annotations

from .models import (
    Caso,
    CasoAsignacion,
    Documento,
    Expediente,
    Ingreso,
    Persona,
    PersonaVinculada,
    Usuario,
)


def usuario_breve(u: Usuario | None) -> dict | None:
    if u is None:
        return None
    return {"id": str(u.id), "usuario": u.usuario, "nombre_completo": u.nombre_completo}


def persona_resumen(p: Persona) -> dict:
    return {
        "id": str(p.id),
        "numero_legajo": p.numero_legajo,
        "legajo_provisorio": p.legajo_provisorio,
        "apellidos": p.apellidos,
        "nombres": p.nombres,
        "tipo_documento": p.tipo_documento,
        "numero_documento": p.numero_documento,
        "sin_documento": p.sin_documento,
        "fecha_nacimiento": p.fecha_nacimiento.isoformat() if p.fecha_nacimiento else None,
        "fecha_nacimiento_aproximada": p.fecha_nacimiento_aproximada,
        "localidad": p.localidad,
        "unificada_en_id": str(p.unificada_en_id) if p.unificada_en_id else None,
    }


def persona_detalle(p: Persona) -> dict:
    d = persona_resumen(p)
    d.update(
        {
            "motivo_sin_documento": p.motivo_sin_documento,
            "domicilio": p.domicilio,
            "telefono": p.telefono,
            "observaciones": p.observaciones,
            "genero": p.genero,
            "barrio": p.barrio,
            "departamento": p.departamento,
            "cud": p.cud,
            "cobertura_salud": p.cobertura_salud or [],
            "obra_social": p.obra_social,
            "cobertura_previsional": p.cobertura_previsional or [],
            "trabajo_informal": p.trabajo_informal,
            "discapacidades": p.discapacidades or [],
            "lat": p.lat,
            "lng": p.lng,
            "ubicacion_actualizada_en": p.ubicacion_actualizada_en.isoformat() if p.ubicacion_actualizada_en else None,
            "creado_en": p.creado_en.isoformat(),
            "actualizado_en": p.actualizado_en.isoformat() if p.actualizado_en else None,
        }
    )
    return d


def asignacion_out(a: CasoAsignacion) -> dict:
    return {
        "id": a.id,
        "usuario": usuario_breve(a.usuario),
        "desde": a.desde.isoformat(),
        "hasta": a.hasta.isoformat() if a.hasta else None,
        "motivo": a.motivo,
    }


CAMPOS_CARATULA = (
    "numero_actuacion", "anio_actuacion", "antecedentes", "tipo_ingreso", "tipo_ingreso_detalle",
    "derivado_por", "derivado_por_detalle", "intervencion_derivacion", "intervencion_otro",
)


def caratula_out(c: Caso) -> dict:
    d = {k: getattr(c, k) for k in CAMPOS_CARATULA}
    d["fecha_ingreso"] = (c.fecha_ingreso or c.abierto_en.date()).isoformat()
    d["fecha_ultimo_ingreso"] = c.fecha_ultimo_ingreso.isoformat() if c.fecha_ultimo_ingreso else None
    d["indicadores"] = c.indicadores or []
    d["intervenciones"] = c.intervenciones or []
    return d


def demanda_out(r, escaneos: list[str] | None = None) -> dict:
    from .models import RegistroDemanda

    base = {
        "id": str(r.id),
        "caso_id": str(r.caso_id),
        "persona_id": str(r.persona_id),
        "fecha": r.fecha.isoformat(),
        "receptor": usuario_breve(r.receptor)
        or ({"id": None, "usuario": None, "nombre_completo": r.receptor_nombre} if r.receptor_nombre else None),
        "cargado_por": usuario_breve(r.cargador),
        "cargado_desde_papel": r.cargado_desde_papel,
        "escaneos": escaneos or [],
        "creado_en": r.creado_en.isoformat(),
    }
    excluir = {
        "id", "caso_id", "persona_id", "fecha", "creado_por", "creado_en", "actualizado_en", "agente_id",
        "receptor_id", "receptor_nombre", "cargado_desde_papel",
    }
    for col in RegistroDemanda.__table__.columns.keys():
        if col not in excluir:
            base[col] = getattr(r, col)
    base["agente"] = usuario_breve(r.agente)
    base["actualizado_en"] = r.actualizado_en.isoformat() if r.actualizado_en else None
    return base


def caso_out(c: Caso, persona: Persona | None = None, detalle: bool = False) -> dict:
    d = {
        "id": str(c.id),
        "numero": c.numero,
        "persona_id": str(c.persona_id),
        "estado": c.estado,
        "area": {"id": c.area.id, "nombre": c.area.nombre} if c.area else None,
        "abierto_en": c.abierto_en.isoformat(),
        "cerrado_en": c.cerrado_en.isoformat() if c.cerrado_en else None,
        "ultima_actividad": c.ultima_actividad.isoformat() if c.ultima_actividad else None,
        "motivo": c.motivo,
        "caratula": caratula_out(c),
        "caratula_impresa_en": c.caratula_impresa_en.isoformat() if c.caratula_impresa_en else None,
        "responsables": [
            usuario_breve(a.usuario) for a in c.asignaciones if a.hasta is None
        ],
    }
    if persona is not None:
        d["persona"] = persona_resumen(persona)
    if detalle:
        d["historial_estados"] = [
            {
                "estado_anterior": h.estado_anterior,
                "estado_nuevo": h.estado_nuevo,
                "motivo": h.motivo,
                "usuario": usuario_breve(h.usuario),
                "en": h.en.isoformat(),
            }
            for h in c.historial_estados
        ]
        d["asignaciones"] = [asignacion_out(a) for a in c.asignaciones]
    return d


def vinculado_out(v: PersonaVinculada) -> dict:
    return {
        "id": str(v.id),
        "persona_id": str(v.persona_id),
        "tipo_vinculo": {"id": v.tipo_vinculo.id, "nombre": v.tipo_vinculo.nombre},
        "es_institucion": v.es_institucion,
        "activo": v.activo,
        "apellidos": v.apellidos,
        "nombres": v.nombres,
        "nombre_institucion": v.nombre_institucion,
        "numero_documento": v.numero_documento,
        "telefono": v.telefono,
        "domicilio": v.domicilio,
        "observaciones": v.observaciones,
    }


def expediente_out(e: Expediente) -> dict:
    return {
        "id": str(e.id),
        "numero": e.numero,
        "tipo": e.tipo,
        "organismo": e.organismo,
        "caratula": e.caratula,
        "persona_id": str(e.persona_id),
        "caso_id": str(e.caso_id) if e.caso_id else None,
        "observaciones": e.observaciones,
        "creado_en": e.creado_en.isoformat(),
    }


def ingreso_out(i: Ingreso, persona: Persona | None = None) -> dict:
    return {
        "id": str(i.id),
        "numero": i.numero,
        "fecha_ingreso": i.fecha_ingreso.isoformat(),
        "remitente": i.remitente,
        "tipo_documental": (
            {"id": i.tipo_documental.id, "nombre": i.tipo_documental.nombre}
            if i.tipo_documental
            else None
        ),
        "asunto": i.asunto,
        "folios": i.folios,
        "persona_mencionada": i.persona_mencionada,
        "documento_mencionado": i.documento_mencionado,
        "numero_expediente_externo": i.numero_expediente_externo,
        "observaciones": i.observaciones,
        "persona_id": str(i.persona_id) if i.persona_id else None,
        "persona": persona_resumen(persona) if persona else None,
        "caso_id": str(i.caso_id) if i.caso_id else None,
        "expediente_id": str(i.expediente_id) if i.expediente_id else None,
        "vinculado_en": i.vinculado_en.isoformat() if i.vinculado_en else None,
        "creado_en": i.creado_en.isoformat(),
    }


def documento_out(d: Documento, cargado_por: Usuario | None = None) -> dict:
    return {
        "id": str(d.id),
        "persona_id": str(d.persona_id) if d.persona_id else None,
        "caso_id": str(d.caso_id) if d.caso_id else None,
        "expediente_id": str(d.expediente_id) if d.expediente_id else None,
        "ingreso_id": str(d.ingreso_id) if d.ingreso_id else None,
        "registro_demanda_id": str(d.registro_demanda_id) if d.registro_demanda_id else None,
        "tipo_documental": {"id": d.tipo_documental.id, "nombre": d.tipo_documental.nombre},
        "cargado_en": d.cargado_en.isoformat(),
        "eliminado": d.eliminado_en is not None,
        "titulo": d.titulo,
        "descripcion": d.descripcion,
        "nombre_original": d.nombre_original,
        "mime": d.mime,
        "tamano": d.tamano,
        "sha256": d.sha256,
        "cargado_por": usuario_breve(cargado_por),
    }


def reiteracion_out(r) -> dict:
    return {
        "id": r.id,
        "fecha": r.fecha.isoformat(),
        "motivo": r.motivo,
        "tipo_ingreso": r.tipo_ingreso,
        "tipo_ingreso_detalle": r.tipo_ingreso_detalle,
        "derivado_por": r.derivado_por,
        "derivado_por_detalle": r.derivado_por_detalle,
        "ingreso_id": str(r.ingreso_id) if r.ingreso_id else None,
        "usuario": usuario_breve(r.usuario),
        "en": r.en.isoformat(),
    }


def evolucion_out(e) -> dict:
    return {
        "id": e.id,
        "texto": e.texto,
        "fecha": (e.fecha or e.en.date()).isoformat(),
        "autor": usuario_breve(e.autor)
        or ({"id": None, "usuario": None, "nombre_completo": e.autor_nombre} if e.autor_nombre else None),
        "usuario": usuario_breve(e.usuario),
        "en": e.en.isoformat(),
    }

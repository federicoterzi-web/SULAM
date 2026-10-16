"""Opciones de los formularios institucionales.

Fuente: «Modelo de carátula de legajo» y «Registro de demanda» de la Dirección
de Adultos Mayores (octubre 2026). Los textos se respetan tal como figuran en
los modelos; los códigos son internos y estables (sirven para estadísticas).

Las opciones con subopciones se guardan como lista de códigos: el código del
grupo ("maltrato") y los de sus subopciones ("maltrato.fisico").
"""

from __future__ import annotations

from fastapi import HTTPException, status

GENEROS = {"F": "Femenino", "M": "Masculino", "otro": "Otro"}

CUD = {"si": "Sí", "no": "No", "en_tramite": "En trámite"}

INDICADORES = {
    "maltrato": ("Maltrato", {
        "fisico": "Físico", "psicologico": "Psicológico", "sexual": "Sexual",
        "economico": "Económico/Patrimonial",
    }),
    "negligencia": ("Negligencia", {"aislamiento": "Aislamiento", "abandono": "Abandono"}),
    "situacion_calle": ("Situación de calle", {}),
    "vulnerabilidad": ("Vulnerabilidad", {
        "economica": "Económica", "habitacional": "Habitacional",
        "socio_sanitaria": "Socio sanitaria", "alimentaria": "Alimentaria",
    }),
    "no_califica": ("No califica como indicador", {}),
}

INTERVENCIONES = {
    "asesoramiento": ("Asesoramiento", {}),
    "subsidio": ("Subsidio", {
        "cuidados": "Para cuidados", "economico": "Económico", "material": "Material",
        "alimentario": "Alimentario",
    }),
    "internacion_rle": ("Internación en RLE", {}),
    "derivacion": ("Derivación", {}),
    "otro": ("Otro", {}),
}

TIPOS_INGRESO = {
    "espontaneo": ("Espontáneo", {"presencial": "Presencial", "no_presencial": "No presencial"}),
    "mesa_entrada": ("Mesa de Entrada", {"amparo": "Amparo"}),
    "portal_sae": ("Portal SAE", {}),
    "derivada": ("Derivada", {}),
}

DERIVADO_POR = {
    "gobierno_local": "Gobierno Local",
    "mpf": "MPF",
    "poder_judicial": "Poder Judicial",
    "siprosa": "SIPROSA",
    "ministerio_seguridad": "Ministerio de Seguridad",
    "otro": "Otro",
}

COBERTURA_PREVISIONAL = {
    "jubilacion": "Jubilación", "pension": "Pensión", "puam": "PUAM", "pnc": "PNC",
    "sin_cobertura": "Sin cobertura", "en_tramite": "En trámite",
}

COBERTURA_SALUD = {
    "pami": "PAMI", "ipsst": "IPSST", "incluir_salud": "Incluir Salud",
    "salud_publica": "Salud pública", "obra_social": "Obra social",
}

DISCAPACIDAD = {
    "motora": "Motora", "visual": "Visual", "auditiva": "Auditiva", "intelectual": "Intelectual",
    "psicosocial": "Psicosocial", "sin_discapacidad": "Sin discapacidad",
}

TIPO_VIVIENDA = {
    "propia": "Propia", "alquilada": "Alquilada", "prestada": "Prestada",
    "tenencia_precaria": "Tenencia precaria", "situacion_calle": "Situación de calle",
    "institucional": "Institucional",
}

ESTADO_CIVIL = {
    "soltero": "Soltero/a", "casado": "Casado/a", "viudo": "Viudo/a", "separado": "Separado/a",
    "divorciado": "Divorciado/a", "union_convivencial": "Unión convivencial",
}

ESTADO_FUNCIONAL = {
    "independiente": "Independiente", "semidependiente": "Semidependiente", "dependiente": "Dependiente",
}

# Departamentos de la provincia de Tucumán (sugerencias; el campo admite texto libre).
DEPARTAMENTOS = [
    "Burruyacú", "Capital", "Chicligasta", "Cruz Alta", "Famaillá", "Graneros",
    "Juan Bautista Alberdi", "La Cocha", "Leales", "Lules", "Monteros", "Río Chico",
    "Simoca", "Tafí del Valle", "Tafí Viejo", "Trancas", "Yerba Buena",
]


def _codigos_jerarquicos(catalogo: dict) -> set[str]:
    codigos = set()
    for grupo, (_, subs) in catalogo.items():
        codigos.add(grupo)
        codigos.update(f"{grupo}.{s}" for s in subs)
    return codigos


def validar_lista_jerarquica(valores: list[str] | None, catalogo: dict, campo: str) -> list[str]:
    """Valida códigos y agrega el grupo cuando se marcó una subopción."""
    if not valores:
        return []
    validos = _codigos_jerarquicos(catalogo)
    resultado: list[str] = []
    for v in valores:
        if v not in validos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Opción inválida en {campo}: {v}")
        grupo = v.split(".")[0]
        for c in (grupo, v):
            if c not in resultado:
                resultado.append(c)
    return resultado


def validar_lista(valores: list[str] | None, catalogo: dict, campo: str) -> list[str]:
    if not valores:
        return []
    for v in valores:
        if v not in catalogo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Opción inválida en {campo}: {v}")
    return list(dict.fromkeys(valores))


def validar_opcion(valor: str | None, catalogo: dict, campo: str) -> str | None:
    if valor is None:
        return None
    if valor not in catalogo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Opción inválida en {campo}: {valor}")
    return valor


def _jerarquico_out(catalogo: dict) -> list[dict]:
    return [
        {"codigo": g, "texto": t, "subopciones": [{"codigo": f"{g}.{s}", "texto": st} for s, st in subs.items()]}
        for g, (t, subs) in catalogo.items()
    ]


def _plano_out(catalogo: dict) -> list[dict]:
    return [{"codigo": c, "texto": t} for c, t in catalogo.items()]


def catalogo_formularios() -> dict:
    return {
        "generos": _plano_out(GENEROS),
        "cud": _plano_out(CUD),
        "indicadores": _jerarquico_out(INDICADORES),
        "intervenciones": _jerarquico_out(INTERVENCIONES),
        "tipos_ingreso": _jerarquico_out(TIPOS_INGRESO),
        "derivado_por": _plano_out(DERIVADO_POR),
        "cobertura_previsional": _plano_out(COBERTURA_PREVISIONAL),
        "cobertura_salud": _plano_out(COBERTURA_SALUD),
        "discapacidad": _plano_out(DISCAPACIDAD),
        "tipo_vivienda": _plano_out(TIPO_VIVIENDA),
        "estado_civil": _plano_out(ESTADO_CIVIL),
        "estado_funcional": _plano_out(ESTADO_FUNCIONAL),
        "departamentos": DEPARTAMENTOS,
    }


# ---------------------------------------------------------------------------
# Validación de bloques de datos
# ---------------------------------------------------------------------------


def validar_datos_persona(d: dict) -> dict:
    """Valida in situ los campos codificados de la persona presentes en `d`."""
    if "genero" in d:
        validar_opcion(d["genero"], GENEROS, "género")
    if "cud" in d:
        validar_opcion(d["cud"], CUD, "CUD")
    if "cobertura_salud" in d:
        d["cobertura_salud"] = validar_lista(d["cobertura_salud"], COBERTURA_SALUD, "cobertura de salud")
    if "cobertura_previsional" in d:
        d["cobertura_previsional"] = validar_lista(
            d["cobertura_previsional"], COBERTURA_PREVISIONAL, "cobertura previsional"
        )
    if "discapacidades" in d:
        d["discapacidades"] = validar_lista(d["discapacidades"], DISCAPACIDAD, "discapacidad")
    return d


def validar_ingreso(d: dict) -> dict:
    """Tipo de ingreso, subtipo y derivación (carátula y registro de demanda)."""
    tipo = d.get("tipo_ingreso")
    if tipo is not None and tipo not in TIPOS_INGRESO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Tipo de ingreso inválido: {tipo}")
    detalle = d.get("tipo_ingreso_detalle")
    if detalle is not None:
        if tipo is None or detalle not in TIPOS_INGRESO[tipo][1]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Detalle de ingreso inválido: {detalle}")
    if "derivado_por" in d:
        validar_opcion(d["derivado_por"], DERIVADO_POR, "derivado por")
    return d


def validar_motivo_consulta(d: dict) -> dict:
    if "indicadores" in d:
        d["indicadores"] = validar_lista_jerarquica(d["indicadores"], INDICADORES, "indicadores")
    if "intervenciones" in d:
        d["intervenciones"] = validar_lista_jerarquica(d["intervenciones"], INTERVENCIONES, "intervenciones")
    return d


def validar_demanda(d: dict) -> dict:
    validar_datos_persona(d)
    validar_ingreso(d)
    validar_motivo_consulta(d)
    for campo, cat, nombre in (
        ("tipo_vivienda", TIPO_VIVIENDA, "tipo de vivienda"),
        ("estado_civil", ESTADO_CIVIL, "estado civil"),
        ("estado_funcional", ESTADO_FUNCIONAL, "estado funcional"),
    ):
        if campo in d:
            validar_opcion(d[campo], cat, nombre)
    return d

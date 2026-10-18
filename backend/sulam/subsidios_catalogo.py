"""Catálogo de subsidios y papeles que se piden.

Fuente: «Requisitos para subsidio destinado a la cobertura de cuidados / a residencia de larga estadía»
(propuesta al Ministro de Desarrollo Social, 1/6/2026) y circular a los referentes de Residencias de Larga
Estadía (15/5/2026) con la documentación mensual para el pago de las estadías.

Cada subsidio copia estos textos al crearse, de modo que un cambio posterior en los requisitos no altera
los trámites ya iniciados; en cada uno se pueden agregar papeles propios.
"""

from __future__ import annotations

TIPOS = [
    {"codigo": "residencia", "texto": "Residencia de larga estadía"},
    {"codigo": "cuidados", "texto": "Cuidador/a domiciliario/a"},
    {"codigo": "alimentario", "texto": "Alimentario"},
    {"codigo": "materiales", "texto": "Materiales"},
    {"codigo": "otro", "texto": "Otro"},
]
CODIGOS_TIPO = {t["codigo"] for t in TIPOS}
# Los que se pagan todos los meses y tienen documentación mensual.
MENSUALES = {"residencia", "cuidados"}

ESTADOS = [
    {"codigo": "en_tramite", "texto": "En trámite (reuniendo papeles)"},
    {"codigo": "elevado", "texto": "Elevado al Ministerio"},
    {"codigo": "aprobado", "texto": "Aprobado"},
    {"codigo": "rechazado", "texto": "Rechazado"},
    {"codigo": "suspendido", "texto": "Suspendido"},
    {"codigo": "finalizado", "texto": "Finalizado"},
]
CODIGOS_ESTADO = {e["codigo"] for e in ESTADOS}
# Estados que solo decide quien tiene «administrar».
ESTADOS_RESERVADOS = {"aprobado", "rechazado", "suspendido", "finalizado"}

ESTADOS_PAGO = [
    {"codigo": "pendiente", "texto": "Pendiente de documentación"},
    {"codigo": "documentacion_completa", "texto": "Documentación completa"},
    {"codigo": "en_liquidacion", "texto": "En liquidación"},
    {"codigo": "pagado", "texto": "Pagado"},
    {"codigo": "observado", "texto": "Observado"},
]
CODIGOS_ESTADO_PAGO = {e["codigo"] for e in ESTADOS_PAGO}
PAGO_RESERVADO = {"en_liquidacion", "pagado"}

ESTADOS_REQUISITO = [
    {"codigo": "pendiente", "texto": "Falta"},
    {"codigo": "presentado", "texto": "Presentado"},
    {"codigo": "no_corresponde", "texto": "No corresponde"},
]
CODIGOS_ESTADO_REQUISITO = {e["codigo"] for e in ESTADOS_REQUISITO}

GRUPOS = {
    "solicitante": "Solicitante",
    "beneficiario": "Beneficiario/a",
    "cuidador": "Cuidador/a",
    "residente": "Residente",
    "institucion": "Institución",
    "otros": "Otros papeles",
}

_SOLICITANTE = [
    ("nota_solicitud", "Nota de solicitud al Ministro de Desarrollo Social, fundada, con el objeto del pedido, datos completos del solicitante y del beneficiario (nombre y apellido, DNI, domicilio real, teléfono y correo) y firma y aclaración"),
    ("dni_solicitante", "Fotocopia del DNI del solicitante"),
    ("vinculo", "Acreditación del vínculo entre solicitante y beneficiario (acta de nacimiento, matrimonio u otro instrumento idóneo)"),
]


def _beneficiario(historia: str, con_comprobantes: bool):
    r = [
        ("dni_beneficiario", "Fotocopia del DNI del beneficiario"),
        ("supervivencia", "Certificado de supervivencia"),
        ("cud", "CUD vigente o constancia de «Mi Argentina»"),
        ("historia_clinica", historia),
        ("recibo_haberes", "Recibo de haberes (jubilación y pensión)"),
    ]
    if con_comprobantes:
        r.append(("comprobantes_gastos", "Comprobantes de gastos destinados al cuidado de la persona mayor"))
    r += [
        ("cobertura", "Credencial o declaración jurada de obra social u otra cobertura"),
        ("negativa_cobertura", "Negativa de cobertura emitida por la obra social o, si no tiene obra social, negativa de ANSES"),
        ("familiares_obligados", "Declaración de familiares obligados"),
        ("recibos_obligados", "Recibos de haberes de los obligados (cónyuge e hijos, convivan o no)"),
        ("cbu_beneficiario", "Constancia de CBU a nombre del beneficiario emitida por entidad financiera (no se admiten billeteras virtuales)"),
    ]
    return r


_HISTORIA_CUIDADOS = "Informe o resumen de historia clínica actualizado, firmado por médico especialista, que justifique el nivel de dependencia y la necesidad de cuidador, y determine las horas diarias o semanales"
_HISTORIA_RESIDENCIA = "Informe o resumen de historia clínica actualizado, firmado por médico especialista, que justifique el nivel de dependencia y la necesidad de internación geriátrica"

# (grupo, [(código, texto)])
TRAMITE: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {
    "residencia": [("solicitante", _SOLICITANTE), ("beneficiario", _beneficiario(_HISTORIA_RESIDENCIA, False))],
    "cuidados": [
        ("solicitante", _SOLICITANTE),
        ("beneficiario", _beneficiario(_HISTORIA_CUIDADOS, True)),
        ("cuidador", [("dni_cuidador", "Fotocopia del DNI del cuidador"), ("plan_trabajo", "Plan de trabajo del asistente personal: tareas, carga horaria y modalidad, de acuerdo con la indicación médica")]),
    ],
    "alimentario": [],
    "materiales": [],
    "otro": [],
}

# Documentación mensual para pagar la estadía (circular a los referentes de residencias, 15/5/2026).
# La del residente se pide por cada subsidio; la de la institución se carga UNA vez por residencia y por mes
# y vale para todos sus residentes (ver ``MENSUAL_INSTITUCION``).
MENSUAL: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {
    "residencia": [
        (
            "residente",
            [
                ("m_dni", "Copia de DNI del residente"),
                ("m_cud", "CUD, si correspondiese"),
                ("m_ingresos", "Boleta de sueldo reciente o negativa de ANSES"),
                ("m_obra_social", "Constancia de afiliación a obra social o su negativa"),
                ("m_autorizacion", "Resolución ministerial, sentencia judicial o nota de autorización de la Directora que avale el ingreso"),
                ("m_supervivencia", "Certificado de supervivencia"),
                ("m_historia", "Historia clínica actualizada"),
                ("m_egreso", "Acta de egreso o acta de defunción (en caso de corresponder)"),
            ],
        ),
    ],
    "cuidados": [("beneficiario", [("m_comprobantes", "Comprobantes de gastos de cuidado del mes")])],
}

MENSUAL_INSTITUCION: list[tuple[str, str]] = [
    ("m_nota_reintegro", "Nota de pedido de reintegro con el monto y los datos completos de los residentes"),
    ("m_habilitacion", "Habilitación del SIPROSA"),
    ("m_categorizacion", "Categorización de la residencia"),
    ("m_fiscal", "Cumplimiento fiscal"),
    ("m_inscripcion", "Constancia de inscripción"),
    ("m_cbu", "Constancia de CBU de la institución"),
    ("m_factura", "Factura correspondiente al período a cobrar"),
    ("m_cae", "CAE (código de autorización electrónico)"),
]


def requisitos_de(tipo: str, mensual: bool = False) -> list[tuple[str, str, str]]:
    """[(grupo, código, texto)] en el orden de presentación."""
    origen = MENSUAL if mensual else TRAMITE
    return [(g, c, t) for g, items in origen.get(tipo, []) for c, t in items]

"""Certificación negativa de ANSES.

SULAM no consulta ANSES por su cuenta (el servicio es para que cada persona o
técnico lo use desde su navegador, y no se envían datos de los legajos a sitios
externos desde el servidor). Lo que sí automatiza:

- el CUIL probable a partir del DNI y el género (para copiarlo y pegarlo en ANSES);
- la lectura del PDF descargado: CUIL, fecha de emisión, código de validación y
  si registra o no prestaciones, aportes u obra social. La lectura es una
  propuesta: quien carga la revisa antes de guardar;
- el vencimiento (30 días por defecto) y los avisos.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime

PREFIJOS_PERSONA = ("20", "23", "24", "27")
_PESOS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

RESULTADOS = {
    "sin_registros": "Sin registros (negativa)",
    "con_registros": "Registra prestaciones, aportes u obra social",
    "no_emitida": "ANSES no emitió la negativa (registra alguna situación)",
}


def _digito(base10: str) -> int:
    resto = sum(int(d) * p for d, p in zip(base10, _PESOS)) % 11
    return 0 if resto == 0 else 11 - resto  # 10 = no válido con ese prefijo


def cuil_valido(cuil: str) -> bool:
    c = re.sub(r"\D", "", cuil or "")
    return len(c) == 11 and c[:2] in ("20", "23", "24", "27", "30", "33", "34") and _digito(c[:10]) == int(c[10])


def formatear(cuil: str) -> str:
    c = re.sub(r"\D", "", cuil or "")
    return f"{c[:2]}-{c[2:10]}-{c[10]}" if len(c) == 11 else cuil


def cuil_sugeridos(dni: str | None, genero: str | None) -> list[str]:
    """CUIL probables según la regla de ANSES. Con género desconocido, ambos."""
    d = re.sub(r"\D", "", dni or "")
    if not d or len(d) > 8:
        return []
    d = d.zfill(8)
    prefijos = {"M": ["20"], "F": ["27"]}.get(genero or "", ["27", "20"])
    salida = []
    for p in prefijos:
        dig = _digito(p + d)
        if dig == 10:
            # La regla de ANSES pasa a prefijo 23 (9 para varones, 4 para mujeres).
            salida.append(f"23{d}{9 if p == '20' else 4}")
        else:
            salida.append(f"{p}{d}{dig}")
    return [formatear(c) for c in salida]


# ---------------------------------------------------------------- lectura del PDF


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[ \t]+", " ", t).lower()


_FECHA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_CUIL = re.compile(r"\b(20|23|24|27)[- ]?(\d{8})[- ]?(\d)\b")
_CODIGO = re.compile(
    r"c[oó]digo\s+(?:de\s+)?(?:validaci[oó]n|verificaci[oó]n|seguridad)\s*(?:n[°ºo.]*\s*)?[:#]?\s*([A-Za-z0-9][A-Za-z0-9-]{5,60})",
    re.I,
)
# Frases habituales de una negativa «limpia» y de una que registra algo. ANSES
# cambia sus textos: por eso el resultado se ofrece como propuesta a revisar.
_NEGATIVAS = (
    "no registra", "no se registra", "no posee", "no percibe", "no se encontraron", "no surgen",
    "sin registro", "no registran", "no cuenta con",
)
_POSITIVAS = (
    "registra la siguiente", "registra las siguientes", "percibe", "beneficio n", "prestacion vigente",
    "posee beneficio", "se registran", "registra aportes", "registra prestacion", "registra obra social",
    "alta en", "titular de",
)


def texto_de_pdf(contenido: bytes, max_paginas: int = 6) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(io.BytesIO(contenido))
    try:
        partes = []
        for i in range(min(len(pdf), max_paginas)):
            pagina = pdf[i]
            partes.append(pagina.get_textpage().get_text_range())
        return "\n".join(partes)
    finally:
        pdf.close()


def leer_negativa(texto: str, hoy: date | None = None) -> dict:
    """Propuesta de datos a partir del texto del PDF descargado de ANSES."""
    hoy = hoy or date.today()
    plano = _plano(texto)
    cuiles = list(dict.fromkeys(f"{a}-{b}-{c}" for a, b, c in _CUIL.findall(texto)))
    fechas: list[date] = []
    for d, m, a in _FECHA.findall(texto):
        try:
            f = date(int(a), int(m), int(d))
        except ValueError:
            continue
        if f <= hoy and f.year >= hoy.year - 2:
            fechas.append(f)
    # La emisión suele estar junto a «emisión»/«emitido»/«fecha»; si no, la más reciente.
    emision = None
    m = re.search(r"(emisi[oó]n|emitid[oa]|generad[oa]|fecha)[^\n]{0,40}?(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", texto, re.I)
    if m:
        d, mm, a = re.split(r"[/.-]", m.group(2))
        try:
            emision = date(int(a), int(mm), int(d))
        except ValueError:
            emision = None
    if emision is None and fechas:
        emision = max(fechas)
    codigo = None
    mc = _CODIGO.search(texto)
    if mc:
        codigo = mc.group(1)

    negativas = sum(plano.count(f) for f in _NEGATIVAS)
    positivas = 0
    lineas_positivas = []
    for linea in plano.splitlines():
        if any(f in linea for f in _POSITIVAS) and not any(f in linea for f in _NEGATIVAS):
            positivas += 1
            lineas_positivas.append(linea.strip())
    if positivas and not negativas:
        resultado, seguridad = "con_registros", "media"
    elif negativas and not positivas:
        resultado, seguridad = "sin_registros", "media"
    elif negativas or positivas:
        resultado, seguridad = ("con_registros" if positivas else "sin_registros"), "baja"
    else:
        resultado, seguridad = None, "nula"

    es_anses = "anses" in plano or "administracion nacional de la seguridad social" in plano
    es_negativa = "negativa" in plano
    avisos = []
    if not texto.strip():
        avisos.append("El PDF no tiene texto (¿es una foto o un escaneo?). Complete los datos a mano.")
    elif not (es_anses and es_negativa):
        avisos.append("No parece una certificación negativa de ANSES. Revise el archivo.")
    if seguridad in ("baja", "nula"):
        avisos.append("No se pudo determinar con seguridad el resultado: léalo en el PDF y elíjalo.")
    return {
        "cuiles": cuiles,
        "fecha_emision": emision.isoformat() if emision else None,
        "codigo_validacion": codigo,
        "resultado": resultado,
        "seguridad": seguridad,
        "detalle": "\n".join(lineas_positivas[:8]) or None,
        "es_negativa_anses": es_anses and es_negativa,
        "avisos": avisos,
    }


def estado(vence: date | None, hoy: date | None = None) -> str:
    if vence is None:
        return "sin_negativa"
    hoy = hoy or date.today()
    if vence < hoy:
        return "vencida"
    if (vence - hoy).days <= 5:
        return "por_vencer"
    return "vigente"


def hoy_local() -> date:
    return datetime.now().astimezone().date()

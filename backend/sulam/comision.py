"""Órdenes de salida en comisión (Word), completadas sobre el formulario oficial de la Dirección.

La plantilla (``papel/comision_de_servicio.docx``) es una hoja oficio con tres órdenes iguales: aquí cada una se
completa para una persona distinta. Lo que no se sabe queda con los puntos originales, para escribirlo a mano.
Las firmas (empleado, jefe de departamento, director) siempre se firman en papel.
"""

from __future__ import annotations

import copy
import io
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Twips
from docx.oxml import OxmlElement

PLANTILLA = Path(__file__).parent / "papel" / "comision_de_servicio.docx"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ARGENTINA = timezone(timedelta(hours=-3))  # sin horario de verano
PUNTOS = "…………………………"
POR_HOJA = 3


def hora_local(d: datetime) -> datetime:
    return d.astimezone(ARGENTINA)


def _dia(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _escribir(p, partes: list[tuple[str, bool]]) -> None:
    """Reemplaza el texto de un párrafo conservando la letra del original; lo cargado va subrayado."""
    runs = p.runs
    rpr = copy.deepcopy(runs[0]._r.rPr) if runs and runs[0]._r.rPr is not None else None
    for r in runs:
        r._r.getparent().remove(r._r)
    for texto, subrayado in partes:
        r = p.add_run(texto)
        if rpr is not None:
            for hijo in list(r._r.findall(qn("w:rPr"))):
                r._r.remove(hijo)
            r._r.insert(0, copy.deepcopy(rpr))
        r.underline = bool(subrayado)


def _dato(valor: str | None, relleno: str = PUNTOS) -> tuple[str, bool]:
    return (valor, True) if valor else (relleno, False)


def _completar(p_fecha, p_senor, p_traslado, p_destino, p_objeto, p_regreso, o: dict) -> None:
    emision: date = o["emision"]
    _escribir(p_fecha, [(f"San Miguel de Tucumán, {_dia(emision)} ", False)])
    _escribir(p_senor, [("SEÑOR/A ", False), _dato(o.get("nombre")), ("   TARJETA Nº: ", False), _dato(o.get("tarjeta"), "…………")])
    dia: date | None = o.get("dia")
    _escribir(p_traslado, [
        ("Sírvase trasladarse el día ", False), _dato(_dia(dia) if dia else None), (" a Hs. ", False),
        _dato(o.get("hora"), "…………"),
    ])
    _escribir(p_destino, [
        ("Con Destino a ", False), _dato(o.get("destino")), ("   Departamento ", False), _dato(o.get("departamento"), "…………………"),
    ])
    _escribir(p_objeto, [("Con el Objeto de ", False), _dato(o.get("objeto"))])
    _escribir(p_regreso, [("Debiendo regresar de esta comisión ", False), _dato(o.get("regreso"))])


def ordenes_docx(ordenes: list[dict]) -> bytes:
    """Una orden por persona, tres por hoja. Cada orden: nombre, tarjeta, emision, dia, hora, destino, departamento,
    objeto y regreso (los que falten quedan con puntos)."""
    doc = Document(str(PLANTILLA))
    # Márgenes algo menores que los del original: sin la letra del formulario (Myriad Pro) en la computadora, las
    # tres órdenes se salían de la hoja.
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Twips(850)
    cuerpo = doc.element.body
    sect = cuerpo.find(qn("w:sectPr"))
    base = [copy.deepcopy(h) for h in cuerpo if h is not sect]
    hojas = max(1, -(-len(ordenes) // POR_HOJA))
    for n in range(1, hojas):
        for h in base:
            nuevo = copy.deepcopy(h)
            if h is base[0] and nuevo.tag == qn("w:p"):
                ppr = nuevo.find(qn("w:pPr"))
                if ppr is None:
                    ppr = OxmlElement("w:pPr")
                    nuevo.insert(0, ppr)
                ppr.insert(0, OxmlElement("w:pageBreakBefore"))
            sect.addprevious(nuevo)
    parrafos = doc.paragraphs
    inicios = [i for i, p in enumerate(parrafos) if p.text.strip() == "MINISTERIO DE DESARROLLO SOCIAL"]
    for o, i in zip(ordenes, inicios):
        _completar(*(parrafos[i + k] for k in (4, 6, 7, 8, 9, 10)), o)
    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()

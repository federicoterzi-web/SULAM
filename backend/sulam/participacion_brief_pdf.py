"""Brief en PDF de un evento o de una campaña (mismo contenido que el Word), para enviar o imprimir."""

from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .participacion_brief import AREA, _cuando, _imagen_jpeg, _organiza

AZUL = colors.HexColor("#1F4E79")
GRIS = colors.HexColor("#595959")
_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=10.5, leading=14)
_TIT = ParagraphStyle("tit", parent=_BASE, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=AZUL, spaceAfter=4)
_SEC = ParagraphStyle("sec", parent=_BASE, fontName="Helvetica-Bold", fontSize=12, textColor=AZUL, spaceBefore=12, spaceAfter=4)
_PEQ = ParagraphStyle("peq", parent=_BASE, fontSize=8.5, leading=11, textColor=GRIS)
_NEG = ParagraphStyle("neg", parent=_BASE, fontName="Helvetica-Bold", spaceBefore=8)


def _p(texto: str, estilo=_BASE) -> Paragraph:
    return Paragraph(escape(texto).replace("\n", "<br/>"), estilo)


def _datos(filas: list[tuple[str, str | None]]) -> Table:
    t = Table([[_p(a, _NEG), _p(b or "—")] for a, b in filas], colWidths=[4 * cm, 12.6 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF3F8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _fotos(fotos: list[tuple[str, bytes]], ancho_cm: float) -> list:
    celdas = []
    for nombre, datos in fotos:
        try:
            img = _imagen_jpeg(datos, 1000)
            from PIL import Image

            w, h = Image.open(io.BytesIO(img.getvalue())).size
            ancho = ancho_cm * cm
            celdas.append(RLImage(io.BytesIO(img.getvalue()), width=ancho, height=ancho * h / w))
        except Exception:  # una imagen dañada no impide armar el brief
            celdas.append(_p(f"(no se pudo incluir la imagen {nombre})", _PEQ))
    if not celdas:
        return []
    t = Table([celdas])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [Spacer(1, 4), t]


def _armar(cuerpo: list, quien: str) -> bytes:
    cuerpo = [_p(AREA, _PEQ), *cuerpo, Spacer(1, 14), _p(f"Brief generado desde SULAM el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {quien}.", _PEQ)]
    salida = io.BytesIO()
    SimpleDocTemplate(salida, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm, title="Brief", author="SULAM").build(cuerpo)
    return salida.getvalue()


def brief_de_evento(e, x, fotos: list[tuple[str, bytes]], quien: str, flyer: tuple[str, bytes] | None = None) -> bytes:
    c = [_p(e.titulo, _TIT), _p(f"{x.tipo.nombre} · {_cuando(e)}")]
    c.append(Spacer(1, 8))
    c.append(_datos([
        ("Tipo de evento", x.tipo.nombre),
        ("Fecha y hora", _cuando(e)),
        ("Lugar", e.lugar),
        ("Organiza", _organiza(x)),
        ("Campaña", x.campania.nombre if x.campania else None),
        ("Instituciones", ", ".join(x.todas_las_instituciones) or None),
        ("Asistentes", str(x.asistentes) if x.asistentes is not None else None),
    ]))
    if flyer:
        c += [_p("Flyer", _SEC), *_fotos([flyer], 7)]
    if x.resumen:
        c += [_p("Resumen", _SEC), _p(x.resumen)]
    if e.resultado:
        c += [_p("Cómo se desarrolló", _SEC), _p(e.resultado)]
    if fotos:
        c += [_p("Fotos", _SEC), *_fotos(fotos, 7.8 if len(fotos) > 1 else 12)]
    return _armar(c, quien)


def brief_de_campania(camp, filas: list[tuple], quien: str) -> bytes:
    periodo = " al ".join(d.strftime("%d/%m/%Y") for d in (camp.desde, camp.hasta) if d) if (camp.desde or camp.hasta) else None
    realizados = [(e, x, f) for e, x, f in filas if e.estado == "realizado"]
    proximos = [(e, x, f) for e, x, f in filas if e.estado == "programado"]
    c = [_p(f"Campaña: {camp.nombre}", _TIT)]
    if periodo:
        c.append(_p(periodo))
    c += [Spacer(1, 8), _datos([
        ("Estado", "Activa" if camp.estado == "activa" else "Cerrada"),
        ("Eventos realizados", str(len(realizados))),
        ("Eventos por realizar", str(len(proximos))),
        ("Asistentes en total", str(sum(x.asistentes or 0 for _, x, _ in realizados))),
    ])]
    if camp.descripcion:
        c += [_p("Descripción", _SEC), _p(camp.descripcion)]
    if realizados:
        c.append(_p("Eventos realizados", _SEC))
        for e, x, fotos in realizados:
            c += [_p(e.titulo, _NEG), _p(f"{x.tipo.nombre} · {_cuando(e)}" + (f" · {e.lugar}" if e.lugar else ""))]
            det = [f"Organiza: {_organiza(x)}"]
            if x.todas_las_instituciones:
                det.append("Instituciones: " + ", ".join(x.todas_las_instituciones))
            if x.asistentes is not None:
                det.append(f"Asistentes: {x.asistentes}")
            c.append(_p(" · ".join(det)))
            if x.resumen:
                c.append(_p(x.resumen))
            c += _fotos(fotos, 6.5)
    if proximos:
        c.append(_p("Próximos eventos", _SEC))
        for e, x, _ in proximos:
            c.append(_p("• " + f"{e.titulo} — {_cuando(e)}" + (f" · {e.lugar}" if e.lugar else "") + f" · Organiza: {_organiza(x)}"))
    return _armar(c, quien)

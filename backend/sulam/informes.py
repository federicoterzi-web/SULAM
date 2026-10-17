"""Informes redactados en SULAM.

- Datos de la persona que se completan solos (y se pueden quitar, agregar o corregir).
- Plantillas iniciales: estructura propuesta a partir del modelo de informe de la
  Dirección; Dirección y jefaturas las ajustan desde SULAM.
- Limpieza del texto con formato que llega del editor (solo párrafos, listas,
  negrita, cursiva y subrayado).
- PDF con membrete, en Liberation Sans (mismas medidas que Arial).
"""

from __future__ import annotations

import html
import io
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .formularios import (
    COBERTURA_PREVISIONAL,
    COBERTURA_SALUD,
    DISCAPACIDAD,
    ESTADO_CIVIL,
    ESTADO_FUNCIONAL,
    INDICADORES,
    TIPO_VIVIENDA,
)
from .models import Caso, Persona, RegistroDemanda

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
]


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _fecha(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _edad(nac: date | None, al: date) -> str:
    if not nac:
        return ""
    anios = al.year - nac.year - ((al.month, al.day) < (nac.month, nac.day))
    return f"{anios} años"


def _miles(numero: str | None) -> str:
    if not numero:
        return ""
    return f"{int(numero):,}".replace(",", ".") if numero.isdigit() else numero


def _lista(codigos: list | None, catalogo: dict) -> str:
    textos = []
    for c in codigos or []:
        if "." in c:
            continue
        v = catalogo.get(c)
        if v is None:
            continue
        textos.append(v[0] if isinstance(v, tuple) else v)
    return ", ".join(textos)


def _indicadores(codigos: list | None) -> str:
    partes = []
    for c in codigos or []:
        if "." in c:
            continue
        nombre, subs = INDICADORES.get(c, (None, {}))
        if not nombre:
            continue
        elegidas = [subs[s.split(".", 1)[1]] for s in codigos if s.startswith(c + ".") and s.split(".", 1)[1] in subs]
        partes.append(nombre + (f" ({', '.join(elegidas).lower()})" if elegidas else ""))
    return "; ".join(partes)


# ---------------------------------------------------------------- datos de la persona

# Orden en que se ofrecen. La etiqueta es la que figura en el informe (editable).
CAMPOS: dict[str, str] = {
    "nombre": "Nombre y apellido",
    "fecha_nacimiento": "Fecha de nacimiento",
    "edad": "Edad",
    "documento": "DNI",
    "legajo": "N° de legajo",
    "actuacion": "Actuación",
    "obra_social": "Obra social",
    "cobertura_previsional": "Cobertura previsional",
    "estado_civil": "Estado civil",
    "domicilio": "Domicilio",
    "departamento": "Departamento",
    "telefono": "Teléfono",
    "cud": "Certificado Único de Discapacidad (CUD)",
    "discapacidad": "Discapacidad",
    "convive_con": "Convive con",
    "referente": "Referente familiar o afectivo",
    "vivienda": "Tipo de vivienda",
    "estado_funcional": "Estado funcional",
    "fecha_ingreso": "Fecha de ingreso",
    "indicadores": "Indicadores",
    "area": "Área interviniente",
}


def ultima_demanda(db: Session, persona: Persona, caso: Caso | None) -> RegistroDemanda | None:
    q = select(RegistroDemanda).where(RegistroDemanda.persona_id == persona.id)
    if caso is not None:
        # Primero la del caso; si no tiene, la última de la persona.
        r = db.execute(
            q.where(RegistroDemanda.caso_id == caso.id).order_by(RegistroDemanda.fecha.desc(), RegistroDemanda.creado_en.desc())
        ).scalars().first()
        if r is not None:
            return r
    return db.execute(q.order_by(RegistroDemanda.fecha.desc(), RegistroDemanda.creado_en.desc())).scalars().first()


def valores_disponibles(db: Session, persona: Persona, caso: Caso | None, al: date) -> dict[str, str]:
    """Valor actual de cada dato según el legajo, el caso y el último registro de demanda."""
    d = ultima_demanda(db, persona, caso)
    salud = _lista(persona.cobertura_salud, COBERTURA_SALUD)
    if persona.obra_social:
        salud = ", ".join(x for x in [salud.replace("Obra social", "").strip(", "), persona.obra_social] if x)
    referente = ""
    if d and d.referente_nombre:
        referente = d.referente_nombre + (f" ({d.referente_vinculo})" if d.referente_vinculo else "")
        if d.referente_telefono:
            referente += f", tel. {d.referente_telefono}"
    domicilio = ", ".join(x for x in [persona.domicilio, persona.barrio, persona.localidad] if x)
    cud = {"si": "Posee", "no": "No posee", "en_tramite": "En trámite"}.get(persona.cud or "", "")
    v = {
        "nombre": f"{persona.nombres} {persona.apellidos}".strip(),
        "fecha_nacimiento": _fecha(persona.fecha_nacimiento) + (" (aprox.)" if persona.fecha_nacimiento and persona.fecha_nacimiento_aproximada else ""),
        "edad": _edad(persona.fecha_nacimiento, al),
        "documento": "" if persona.sin_documento else _miles(persona.numero_documento),
        "legajo": persona.numero_legajo or "",
        "actuacion": f"{caso.numero_actuacion}/{caso.anio_actuacion}" if caso and caso.numero_actuacion else (caso.numero if caso else ""),
        "obra_social": salud,
        "cobertura_previsional": _lista(persona.cobertura_previsional, COBERTURA_PREVISIONAL),
        "estado_civil": ESTADO_CIVIL.get(d.estado_civil, "") if d and d.estado_civil else "",
        "domicilio": domicilio,
        "departamento": persona.departamento or "",
        "telefono": persona.telefono or "",
        "cud": cud,
        "discapacidad": _lista(persona.discapacidades, DISCAPACIDAD),
        "convive_con": (d.convive_con or "") if d else "",
        "referente": referente,
        "vivienda": TIPO_VIVIENDA.get(d.tipo_vivienda, "") if d and d.tipo_vivienda else "",
        "estado_funcional": ESTADO_FUNCIONAL.get(d.estado_funcional, "") if d and d.estado_funcional else "",
        "fecha_ingreso": _fecha(caso.fecha_ingreso) if caso else "",
        "indicadores": _indicadores(caso.indicadores) if caso else "",
        "area": caso.area.nombre if caso and caso.area else "",
    }
    if persona.tipo_documento and persona.tipo_documento.upper() != "DNI" and v["documento"]:
        v["documento"] = f"{persona.tipo_documento} {v['documento']}"
    return v


def datos_iniciales(claves: list[str], valores: dict[str, str]) -> list[dict]:
    return [{"clave": c, "etiqueta": CAMPOS[c], "valor": valores.get(c, "")} for c in claves if c in CAMPOS]


# ---------------------------------------------------------------- plantillas iniciales

_DATOS_BASE = ["nombre", "fecha_nacimiento", "edad", "documento", "obra_social", "estado_civil", "domicilio", "cud"]

PLANTILLAS_INICIALES = [
    {
        "nombre": "Informe socioambiental",
        "tipo_documental": "Informe socioambiental",
        "descripcion": "Situación social, habitacional y de salud de la persona mayor, con la opinión profesional del equipo.",
        "estructura": {
            "titulo": "Informe socioambiental",
            "destinatario": False,
            "numerar": True,
            "datos": _DATOS_BASE,
            "secciones": [
                {"titulo": "Reseña", "guia": "Cómo llegó el caso, con quién se tomó contacto y qué información aportaron."},
                {"titulo": "Situación social y económica", "guia": "Red de apoyo familiar y comunitaria, con quién vive, ingresos y administración de recursos."},
                {"titulo": "Situación habitacional", "guia": "Vivienda, higiene, servicios básicos, accesibilidad y seguridad."},
                {"titulo": "Situación de salud", "guia": "Diagnósticos referidos, autonomía, medicación, cuidados que requiere y quién los brinda."},
                {"titulo": "Opinión profesional", "guia": "Valoración del equipo técnico, nivel de urgencia y recomendaciones o solicitudes concretas."},
            ],
        },
    },
    {
        "nombre": "Informe social / de situación",
        "tipo_documental": "Informe social",
        "descripcion": "Estado del caso para la Dirección, un juzgado u otro organismo.",
        "estructura": {
            "titulo": "Informe social",
            "destinatario": True,
            "numerar": True,
            "datos": _DATOS_BASE + ["legajo", "actuacion"],
            "secciones": [
                {"titulo": "Motivo del informe", "guia": "Qué se informa y a pedido de quién (oficio, expediente, Dirección)."},
                {"titulo": "Antecedentes", "guia": "Ingreso del caso, intervenciones anteriores y articulaciones."},
                {"titulo": "Situación actual", "guia": "Lo relevado en la última intervención: social, habitacional y de salud."},
                {"titulo": "Intervenciones realizadas", "guia": "Acciones del equipo y de otras instituciones, con fechas."},
                {"titulo": "Opinión profesional y sugerencias", "guia": "Valoración del equipo y pasos que se proponen."},
            ],
        },
    },
    {
        "nombre": "Informe de seguimiento",
        "tipo_documental": "Informe de seguimiento",
        "descripcion": "Evolución del caso en un período: qué se hizo, cómo está hoy y qué sigue.",
        "estructura": {
            "titulo": "Informe de seguimiento",
            "destinatario": False,
            "numerar": True,
            "datos": ["nombre", "edad", "documento", "legajo", "actuacion", "domicilio"],
            "secciones": [
                {"titulo": "Período informado", "guia": "Desde y hasta qué fecha, y motivo del seguimiento."},
                {"titulo": "Intervenciones del período", "guia": "Visitas, entrevistas, gestiones y articulaciones (puede insertar las evoluciones del caso)."},
                {"titulo": "Situación actual", "guia": "Cambios respecto del informe anterior."},
                {"titulo": "Próximos pasos", "guia": "Acciones previstas, responsables y plazos."},
            ],
        },
    },
    {
        "nombre": "Nota / oficio a otra institución",
        "tipo_documental": "Nota",
        "descripcion": "Pedido, derivación o respuesta a otro organismo, con membrete.",
        "estructura": {
            "titulo": "",
            "destinatario": True,
            "destinatario_inicial": "Sr./Sra. \nCargo\nInstitución\nS / D",
            "numerar": False,
            "datos": ["nombre", "documento", "domicilio"],
            "secciones": [
                {
                    "titulo": "",
                    "guia": "Cuerpo de la nota.",
                    "texto": "<p>Tengo el agrado de dirigirme a usted, en representación de la Dirección de Adultos Mayores, a fin de </p>",
                },
                {"titulo": "", "guia": "Saludo final.", "texto": "<p>Sin otro particular, saludo a usted atentamente.</p>"},
            ],
        },
    },
]


def crear_plantillas_iniciales(db: Session) -> None:
    """Idempotente: solo si todavía no hay ninguna plantilla."""
    from .models import PlantillaInforme, TipoDocumental

    if db.execute(select(PlantillaInforme.id)).first() is not None:
        return
    tipos = {t.nombre: t.id for t in db.execute(select(TipoDocumental)).scalars()}
    for i, p in enumerate(PLANTILLAS_INICIALES):
        estructura = dict(p["estructura"])
        estructura["secciones"] = [
            {"titulo": s["titulo"], "guia": s.get("guia", ""), "texto": s.get("texto", "")} for s in estructura["secciones"]
        ]
        db.add(
            PlantillaInforme(
                nombre=p["nombre"],
                descripcion=p["descripcion"],
                tipo_documental_id=tipos.get(p["tipo_documental"]),
                estructura=estructura,
                orden=i,
            )
        )


# ---------------------------------------------------------------- texto con formato

_INLINE = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u"}
_BLOQUE = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section", "article", "header", "footer"}
_IGNORAR = {"script", "style", "head", "title", "template", "iframe", "object", "noscript"}


class _Limpiador(HTMLParser):
    """Convierte HTML arbitrario (pegado de Word, del navegador) en bloques simples."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bloques: list[tuple[str, object]] = []  # ("p", markup) | ("ul"/"ol", [markup])
        self.actual = ""
        self.abiertos: list[str] = []
        self.lista: tuple[str, list[str]] | None = None
        self.profundidad_lista = 0
        self.ignorando = 0

    # -- utilidades
    def _cerrar_inline(self) -> str:
        return "".join(f"</{t}>" for t in reversed(self.abiertos))

    def _reabrir_inline(self) -> str:
        return "".join(f"<{t}>" for t in self.abiertos)

    def _cortar(self) -> None:
        texto = self.actual + self._cerrar_inline()
        self.actual = self._reabrir_inline()
        if not _vacio(texto):
            texto = _recortar_br(texto)
            if self.lista is not None:
                self.lista[1].append(texto)
            else:
                self.bloques.append(("p", texto))

    def _cerrar_lista(self) -> None:
        if self.lista is not None:
            if self.lista[1]:
                self.bloques.append(self.lista)
            self.lista = None

    # -- eventos
    def handle_starttag(self, tag, attrs):
        if tag in _IGNORAR:
            self.ignorando += 1
            return
        if self.ignorando:
            return
        if tag in _INLINE:
            t = _INLINE[tag]
            self.abiertos.append(t)
            self.actual += f"<{t}>"
        elif tag == "br":
            self.actual += "<br/>"
        elif tag in ("ul", "ol"):
            self._cortar()
            if self.profundidad_lista == 0:
                self._cerrar_lista()
                self.lista = (tag, [])
            self.profundidad_lista += 1
        elif tag == "li":
            self._cortar()
            if self.lista is None:
                self.lista = ("ul", [])
        elif tag in _BLOQUE:
            self._cortar()

    def handle_endtag(self, tag):
        if tag in _IGNORAR:
            self.ignorando = max(0, self.ignorando - 1)
            return
        if self.ignorando:
            return
        if tag in _INLINE:
            t = _INLINE[tag]
            if t in self.abiertos:
                # Cierra hasta t y reabre lo que quedó por dentro.
                i = len(self.abiertos) - 1 - self.abiertos[::-1].index(t)
                internos = self.abiertos[i + 1 :]
                self.actual += "".join(f"</{x}>" for x in reversed(self.abiertos[i:]))
                self.abiertos = self.abiertos[:i] + internos
                self.actual += "".join(f"<{x}>" for x in internos)
        elif tag in ("ul", "ol"):
            self._cortar()
            self.profundidad_lista = max(0, self.profundidad_lista - 1)
            if self.profundidad_lista == 0:
                self._cerrar_lista()
        elif tag == "li":
            self._cortar()
        elif tag in _BLOQUE:
            self._cortar()

    def handle_data(self, data):
        if self.ignorando:
            return
        texto = re.sub(r"[\r\n\t ]+", " ", data)
        if self.lista is not None and self.profundidad_lista == 0 and texto.strip():
            # Texto suelto después de una lista: empieza un párrafo nuevo.
            self._cerrar_lista()
        self.actual += html.escape(texto, quote=False)

    def terminar(self) -> list[tuple[str, object]]:
        self.close()
        self._cortar()
        self._cerrar_lista()
        return self.bloques


def _vacio(markup: str) -> bool:
    return re.sub(r"<[^>]+>|&nbsp;|\s| ", "", markup) == ""


def _recortar_br(markup: str) -> str:
    markup = re.sub(r"^(\s|<br/>)+", "", markup)
    markup = re.sub(r"(\s|<br/>)+$", "", markup)
    # Etiquetas vacías como <b></b>.
    for _ in range(3):
        markup = re.sub(r"<(b|i|u)>(\s*)</\1>", r"\2", markup)
    return markup.strip()


def bloques(html_entrada: str | None) -> list[tuple[str, object]]:
    p = _Limpiador()
    p.feed(html_entrada or "")
    return p.terminar()


def limpiar_html(html_entrada: str | None) -> str:
    """HTML seguro: solo <p>, <ul>/<ol>/<li>, <b>, <i>, <u> y <br/>."""
    partes = []
    for tipo, contenido in bloques(html_entrada):
        if tipo == "p":
            partes.append(f"<p>{contenido}</p>")
        else:
            items = "".join(f"<li>{x}</li>" for x in contenido)  # type: ignore[union-attr]
            partes.append(f"<{tipo}>{items}</{tipo}>")
    return "".join(partes)


def texto_plano(html_entrada: str | None) -> str:
    salida = []
    for tipo, contenido in bloques(html_entrada):
        if tipo == "p":
            salida.append(html.unescape(re.sub(r"<br/>", "\n", re.sub(r"<(?!br/)[^>]+>", "", contenido))))  # type: ignore[arg-type]
        else:
            for x in contenido:  # type: ignore[union-attr]
                salida.append("• " + html.unescape(re.sub(r"<[^>]+>", "", x)))
    return "\n".join(salida)


# ---------------------------------------------------------------- PDF

MEMBRETE = Path(__file__).parent / "recursos" / "membrete-2024.jpg"
_FUENTES = Path("/usr/share/fonts/truetype/liberation")
_fuente_registrada: str | None = None


def _fuente() -> tuple[str, str, str, str]:
    """Liberation Sans (medidas de Arial) si está instalada; si no, Helvetica."""
    global _fuente_registrada
    if _fuente_registrada is None:
        try:
            from reportlab.lib.fonts import addMapping
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            variantes = {
                "Arial": "LiberationSans-Regular.ttf",
                "Arial-Bold": "LiberationSans-Bold.ttf",
                "Arial-Italic": "LiberationSans-Italic.ttf",
                "Arial-BoldItalic": "LiberationSans-BoldItalic.ttf",
            }
            for nombre, archivo in variantes.items():
                pdfmetrics.registerFont(TTFont(nombre, str(_FUENTES / archivo)))
            addMapping("Arial", 0, 0, "Arial")
            addMapping("Arial", 1, 0, "Arial-Bold")
            addMapping("Arial", 0, 1, "Arial-Italic")
            addMapping("Arial", 1, 1, "Arial-BoldItalic")
            _fuente_registrada = "Arial"
        except Exception:
            _fuente_registrada = "Helvetica"
    if _fuente_registrada == "Arial":
        return "Arial", "Arial-Bold", "Arial-Italic", "Arial-BoldItalic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"


AZUL = "#1f5f9f"


def generar_pdf(
    *,
    titulo: str,
    mostrar_titulo: bool,
    lugar: str,
    fecha: date,
    destinatario: str | None,
    datos: list[dict],
    secciones: list[dict],
    numerar: bool,
    firmantes: list[dict],
    area: str | None,
    pie: str,
    leyenda: str,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import (
        KeepTogether,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    normal, negrita, _, _ = _fuente()
    ancho, alto = A4
    estilo = ParagraphStyle("cuerpo", fontName=normal, fontSize=11, leading=15.5, alignment=TA_JUSTIFY, spaceAfter=7)
    parrafo = ParagraphStyle("parrafo", parent=estilo, firstLineIndent=12 * mm)
    item = ParagraphStyle("item", parent=estilo, spaceAfter=3)
    derecha = ParagraphStyle("derecha", parent=estilo, alignment=TA_RIGHT, spaceAfter=0)
    izquierda = ParagraphStyle("izquierda", parent=estilo, alignment=TA_LEFT, spaceAfter=0)
    dato = ParagraphStyle("dato", parent=estilo, alignment=TA_LEFT, spaceAfter=1.5, leading=15)
    titulo_doc = ParagraphStyle("titulo", fontName=negrita, fontSize=12.5, leading=16, alignment=TA_CENTER, spaceBefore=4, spaceAfter=10)
    titulo_sec = ParagraphStyle("titulo_sec", fontName=negrita, fontSize=11, leading=15, spaceBefore=9, spaceAfter=5, keepWithNext=1)
    firma = ParagraphStyle("firma", fontName=normal, fontSize=10, leading=13, alignment=TA_CENTER)

    def esc(t: str | None) -> str:
        return html.escape(t or "", quote=False)

    cuerpo: list = []
    cuerpo.append(Paragraph(f"{esc(lugar)},<br/>{fecha_larga(fecha)}", derecha))
    cuerpo.append(Spacer(1, 7 * mm))
    if destinatario and destinatario.strip():
        cuerpo.append(Paragraph(esc(destinatario.strip()).replace("\n", "<br/>"), ParagraphStyle("dest", parent=izquierda, fontName=negrita)))
        cuerpo.append(Spacer(1, 6 * mm))
    if mostrar_titulo and titulo.strip():
        cuerpo.append(Paragraph(esc(titulo.strip().upper()), titulo_doc))
    visibles = [d for d in datos if (d.get("etiqueta") or "").strip()]
    if visibles:
        for d in visibles:
            cuerpo.append(Paragraph(f"<b>{esc(d['etiqueta'].strip())}</b>: {esc((d.get('valor') or '').strip())}", dato))
        cuerpo.append(Spacer(1, 4 * mm))

    n = 0
    for s in secciones:
        t = (s.get("titulo") or "").strip()
        contenido = bloques(s.get("html"))
        if not contenido:
            # Las secciones sin texto no se imprimen (aunque tengan título).
            continue
        if t:
            n += 1
            cuerpo.append(Paragraph(esc(f"{n}. {t}" if numerar else t), titulo_sec))
        for tipo, c in contenido:
            if tipo == "p":
                cuerpo.append(Paragraph(c, parrafo))  # type: ignore[arg-type]
            else:
                cuerpo.append(
                    ListFlowable(
                        [ListItem(Paragraph(x, item)) for x in c],  # type: ignore[union-attr]
                        bulletType="1" if tipo == "ol" else "bullet",
                        start="1" if tipo == "ol" else "•",
                        bulletFontName=normal,
                        bulletFontSize=10,
                        leftIndent=17 * mm,
                        bulletDedent=6 * mm,
                        spaceAfter=6,
                    )
                )

    firmas = [f for f in firmantes if (f.get("nombre") or "").strip()]
    if firmas:
        celdas = [
            Paragraph(
                "_______________________________<br/>"
                f"<b>{esc(f['nombre'].strip())}</b>"
                + (f"<br/>{esc(f.get('cargo', '').strip())}" if (f.get("cargo") or "").strip() else ""),
                firma,
            )
            for f in firmas
        ]
        filas = [celdas[i : i + 2] for i in range(0, len(celdas), 2)]
        if len(filas[-1]) == 1 and len(celdas) > 1:
            filas[-1].append("")
        util = ancho - 55 * mm
        tabla = Table(filas, colWidths=[util / 2] * 2 if len(celdas) > 1 else [util * 0.5], hAlign="RIGHT" if len(celdas) == 1 else "CENTER")
        tabla.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 16 * mm)]))
        cuerpo.append(KeepTogether([Spacer(1, 4 * mm), tabla]))

    area_txt = re.sub(r"^(Departamento|División|Dirección de)\s+", "", area or "", flags=re.I).upper()

    class Lienzo(Canvas):
        """Numera las páginas («Página 1 de 3») después de armarlas."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._marco(total)
                super().showPage()
            super().save()

        def _marco(self, total: int):
            self.saveState()
            if MEMBRETE.is_file():
                w = 78 * mm
                h = w * 387 / 1396
                self.drawImage(str(MEMBRETE), 18 * mm, alto - 12 * mm - h, w, h, mask="auto")
            if area_txt:
                self.setFillColor(colors.HexColor(AZUL))
                self.setFont(negrita, 8)
                lineas = _partir(area_txt, 34)
                y = alto - 20 * mm
                for linea in lineas:
                    self.drawRightString(ancho - 20 * mm, y, linea)
                    y -= 10
                self.setStrokeColor(colors.HexColor(AZUL))
                self.setLineWidth(0.6)
                self.line(ancho - 20 * mm - 52 * mm, y + 6, ancho - 20 * mm, y + 6)
            self.setFillColor(colors.black)
            self.setStrokeColor(colors.HexColor("#999999"))
            self.setLineWidth(0.4)
            self.line(25 * mm, 19 * mm, ancho - 25 * mm, 19 * mm)
            self.setFont(normal, 8)
            self.drawCentredString(ancho / 2, 15 * mm, pie)
            self.setFont(normal, 7)
            self.setFillColor(colors.HexColor("#666666"))
            self.drawCentredString(ancho / 2, 11 * mm, f"{leyenda} · Página {self._pageNumber} de {total}")
            self.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=27 * mm,
        rightMargin=25 * mm,
        topMargin=42 * mm,
        bottomMargin=27 * mm,
        title=titulo or "Informe",
        author="Dirección de Adultos Mayores",
        creator="SULAM",
    )
    doc.build(cuerpo, canvasmaker=Lienzo)
    return buf.getvalue()


def _partir(texto: str, largo: int) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        if actual and len(actual) + 1 + len(p) > largo:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        lineas.append(actual)
    return lineas

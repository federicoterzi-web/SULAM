"""Maquetador de fichas en papel preparadas para lectura automática.

Cada hoja A4 lleva:
- cuatro marcas negras en las esquinas, para enderezar la foto;
- un QR con el tipo de ficha, la versión y el número de página;
- casillas cuadradas para marcar con X;
- cuadrículas de una celda por dígito (DNI, fechas, números), que se leen mucho
  mejor que la escritura libre;
- recuadros para texto en imprenta.

Mientras dibuja, el maquetador registra la posición exacta (en mm, desde la
esquina superior izquierda) de cada elemento. Esa "plantilla" es la que usa el
lector para saber dónde mirar en la foto: la ficha y su lectura salen siempre
de la misma definición.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import segno
from reportlab.lib.colors import Color, black, white
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

ANCHO, ALTO = 210.0, 297.0
MARCA = 7.0  # lado de las marcas de esquina
MARCA_MARGEN = 8.0  # distancia de la marca al borde del papel
IZQ, DER = 17.0, 193.0  # área útil
ARRIBA, ABAJO = 17.0, 281.0
CASILLA = 4.2
CELDA_ANCHO, CELDA_ALTO = 5.4, 7.0
ALTO_LINEA = 8.2
GRIS = Color(0.55, 0.55, 0.55)
GRIS_CLARO = Color(0.8, 0.8, 0.8)
FUENTE, NEGRITA = "Helvetica", "Helvetica-Bold"


def centros_marcas() -> list[tuple[float, float]]:
    """Centros de las marcas (sup-izq, sup-der, inf-der, inf-izq), en mm."""
    a = MARCA_MARGEN + MARCA / 2
    return [(a, a), (ANCHO - a, a), (ANCHO - a, ALTO - a), (a, ALTO - a)]


@dataclass
class Hoja:
    c: Canvas
    ficha: str
    version: int
    pagina: int
    paginas: int
    titulo: str
    elementos: list[dict] = field(default_factory=list)
    y: float = ARRIBA

    # ------------------------------------------------------------ primitivas

    def _Y(self, y_mm: float) -> float:
        return (ALTO - y_mm) * mm

    def texto(self, x: float, y: float, s: str, tam: float = 8.5, fuente: str = FUENTE, color=black) -> float:
        self.c.setFillColor(color)
        self.c.setFont(fuente, tam)
        self.c.drawString(x * mm, self._Y(y), s)
        return self.c.stringWidth(s, fuente, tam) / mm

    def ancho_texto(self, s: str, tam: float = 8.5, fuente: str = FUENTE) -> float:
        return self.c.stringWidth(s, fuente, tam) / mm

    def rect(self, x: float, y: float, w: float, h: float, grosor: float = 0.6, color=black, relleno=False):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(grosor)
        if relleno:
            self.c.setFillColor(color)
        self.c.rect(x * mm, self._Y(y + h), w * mm, h * mm, stroke=1, fill=1 if relleno else 0)

    def linea(self, x1, y1, x2, y2, grosor=0.4, color=black, punteada=False):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(grosor)
        self.c.setDash(1, 1.5) if punteada else self.c.setDash()
        self.c.line(x1 * mm, self._Y(y1), x2 * mm, self._Y(y2))
        self.c.setDash()

    # ------------------------------------------------------------ estructura

    def encabezado(self):
        for cx, cy in centros_marcas():
            self.rect(cx - MARCA / 2, cy - MARCA / 2, MARCA, MARCA, color=black, relleno=True)
        contenido = f"SULAM|{self.ficha}|v{self.version}|p{self.pagina}"
        qr = segno.make(contenido, error="m", micro=False)
        tam_qr = 17.0
        self._dibujar_qr(qr, DER - tam_qr, ARRIBA - 2, tam_qr)
        self.elementos.append({
            "id": "qr", "tipo": "qr", "x": DER - tam_qr, "y": ARRIBA - 2, "w": tam_qr, "h": tam_qr,
        })
        self.texto(IZQ, ARRIBA + 2, "DIRECCIÓN DE ADULTOS MAYORES · PROVINCIA DE TUCUMÁN", 7.5, color=GRIS)
        self.texto(IZQ, ARRIBA + 9, self.titulo, 15, NEGRITA)
        self.texto(
            IZQ, ARRIBA + 14.5,
            "Escribir en IMPRENTA MAYÚSCULA, un dígito por casilla. Marcar las opciones con una X dentro del cuadro.",
            7, color=GRIS,
        )
        self.y = ARRIBA + 21
        self.pie()

    def _dibujar_qr(self, qr, x, y, lado):
        matriz = list(qr.matrix_iter(scale=1, border=0))
        n = len(matriz)
        modulo = lado / n
        self.c.setFillColor(black)
        for fila, valores in enumerate(matriz):
            for col, v in enumerate(valores):
                if v:
                    self.c.rect((x + col * modulo) * mm, self._Y(y + (fila + 1) * modulo), modulo * mm + 0.05,
                                modulo * mm + 0.05, stroke=0, fill=1)

    def pie(self):
        self.texto(
            IZQ, ABAJO + 1.5,
            f"SULAM · {self.titulo.capitalize()} · versión {self.version} · hoja {self.pagina} de {self.paginas}",
            6.5, color=GRIS,
        )

    def seccion(self, titulo: str):
        self.y += 3.2
        self.texto(IZQ, self.y, titulo.upper(), 9, NEGRITA)
        self.linea(IZQ, self.y + 1.2, DER, self.y + 1.2, 0.5)
        self.y += 4.2

    def fila(self, sangria: float = 0.0) -> "Fila":
        return Fila(self, IZQ + sangria)

    def espacio(self, mm_: float):
        self.y += mm_

    def lineas_libres(self, campo: str, renglones: int, etiqueta: str | None = None):
        """Recuadro de varias líneas para texto libre."""
        if etiqueta:
            self.texto(IZQ, self.y + 3, etiqueta, 8.5, NEGRITA)
            self.y += 4.5
        alto = renglones * 7.0
        self.rect(IZQ, self.y, DER - IZQ, alto)
        for i in range(1, renglones):
            self.linea(IZQ + 1, self.y + i * 7.0, DER - 1, self.y + i * 7.0, 0.3, GRIS_CLARO)
        self.elementos.append({
            "id": campo, "tipo": "texto", "campo": campo, "renglones": renglones,
            "x": IZQ, "y": self.y, "w": DER - IZQ, "h": alto,
        })
        self.y += alto + 1.5


class Fila:
    """Una línea del formulario que se completa de izquierda a derecha y salta sola."""

    def __init__(self, hoja: Hoja, x: float):
        self.h = hoja
        self.x0 = x
        self.x = x
        self.alto = ALTO_LINEA

    def _base(self) -> float:
        return self.h.y + 5.2  # línea de base del texto

    def _cabe(self, ancho: float):
        if self.x + ancho > DER + 0.01:
            self.salto()

    def salto(self, sangria: float = 6.0):
        self.h.y += self.alto
        self.x = self.x0 + sangria

    def etiqueta(self, s: str, negrita: bool = True, tam: float = 8.5):
        w = self.h.ancho_texto(s, tam, NEGRITA if negrita else FUENTE)
        self._cabe(w + 1.5)
        self.h.texto(self.x, self._base(), s, tam, NEGRITA if negrita else FUENTE)
        self.x += w + 1.5
        return self

    def separador(self, mm_: float = 3.5):
        self.x += mm_
        return self

    def digitos(self, campo: str, n: int, separadores: tuple[int, ...] = (), simbolo: str = "/",
                prefijos: dict[int, str] | None = None):
        """Cuadrícula de un dígito por celda. `prefijos` imprime texto fijo antes de
        una celda (por ejemplo, el «20» de los años)."""
        prefijos = prefijos or {}
        ancho_pref = sum(self.h.ancho_texto(t, 9.5, NEGRITA) + 1.2 for t in prefijos.values())
        ancho = n * CELDA_ANCHO + len(separadores) * 2.8 + ancho_pref
        self._cabe(ancho + 1)
        y = self.h.y + 0.6
        celdas = []
        x = self.x
        for i in range(n):
            if i in separadores:
                self.h.texto(x + 0.7, self._base() + 0.3, simbolo, 9)
                x += 2.8
            if i in prefijos:
                x += self.h.texto(x + 0.3, self._base() + 0.3, prefijos[i], 9.5, NEGRITA) + 1.2
            self.h.rect(x, y, CELDA_ANCHO, CELDA_ALTO, 0.5)
            celdas.append({"x": round(x, 3), "y": round(y, 3), "w": CELDA_ANCHO, "h": CELDA_ALTO})
            x += CELDA_ANCHO
        elemento = {
            "id": campo, "tipo": "digitos", "campo": campo, "celdas": celdas,
            "x": self.x, "y": y, "w": x - self.x, "h": CELDA_ALTO,
        }
        if prefijos:
            elemento["prefijos"] = {str(k): v for k, v in prefijos.items()}
        self.h.elementos.append(elemento)
        self.x = x + 1.5
        return self

    def fecha(self, campo: str, siglo: str = "20"):
        """DD / MM / 20AA: el siglo va impreso y se completan dos dígitos del año."""
        return self.digitos(campo, 6, separadores=(2, 4), prefijos={4: siglo})

    def anio(self, campo: str, siglo: str = "20"):
        return self.digitos(campo, 2, prefijos={0: siglo})

    def caja(self, campo: str, ancho: float | None = None, minimo: float = 30):
        """Recuadro de una línea para texto. Sin ancho, ocupa lo que queda de la línea."""
        if ancho is None:
            if DER - self.x < minimo:
                self.salto()
            ancho = DER - self.x
        self._cabe(ancho)
        y = self.h.y + 0.6
        self.h.rect(self.x, y, ancho, CELDA_ALTO, 0.5)
        self.h.elementos.append({
            "id": campo, "tipo": "texto", "campo": campo, "renglones": 1,
            "x": self.x, "y": y, "w": ancho, "h": CELDA_ALTO,
        })
        self.x += ancho + 1.5
        return self

    def casilla(self, campo: str, valor: str, texto: str, grupo_unico: bool = False, tam: float = 8.5):
        w_txt = self.h.ancho_texto(texto, tam)
        self._cabe(CASILLA + 1.4 + w_txt + 1)
        y = self.h.y + (ALTO_LINEA - CASILLA) / 2 - 0.4
        self.h.rect(self.x, y, CASILLA, CASILLA, 0.7)
        self.h.elementos.append({
            "id": f"{campo}={valor}", "tipo": "casilla", "campo": campo, "valor": valor,
            "unica": grupo_unico, "x": round(self.x, 3), "y": round(y, 3), "w": CASILLA, "h": CASILLA,
        })
        self.h.texto(self.x + CASILLA + 1.4, self._base(), texto, tam)
        self.x += CASILLA + 1.4 + w_txt + 3.2
        return self

    def texto(self, s: str, tam: float = 8.5, color=black):
        w = self.h.ancho_texto(s, tam)
        self._cabe(w)
        self.h.texto(self.x, self._base(), s, tam, color=color)
        self.x += w + 1.2
        return self

    def fin(self):
        self.h.y += self.alto
        return self.h


@dataclass
class Ficha:
    codigo: str
    titulo: str
    version: int
    hojas: list[Hoja] = field(default_factory=list)


def generar(codigo: str, titulo: str, version: int, dibujantes: list) -> tuple[bytes, dict]:
    """Genera el PDF y la plantilla. `dibujantes` es una lista de funciones, una por hoja."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(ANCHO * mm, ALTO * mm))
    c.setTitle(f"SULAM - {titulo.capitalize()} (v{version})")
    c.setAuthor("SULAM - Dirección de Adultos Mayores de Tucumán")
    paginas = []
    for i, dibujar in enumerate(dibujantes, start=1):
        hoja = Hoja(c, codigo, version, i, len(dibujantes), titulo)
        c.setFillColor(white)
        hoja.encabezado()
        dibujar(hoja)
        if hoja.y > ABAJO - 2:
            raise ValueError(f"La hoja {i} de {codigo} se pasa del área útil ({hoja.y:.1f} mm)")
        paginas.append({"pagina": i, "elementos": hoja.elementos, "alto_usado": round(hoja.y, 1)})
        c.showPage()
    c.save()
    plantilla = {
        "ficha": codigo,
        "titulo": titulo,
        "version": version,
        "tamano_mm": [ANCHO, ALTO],
        "marcas_mm": centros_marcas(),
        "marca_lado_mm": MARCA,
        "paginas": paginas,
    }
    return buf.getvalue(), plantilla

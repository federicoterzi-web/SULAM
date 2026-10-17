"""Fichas en papel de la Dirección (versión 1, con marcas para lectura automática).

Contenido y textos: «Modelo de carátula de legajo» y «Registro de demanda»
de la Dirección. Las opciones de casillas salen de `formularios.py`, de modo
que lo impreso, lo que se carga en pantalla y lo que se lee de una foto
coinciden siempre. Se agrega una «Hoja de evolución» para continuar la
evolución del caso a mano.
"""

from __future__ import annotations

from functools import lru_cache

from .. import formularios as F
from .maqueta import GRIS as F_GRIS
from .maqueta import Hoja, generar

VERSION = 1


def _identificacion(h: Hoja):
    """Legajo N° = DNI de la persona. Actuación N° / año = número de caso."""
    f = h.fila()
    f.etiqueta("LEGAJO N° (DNI)").digitos("numero_legajo", 8)
    f.casilla("sin_dni", "si", "Sin DNI").separador(1)
    f.etiqueta("ACTUACIÓN N°").digitos("numero_actuacion", 5).etiqueta("/ AÑO").anio("anio_actuacion")
    f.fin()


def _grupo_jerarquico(h: Hoja, campo: str, catalogo: dict, extras: dict | None = None, excluir=()):
    """Cada grupo con subopciones empieza una línea, como en el modelo:
    «Maltrato (Físico | ...)», «Negligencia (...) Situación de calle», etc."""
    extras = extras or {}
    f = None
    for grupo, (texto, subs) in catalogo.items():
        if grupo in excluir:
            continue
        if f is None or subs or grupo in extras:
            if f is not None:
                f.fin()
            f = h.fila(sangria=4)
        f.casilla(campo, grupo, texto)
        if subs:
            f.texto("(", color=F_GRIS)
            for s, st in subs.items():
                f.casilla(campo, f"{grupo}.{s}", st)
            f.texto(")", color=F_GRIS)
        if grupo in extras:
            f.caja(extras[grupo], minimo=45)
            f.fin()
            f = None
    if f is not None:
        f.fin()


def _plano(f, campo: str, catalogo: dict, unica: bool, excluir=()):
    for codigo, texto in catalogo.items():
        if codigo not in excluir:
            f.casilla(campo, codigo, texto, grupo_unico=unica)
    return f


def _si_no(f, campo: str):
    return f.casilla(campo, "si", "Sí", grupo_unico=True).casilla(campo, "no", "No", grupo_unico=True)


def _tipo_ingreso(h: Hoja, con_derivada_texto: bool):
    f = h.fila()
    f.etiqueta("Tipo de ingreso:")
    f.casilla("tipo_ingreso", "espontaneo", "Espontáneo", True)
    f.texto("(")
    f.casilla("tipo_ingreso_detalle", "presencial", "Presencial", True)
    f.casilla("tipo_ingreso_detalle", "no_presencial", "No presencial", True)
    f.texto(")")
    f.casilla("tipo_ingreso", "mesa_entrada", "Mesa de Entrada", True)
    f.texto("(")
    f.casilla("tipo_ingreso_detalle", "amparo", "Amparo", True)
    f.texto(")")
    f.casilla("tipo_ingreso", "portal_sae", "Portal SAE", True)
    f.casilla("tipo_ingreso", "derivada", "Derivada" + (":" if con_derivada_texto else ""), True)
    if con_derivada_texto:
        f.caja("derivado_por_detalle", minimo=50)
    f.fin()


# ------------------------------------------------------------------ carátula


def _caratula(h: Hoja):
    _identificacion(h)

    h.seccion("Datos de la persona mayor")
    h.fila().etiqueta("Apellido y nombre:").caja("persona.apellido_nombre").fin()
    f = h.fila()
    f.etiqueta("Fecha de nacimiento").fecha("persona.fecha_nacimiento", siglo="19").separador(3)
    f.etiqueta("Edad").digitos("edad", 3)
    f.fin()
    f = h.fila().etiqueta("Género:")
    _plano(f, "persona.genero", F.GENEROS, True).separador(6)
    f.etiqueta("CUD:")
    _plano(f, "persona.cud", F.CUD, True)
    f.fin()
    f = h.fila().etiqueta("Cobertura de salud:")
    _plano(f, "persona.cobertura_salud", F.COBERTURA_SALUD, False)
    f.caja("persona.obra_social", minimo=40)
    f.fin()

    h.seccion("Domicilio")
    h.fila().etiqueta("Dirección:").caja("persona.domicilio").fin()
    f = h.fila()
    f.etiqueta("Localidad:").caja("persona.localidad", 58).etiqueta("Departamento:").caja("persona.departamento")
    f.fin()
    h.fila().etiqueta("Teléfono").digitos("persona.telefono", 12).fin()

    h.seccion("Información administrativa")
    f = h.fila()
    f.etiqueta("Fecha de ingreso").fecha("fecha_ingreso").separador(4)
    f.etiqueta("¿Tiene antecedentes?")
    _si_no(f, "antecedentes")
    f.fin()
    h.fila().etiqueta("Fecha del último ingreso").fecha("fecha_ultimo_ingreso").fin()
    h.lineas_libres("motivo", 3, "Motivo de ingreso:")
    _tipo_ingreso(h, con_derivada_texto=True)
    h.fila().etiqueta("Indicadores:").fin()
    _grupo_jerarquico(h, "indicadores", F.INDICADORES)
    h.fila().etiqueta("Tipo de intervención:").fin()
    _grupo_jerarquico(
        h, "intervenciones", F.INTERVENCIONES,
        extras={"derivacion": "intervencion_derivacion", "otro": "intervencion_otro"},
    )


# ------------------------------------------------------------------ registro de demanda


def _registro_1(h: Hoja):
    _identificacion(h)

    h.seccion("1. Datos del solicitante")
    h.fila().etiqueta("Solicitante:").caja("solicitante_nombre").fin()
    h.fila().etiqueta("Vínculo con la persona mayor:").caja("solicitante_vinculo").fin()
    h.fila().etiqueta("Teléfono").digitos("solicitante_telefono", 12).fin()

    h.seccion("2. Datos de la persona mayor")
    h.fila().etiqueta("Apellido y nombre:").caja("persona.apellido_nombre").fin()
    f = h.fila()
    f.etiqueta("Fecha de nacimiento").fecha("persona.fecha_nacimiento", siglo="19").separador(3)
    f.etiqueta("Edad").digitos("edad", 3)
    f.fin()
    f = h.fila().etiqueta("Género:")
    _plano(f, "genero", F.GENEROS, True).separador(6)
    f.etiqueta("Teléfono").digitos("telefono", 12)
    f.fin()

    h.seccion("3. Motivo de consulta")
    h.lineas_libres("solicitud_expresa", 2, "Solicitud expresa:")
    h.fila().etiqueta("Indicadores:").fin()
    _grupo_jerarquico(h, "indicadores", F.INDICADORES)
    h.fila().etiqueta("Tipo de intervención solicitada:").fin()
    _grupo_jerarquico(h, "intervenciones", F.INTERVENCIONES, extras={"otro": "intervencion_otro"}, excluir=("derivacion",))

    h.seccion("4. Cobertura social y previsional")
    f = h.fila().etiqueta("Cobertura previsional:")
    _plano(f, "cobertura_previsional", F.COBERTURA_PREVISIONAL, False)
    f.casilla("trabajo_informal", "si", "Trabajo informal")
    f.fin()
    f = h.fila().etiqueta("Cobertura de salud:")
    _plano(f, "cobertura_salud", F.COBERTURA_SALUD, False)
    f.caja("obra_social", minimo=40)
    f.fin()
    f = h.fila().etiqueta("CUD:")
    _plano(f, "cud", F.CUD, True).separador(6)
    f.fin()
    f = h.fila().etiqueta("Discapacidad:")
    _plano(f, "discapacidades", F.DISCAPACIDAD, False)
    f.fin()



def _registro_2(h: Hoja):
    _identificacion(h)

    h.seccion("5. Situación habitacional")
    h.fila().etiqueta("Domicilio:").caja("domicilio").fin()
    f = h.fila().etiqueta("Barrio:").caja("barrio", 44).etiqueta("Localidad:").caja("localidad", 44)
    f.etiqueta("Departamento:").caja("departamento", minimo=25)
    f.fin()
    f = h.fila().etiqueta("Tipo de vivienda:")
    _plano(f, "tipo_vivienda", F.TIPO_VIVIENDA, True)
    f.caja("vivienda_institucional", minimo=35)
    f.fin()

    h.seccion("6. Situación familiar")
    f = h.fila().etiqueta("Estado civil:")
    _plano(f, "estado_civil", F.ESTADO_CIVIL, True)
    f.fin()
    f = h.fila().etiqueta("Tiene hijos:")
    _si_no(f, "tiene_hijos")
    f.separador(3).etiqueta("Cantidad").digitos("cantidad_hijos", 2).separador(3)
    f.etiqueta("Tiene vínculo con ellos:")
    _si_no(f, "vinculo_con_hijos")
    f.fin()
    h.fila().etiqueta("Con quién convive:").caja("convive_con").fin()
    h.fila().etiqueta("Referente:").caja("referente_nombre").fin()
    f = h.fila().etiqueta("Vínculo:").caja("referente_vinculo", 60).etiqueta("Teléfono").digitos("referente_telefono", 12)
    f.fin()

    h.seccion("7. Situación de salud")
    h.lineas_libres("diagnosticos", 2, "Diagnósticos relevantes:")
    f = h.fila().etiqueta("Tiene autonomía:")
    _si_no(f, "tiene_autonomia")
    f.separador(6).etiqueta("Estado funcional:")
    _plano(f, "estado_funcional", F.ESTADO_FUNCIONAL, True)
    f.fin()

    h.seccion("8. Ingreso al sistema")
    _tipo_ingreso(h, con_derivada_texto=False)
    f = h.fila().etiqueta("Derivado por:")
    _plano(f, "derivado_por", F.DERIVADO_POR, True)
    f.caja("derivado_por_detalle", minimo=40)
    f.fin()
    h.fila().etiqueta("Agente a cargo:").caja("agente_nombre").fin()

    h.seccion("Observaciones / datos relevantes")
    h.lineas_libres("observaciones", 3)
    f = h.fila().etiqueta("Lugar:").caja("lugar", 80).etiqueta("Fecha").fecha("fecha")
    f.fin()
    h.espacio(8)
    h.linea(110, h.y, 193, h.y, 0.5)
    h.texto(128, h.y + 3.5, "Firma del receptor", 8)
    h.espacio(5)
    h.fila(sangria=93).etiqueta("Aclaración:").caja("receptor_nombre").fin()
    h.texto(17, h.y - 3, "La evolución del caso se registra en la «Hoja de evolución».", 7.5)


# ------------------------------------------------------------------ hoja de evolución

ENTRADAS_EVOLUCION = 5


def _evolucion(h: Hoja):
    _identificacion(h)
    for i in range(1, ENTRADAS_EVOLUCION + 1):
        h.seccion(f"Intervención {i}")
        f = h.fila().etiqueta("Fecha").fecha(f"evolucion.{i}.fecha").separador(3)
        f.etiqueta("Realizada por:").caja(f"evolucion.{i}.autor")
        f.fin()
        h.lineas_libres(f"evolucion.{i}.texto", 4)


# ------------------------------------------------------------------ catálogo de fichas

FICHAS = {
    "CAR": ("CARÁTULA DE LEGAJO", [_caratula]),
    "RDD": ("REGISTRO DE DEMANDA", [_registro_1, _registro_2]),
    "EVO": ("HOJA DE EVOLUCIÓN", [_evolucion]),
}

NOMBRES_ARCHIVO = {
    "CAR": "caratula-de-legajo",
    "RDD": "registro-de-demanda",
    "EVO": "hoja-de-evolucion",
}


@lru_cache
def ficha(codigo: str) -> tuple[bytes, dict]:
    """PDF en blanco y plantilla de lectura de una ficha."""
    titulo, hojas = FICHAS[codigo]
    return generar(codigo, titulo, VERSION, hojas)

"""Datos de demostración ampliados (todos FICTICIOS).

Completan lo que carga `datos-demo` para que cada rol tenga algo que ver al
entrar: casos repartidos en el año con indicadores, registros de demanda y
evoluciones; recursos y contactos en el mapa; Mesa de Entrada; novedades;
carpetas en papel y pases; negativas de ANSES; un informe en borrador; y para
Personal, semanas del reloj, pedidos en distintos estados y quién no está hoy.

Nombres, documentos, domicilios y teléfonos son inventados. No usar en producción.
"""
from __future__ import annotations

import hashlib
import io
import random
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    EventoAgenda,
    ParticipanteAgenda,
    Agente,
    Area,
    Articulacion,
    Caso,
    CasoAsignacion,
    CasoEstadoHistorial,
    CasoEvolucion,
    Constancia,
    Contacto,
    Expediente,
    Horario,
    Informe,
    Ingreso,
    Justificativo,
    Marcacion,
    Novedad,
    NovedadLectura,
    Pase,
    Persona,
    PersonaVinculada,
    PlantillaInforme,
    Recurso,
    RegistroDemanda,
    Reiteracion,
    RelojImportacion,
    RevisionJornada,
    SolicitudPersonal,
    TipoDocumental,
    TipoVinculo,
    UbicacionFisica,
    Usuario,
)
from .numbering import nueva_actuacion, numero_ingreso, numero_legajo
from .textutil import normalizar

ADMISION = "Departamento Admisión de Casos y Recepción de Denuncias"
PROMOCION = "Departamento Promoción Integral de Derechos"
CUIDADOS = "División Cuidados y Promoción de Autonomía"
ADMINISTRATIVA = "División Asistencia Administrativa"
DIRECCION = "Dirección de Adultos Mayores"
REGISTRO = "Oficina de Registro"

# localidad → (departamento, lat, lng)
LUGARES = {
    "San Miguel de Tucumán": ("Capital", -26.8241, -65.2226),
    "Yerba Buena": ("Yerba Buena", -26.8167, -65.3167),
    "Tafí Viejo": ("Tafí Viejo", -26.7322, -65.2592),
    "Banda del Río Salí": ("Cruz Alta", -26.8333, -65.1667),
    "Alderetes": ("Cruz Alta", -26.8167, -65.1333),
    "Famaillá": ("Famaillá", -27.0544, -65.4031),
    "Lules": ("Lules", -26.9333, -65.3333),
    "Monteros": ("Monteros", -27.1667, -65.5000),
    "Concepción": ("Chicligasta", -27.3433, -65.5936),
    "Aguilares": ("Río Chico", -27.4333, -65.6167),
}

APELLIDOS = [
    "RODRÍGUEZ", "GÓMEZ", "DÍAZ", "MORALES", "SORIA", "JUÁREZ", "LEDESMA", "VILLAFAÑE", "CÓRDOBA", "BRITO", "PAZ", "ROMANO",
    "MEDINA", "NIEVA", "ALBORNOZ", "QUIROGA", "TOLEDO", "VERA", "CARRIZO", "FIGUEROA", "LUNA", "OLEA", "SALAS", "GUZMÁN",
]
NOMBRES_F = ["Ramona", "Elsa", "Nélida", "Teresa", "Blanca", "Olga", "Irma", "Zulema", "Dora", "Amalia", "Haydée", "Norma"]
NOMBRES_M = ["Hugo", "Ramón", "Julio", "Oscar", "Segundo", "Ángel", "Carlos", "Pedro", "Rubén", "Mario", "Luis", "Raúl"]

MOTIVOS = [
    ("Hija refiere maltrato psicológico por parte de un familiar conviviente (ficticio).", ["maltrato.psicologico"]),
    ("Vecinos informan que la persona vive sola y no recibe asistencia (ficticio).", ["negligencia.abandono", "negligencia.aislamiento"]),
    ("Solicita acompañamiento para tramitar pensión (ficticio).", ["vulnerabilidad.economica"]),
    ("Denuncia de apropiación de haberes por parte de un sobrino (ficticio).", ["maltrato.economico"]),
    ("Vivienda en condiciones precarias, riesgo de derrumbe (ficticio).", ["vulnerabilidad.habitacional"]),
    ("Hospital informa alta sin red de cuidados (ficticio).", ["vulnerabilidad.socio_sanitaria", "negligencia.abandono"]),
    ("Persona en situación de calle en la plaza de la localidad (ficticio).", ["situacion_calle", "vulnerabilidad.alimentaria"]),
    ("Consulta por ingreso a residencia de larga estadía (ficticio).", ["no_califica"]),
    ("Denuncia de golpes por parte del yerno, con lesiones visibles (ficticio).", ["maltrato.fisico"]),
    ("Falta de alimentos y medicación, ingresos insuficientes (ficticio).", ["vulnerabilidad.alimentaria", "vulnerabilidad.economica"]),
]
INTERVENCIONES = [["asesoramiento"], ["subsidio.alimentario"], ["derivacion"], ["subsidio.cuidados"], ["asesoramiento", "derivacion"], ["internacion_rle"], []]
EVOLUCIONES = [
    "Se realizó visita domiciliaria. La persona se encuentra lúcida y colaboradora (ficticio).",
    "Llamado telefónico a la referente familiar; se acuerda nueva entrevista (ficticio).",
    "Se articuló con el CAPS de la zona para control de salud (ficticio).",
    "Se entregó módulo alimentario y se orientó sobre trámites (ficticio).",
    "Entrevista en sede con la hija; refiere mejoras en la convivencia (ficticio).",
    "Se envió nota a la comuna solicitando relevamiento habitacional (ficticio).",
]


def _dt(d: date, h: int = 10, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m)).astimezone()


def _habil(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def cargar(db: Session, usuarios: dict[str, Usuario], personas: list[Persona], casos: list[Caso], almacen, tecnicos_reales: dict[str, list[Usuario]] | None = None) -> None:
    """Agrega los datos ampliados. ``personas`` y ``casos`` son los de la carga base."""
    rnd = random.Random(2026)
    hoy = date.today()
    areas = {a.nombre: a for a in db.execute(select(Area)).scalars()}
    tipos = {t.nombre: t for t in db.execute(select(TipoDocumental)).scalars()}
    vinculos = {t.nombre: t for t in db.execute(select(TipoVinculo)).scalars()}
    U = usuarios

    # ------------------------------------------------------------ completar los casos base
    base_info = [
        (200, ["vulnerabilidad.habitacional"], ["asesoramiento"], "espontaneo", "presencial", None),
        (120, ["vulnerabilidad.economica"], ["derivacion"], "derivada", None, "gobierno_local"),
        (35, ["maltrato.economico", "maltrato.psicologico"], ["asesoramiento"], "mesa_entrada", None, None),
        (160, ["negligencia.aislamiento"], ["subsidio.cuidados"], "derivada", None, "siprosa"),
        (240, ["no_califica"], ["asesoramiento"], "espontaneo", "no_presencial", None),
    ]
    for c, (dias, ind, inter, ti, tid, der) in zip(casos, base_info):
        fi = _habil(hoy - timedelta(days=dias))
        c.fecha_ingreso, c.indicadores, c.intervenciones = fi, ind, inter
        c.tipo_ingreso, c.tipo_ingreso_detalle, c.derivado_por = ti, tid, der
        c.abierto_en = _dt(fi)
        c.ultima_actividad = _dt(hoy - timedelta(days=rnd.randint(1, 20)))
        if c.estado == "cerrado":
            c.cerrado_en = _dt(fi + timedelta(days=45))
        for a in db.execute(select(CasoAsignacion).where(CasoAsignacion.caso_id == c.id)).scalars():
            a.desde = _dt(fi + timedelta(days=2), 11)
    datos_base = [("F", "Capital"), ("M", "Yerba Buena"), ("F", "Tafí Viejo"), ("M", "Famaillá"), ("F", "Cruz Alta"), ("M", "Chicligasta")]
    for p, (g, dep) in zip(personas, datos_base):
        p.genero, p.departamento = g, dep
        p.cobertura_salud = ["pami"]
        p.cobertura_previsional = [rnd.choice(["jubilacion", "pension", "puam"])]
        p.cud = rnd.choice(["no", "no", "si", "en_tramite"])
        p.discapacidades = [rnd.choice(["sin_discapacidad", "sin_discapacidad", "motora", "visual"])]

    # ------------------------------------------------------------ más personas y casos
    tecnicos_area = {
        ADMISION: [U["tecnica1"], U["tecnica3"]],
        PROMOCION: [U["tecnico2"]],
        CUIDADOS: [U["tecnico4"]],
    }
    for area_nombre, lista in (tecnicos_reales or {}).items():
        if area_nombre in tecnicos_area and lista:
            tecnicos_area[area_nombre] = lista
    nuevas: list[Persona] = []
    nuevos: list[Caso] = []
    usados_doc = {p.numero_documento for p in personas}
    for i in range(26):
        mujer = rnd.random() < 0.62
        localidad = rnd.choice(list(LUGARES))
        dep, lat, lng = LUGARES[localidad]
        doc = str(rnd.randint(2_100_000, 11_900_000))
        while doc in usados_doc:
            doc = str(int(doc) + 7)
        usados_doc.add(doc)
        nac = date(hoy.year - rnd.randint(61, 94), rnd.randint(1, 12), rnd.randint(1, 28))
        ap = rnd.choice(APELLIDOS)
        no = rnd.choice(NOMBRES_F if mujer else NOMBRES_M)
        p = Persona(
            numero_legajo=numero_legajo(db, "DNI", doc), apellidos=ap, nombres=no, apellidos_norm=normalizar(ap), nombres_norm=normalizar(no),
            tipo_documento="DNI", numero_documento=doc, fecha_nacimiento=nac, fecha_nacimiento_aproximada=False,
            genero="F" if mujer else "M", localidad=localidad, departamento=dep, barrio=f"Barrio {rnd.choice(['Norte', 'Sur', 'Centro', 'Oeste', 'El Palomar', 'San Cayetano'])} (ficticio)",
            domicilio=f"Calle Ficticia {rnd.randint(100, 2900)}", telefono=f"381 000-{1000 + i:04d}",
            lat=lat + rnd.uniform(-0.012, 0.012), lng=lng + rnd.uniform(-0.012, 0.012), ubicacion_actualizada_en=_dt(hoy - timedelta(days=30)),
            cobertura_salud=rnd.choice([["pami"], ["pami"], ["incluir_salud"], ["salud_publica"], ["ipsst"], ["obra_social"]]),
            cobertura_previsional=rnd.choice([["jubilacion"], ["jubilacion"], ["pension"], ["puam"], ["pnc"], ["sin_cobertura"], ["en_tramite"]]),
            cud=rnd.choice(["no", "no", "no", "si", "en_tramite"]),
            discapacidades=rnd.choice([["sin_discapacidad"], ["sin_discapacidad"], ["motora"], ["visual"], ["auditiva"], ["motora", "visual"]]),
            trabajo_informal=rnd.random() < 0.2, creado_por=U["carga"].id,
        )
        if p.cobertura_salud == ["obra_social"]:
            p.obra_social = "Obra social ficticia"
        db.add(p)
        nuevas.append(p)
    db.flush()

    for i, p in enumerate(nuevas):
        area = rnd.choices([ADMISION, PROMOCION, CUIDADOS], weights=[5, 3, 2])[0]
        motivo, ind = MOTIVOS[i % len(MOTIVOS)]
        dias = rnd.randint(2, 280)
        recientes = {0: 1, 1: 3, 2: 4, 3: 7, 4: 9, 5: 12, 6: 16}
        if i in recientes:  # casos del mes, para que los inicios tengan movimiento
            dias = recientes[i]
            area = ADMISION if i % 2 == 0 else rnd.choice([PROMOCION, CUIDADOS])
        fi = _habil(hoy - timedelta(days=dias))
        anio, n, numero = nueva_actuacion(db, fi.year)
        estado = "cerrado" if dias > 120 and rnd.random() < 0.45 else "abierto" if dias < 20 else rnd.choice(["abierto", "en_seguimiento", "en_seguimiento", "pausado"])
        ti = rnd.choice(["espontaneo", "espontaneo", "mesa_entrada", "derivada", "portal_sae"])
        c = Caso(
            numero=numero, numero_actuacion=n, anio_actuacion=anio, persona_id=p.id, area_id=areas[area].id, estado=estado, motivo=motivo,
            fecha_ingreso=fi, indicadores=_con_grupos(ind), intervenciones=_con_grupos(rnd.choice(INTERVENCIONES)),
            tipo_ingreso=ti, tipo_ingreso_detalle={"espontaneo": rnd.choice(["presencial", "no_presencial"]), "mesa_entrada": None}.get(ti),
            derivado_por=rnd.choice(["gobierno_local", "mpf", "poder_judicial", "siprosa", "ministerio_seguridad"]) if ti == "derivada" else None,
            antecedentes=rnd.random() < 0.25, abierto_en=_dt(fi, 9), creado_por=U["carga"].id,
        )
        db.add(c)
        db.flush()
        db.add(CasoEstadoHistorial(caso_id=c.id, estado_nuevo="abierto", usuario_id=U["carga"].id, en=_dt(fi, 9)))
        # Responsables: casi todos con técnico; algunos recientes de Admisión, sin asignar.
        sin_asignar = i in (0, 2, 4)  # recientes de Admisión: «para asignar»
        responsables = [] if sin_asignar else [rnd.choice(tecnicos_area[area])]
        if responsables and rnd.random() < 0.15 and area == ADMISION:
            responsables = tecnicos_area[ADMISION]
        jefe = U["jefa_admision"] if area == ADMISION else U["jefe_promocion"] if area == PROMOCION else U["jefa_cuidados"]
        for u in responsables:
            db.add(CasoAsignacion(caso_id=c.id, usuario_id=u.id, asignado_por=jefe.id, desde=_dt(fi + timedelta(days=rnd.randint(0, 6)), 11)))
        # Evoluciones
        ultima = fi
        if responsables:
            for k in range(rnd.randint(1, 4)):
                f = min(hoy, fi + timedelta(days=rnd.randint(3, max(4, dias))))
                autor = rnd.choice(responsables)
                db.add(CasoEvolucion(caso_id=c.id, texto=rnd.choice(EVOLUCIONES), fecha=f, autor_id=autor.id, usuario_id=autor.id, en=_dt(f, 12)))
                ultima = max(ultima, f)
        # Algunos activos quedan quietos (más de 30 días sin movimiento).
        if estado != "cerrado" and i % 5 == 1:
            ultima = min(ultima, hoy - timedelta(days=rnd.randint(35, 70)))
        c.ultima_actividad = _dt(ultima, 13)
        if estado != "abierto":
            db.add(CasoEstadoHistorial(caso_id=c.id, estado_anterior="abierto", estado_nuevo=estado, motivo="Cambio de estado (ficticio)",
                                       usuario_id=(responsables[0] if responsables else jefe).id, en=_dt(min(hoy, fi + timedelta(days=20)), 15)))
        if estado == "cerrado":
            c.cerrado_en = _dt(min(hoy, fi + timedelta(days=rnd.randint(30, 110))), 15)
            c.ultima_actividad = c.cerrado_en
        # Registro de demanda (la mayoría)
        if i % 4 != 3:
            db.add(RegistroDemanda(
                caso_id=c.id, persona_id=p.id, fecha=fi, solicitante_nombre=rnd.choice(["La propia persona", "Hija (ficticia)", "Vecina (ficticia)", "Sobrino (ficticio)"]),
                solicitante_vinculo=rnd.choice(["Propia persona", "Hija", "Vecina", "Sobrino"]), solicitud_expresa=motivo,
                tipo_vivienda=rnd.choice(["propia", "propia", "alquilada", "prestada", "tenencia_precaria"]),
                estado_civil=rnd.choice(["viudo", "viudo", "casado", "soltero", "separado"]), tiene_hijos=rnd.random() < 0.75,
                convive_con=rnd.choice(["Sola/o", "Hija", "Hijo y nuera", "Pareja", "Nietos"]), estado_funcional=rnd.choice(["independiente", "semidependiente", "dependiente"]),
                tiene_autonomia=rnd.random() < 0.6, indicadores=c.indicadores, intervenciones=c.intervenciones, tipo_ingreso=ti,
                receptor_id=U["carga"].id, lugar="Sede de la Dirección", cargado_desde_papel=rnd.random() < 0.5, creado_por=U["carga"].id,
            ))
        nuevos.append(c)
    db.flush()

    # Reiteraciones (una reciente, para el aviso del inicio).
    for c, dias in ((nuevos[3], 2), (nuevos[10], 60), (casos[0], 12)):
        db.add(Reiteracion(caso_id=c.id, fecha=max(c.fecha_ingreso, hoy - timedelta(days=dias)), motivo="Nueva llamada por la misma situación (ficticio)", tipo_ingreso="espontaneo",
                           usuario_id=U["carga"].id))
    for p in nuevas[:6]:
        db.add(PersonaVinculada(persona_id=p.id, tipo_vinculo_id=vinculos["Familiar"].id, apellidos=p.apellidos, nombres="Referente familiar (ficticio)",
                                telefono="381 000-9999", creado_por=U["carga"].id))

    # ------------------------------------------------------------ recursos, contactos y articulaciones
    recursos_def = [
        ("centro_dia", None, "Centro de Día «Los Aromos» (ficticio)", "San Miguel de Tucumán", "Lunes a viernes de 8 a 16"),
        ("centro_jubilados", None, "Centro de Jubilados «Amanecer» (ficticio)", "Yerba Buena", "Martes y jueves de 16 a 20"),
        ("residencia", None, "Residencia de larga estadía «San Roque» (ficticia)", "Tafí Viejo", "Todos los días"),
        ("institucion", "salud", "CAPS Barrio Norte (ficticio)", "San Miguel de Tucumán", "Lunes a viernes de 7 a 13"),
        ("institucion", "municipio", "Comuna de Alderetes - Área social (ficticia)", "Alderetes", "Lunes a viernes de 8 a 13"),
        ("institucion", "seguridad", "Comisaría de Famaillá (ficticia)", "Famaillá", "24 horas"),
        ("institucion", "justicia", "Defensoría ficticia de Concepción", "Concepción", "Lunes a viernes de 8 a 13"),
        ("cuidador", None, "Cuidadora formada Ficticia, Graciela", "Lules", "Mañanas"),
    ]
    recursos = []
    for tipo, cat, nombre, loc, horario in recursos_def:
        dep, lat, lng = LUGARES[loc]
        r = Recurso(tipo=tipo, categoria=cat, nombre=nombre, nombre_norm=normalizar(nombre), direccion=f"Calle Ficticia {rnd.randint(100, 999)}", localidad=loc,
                    departamento=dep, lat=lat + rnd.uniform(-0.01, 0.01), lng=lng + rnd.uniform(-0.01, 0.01), telefono="381 000-5555", horario=horario,
                    referente="Referente ficticio/a", servicios="Datos de prueba", zonas=[dep, "Capital"] if tipo == "cuidador" else None,
                    formacion="Curso de cuidadores domiciliarios (ficticio)" if tipo == "cuidador" else None, origen="relevamiento", creado_por=U["direccion"].id)
        db.add(r)
        recursos.append(r)
    db.flush()
    contactos = []
    for nombre, cargo, inst, cat, rec in (
        ("Lic. Ficticia Andrea", "Trabajadora social", "CAPS Barrio Norte (ficticio)", "salud", recursos[3]),
        ("Ficticio Martín", "Responsable del área social", "Comuna de Alderetes (ficticia)", "municipio", recursos[4]),
        ("Of. Ficticio Gustavo", "Oficial de guardia", "Comisaría de Famaillá (ficticia)", "seguridad", recursos[5]),
        ("Dra. Ficticia Laura", "Defensora", "Defensoría ficticia de Concepción", "justicia", recursos[6]),
        ("Ficticia Silvia", "Coordinadora", "Centro de Día «Los Aromos» (ficticio)", "organizacion_social", recursos[0]),
    ):
        k = Contacto(nombre=nombre, nombre_norm=normalizar(nombre), cargo=cargo, institucion=inst, institucion_norm=normalizar(inst), categoria=cat, recurso_id=rec.id,
                     localidad=rec.localidad, departamento=rec.departamento, telefono="381 000-7777", whatsapp="3810007777", temas="Contacto de prueba",
                     origen="articulacion", creado_por=U["direccion"].id)
        db.add(k)
        contactos.append(k)
    db.flush()
    for c, k, dias in ((nuevos[12], contactos[0], 10), (nuevos[13], contactos[1], 40), (nuevos[15], contactos[2], 70), (casos[2], contactos[3], 25)):
        db.add(Articulacion(caso_id=c.id, contacto_id=k.id, recurso_id=k.recurso_id, fecha=max(c.fecha_ingreso, hoy - timedelta(days=dias)), motivo="Articulación de prueba (ficticia)",
                            resultado="Se acordó seguimiento conjunto (ficticio)", usuario_id=U["tecnica1"].id))

    # ------------------------------------------------------------ Mesa de Entrada y expedientes
    remitentes = ["Juzgado ficticio de Familia", "Hospital ficticio Padilla", "Comuna ficticia", "Fiscalía ficticia", "Particular", "Defensoría ficticia"]
    todas = personas + nuevas
    for k in range(12):
        dias = rnd.randint(0, 200) if k > 2 else k
        f = _dt(_habil(hoy - timedelta(days=dias)), 9, 30)
        p = rnd.choice(todas)
        vinc = k > 2 and rnd.random() < 0.8
        caso = next((c for c in casos + nuevos if c.persona_id == p.id), None)
        db.add(Ingreso(
            numero=numero_ingreso(db), fecha_ingreso=f, remitente=rnd.choice(remitentes), tipo_documental_id=tipos[rnd.choice(["Oficio", "Nota", "Elevación"])].id,
            asunto=rnd.choice(["Solicita informe de situación", "Remite denuncia", "Pide intervención urgente", "Comunica alta hospitalaria"]) + " (ficticio)",
            folios=rnd.randint(1, 8), persona_mencionada=f"{p.apellidos.title()} {p.nombres}", documento_mencionado=p.numero_documento,
            persona_id=p.id if vinc else None, caso_id=caso.id if vinc and caso else None, vinculado_por=U["mesa"].id if vinc else None,
            vinculado_en=f + timedelta(hours=rnd.randint(1, 50)) if vinc else None, creado_por=U["mesa"].id,
        ))
    expedientes = []
    for p, c, numero in ((nuevas[3], nuevos[3], "EXP-4521/310-D-2026"), (nuevas[8], nuevos[8], "J-9876/2026")):
        e = Expediente(numero=numero, tipo="judicial" if numero.startswith("J") else "administrativo", organismo="Organismo ficticio",
                       caratula=f"{p.apellidos.title()} {p.nombres} s/ protección (ficticio)", persona_id=p.id, caso_id=c.id, creado_por=U["mesa"].id)
        db.add(e)
        expedientes.append(e)
    db.flush()

    # ------------------------------------------------------------ carpetas en papel y pases
    registro = areas[REGISTRO]
    tiene = {nuevas[7].id: U["tecnica1"], nuevas[8].id: U["tecnico2"], personas[0].id: U["tecnica1"]}
    for p in todas:
        u = tiene.get(p.id)
        db.add(UbicacionFisica(persona_id=p.id, area_id=u.area_id if u else registro.id, usuario_id=u.id if u else None, actualizado_por=U["registro"].id))
    for e in expedientes:
        db.add(UbicacionFisica(expediente_id=e.id, area_id=registro.id, actualizado_por=U["registro"].id))
    for p, u in tiene.items():
        ini = _dt(hoy - timedelta(days=rnd.randint(3, 20)), 10)
        db.add(Pase(tipo="pedido", persona_id=p, desde_area_id=registro.id, hacia_area_id=u.area_id, hacia_usuario_id=u.id, motivo="Visita domiciliaria (ficticio)",
                    estado="hecho", iniciado_por=u.id, iniciado_en=ini, resuelto_por=U["registro"].id, resuelto_en=ini + timedelta(hours=rnd.randint(1, 30))))
    # Pendientes: un pedido para que Registro entregue y una devolución para que Registro reciba.
    db.add(Pase(tipo="pedido", persona_id=nuevas[9].id, desde_area_id=registro.id, hacia_area_id=U["tecnico2"].area_id, hacia_usuario_id=U["tecnico2"].id,
                motivo="Necesito revisar antecedentes (ficticio)", estado="pendiente", iniciado_por=U["tecnico2"].id, iniciado_en=_dt(hoy, 8, 40)))
    db.add(Pase(tipo="pedido", persona_id=nuevas[11].id, desde_area_id=registro.id, hacia_area_id=U["tecnica3"].area_id, hacia_usuario_id=U["tecnica3"].id,
                motivo="Audiencia del jueves (ficticio)", estado="pendiente", iniciado_por=U["tecnica3"].id, iniciado_en=_dt(hoy - timedelta(days=3), 11)))

    # ------------------------------------------------------------ negativas de ANSES
    db.add(Constancia(persona_id=nuevas[0].id, tipo="negativa_anses", fecha_emision=hoy - timedelta(days=20), vence=hoy + timedelta(days=40), resultado="sin_registros",
                      detalle="Constancia de prueba (ficticia)", origen="manual", usuario_id=U["tecnica1"].id))
    db.add(Constancia(persona_id=nuevas[3].id, tipo="negativa_anses", fecha_emision=hoy - timedelta(days=150), vence=hoy - timedelta(days=60), resultado="sin_registros",
                      detalle="Constancia de prueba vencida (ficticia)", origen="manual", usuario_id=U["tecnica1"].id))

    # ------------------------------------------------------------ informe en borrador
    plantilla = db.execute(select(PlantillaInforme).where(PlantillaInforme.activo).order_by(PlantillaInforme.orden, PlantillaInforme.id)).scalars().first()
    if plantilla is not None:
        from .config import get_settings
        from .informes import datos_iniciales, limpiar_html, valores_disponibles

        caso = casos[0]
        persona = personas[0]
        e = plantilla.estructura
        db.add(Informe(
            grupo_id=uuid.uuid4(), version=1, persona_id=persona.id, caso_id=caso.id, plantilla_id=plantilla.id, tipo_documental_id=plantilla.tipo_documental_id,
            titulo=(e.get("titulo") or plantilla.nombre)[:300], lugar=get_settings().lugar_informes, fecha=hoy,
            destinatario=(e.get("destinatario_inicial") or "") if e.get("destinatario") else None,
            datos=datos_iniciales(e.get("datos", []), valores_disponibles(db, persona, caso, hoy)),
            secciones=[{"titulo": s.get("titulo", ""), "html": limpiar_html(s.get("texto", ""))} for s in e.get("secciones", [])],
            firmantes=[{"nombre": U["tecnica1"].nombre_completo, "cargo": "Técnica"}], estado="borrador", creado_por=U["tecnica1"].id, actualizado_por=U["tecnica1"].id,
        ))

    # ------------------------------------------------------------ novedades
    nov = [
        ("Circular 12/2026: nuevo circuito de pases de carpetas (ficticia)",
         "<p>A partir del lunes, los pedidos de carpetas se hacen desde SULAM. Registro confirma la entrega en el sistema.</p>", None, U["directora"], True, True, 6),
        ("Reunión de equipo de Admisión (ficticia)", "<p>El jueves a las 10 h, en la sala de reuniones. Traer casos sin movimiento.</p>",
         areas[ADMISION].id, U["jefa_admision"], True, False, 2),
        ("Feria de salud en Plaza Independencia (ficticia)", "<p>Necesitamos dos voluntarios para la mesa de información del sábado.</p>",
         areas[PROMOCION].id, U["jefe_promocion"], False, False, 9),
    ]
    for titulo, cuerpo, area_id, autor, confirma, fijada, dias in nov:
        n = Novedad(titulo=titulo, cuerpo=cuerpo, area_id=area_id, requiere_confirmacion=confirma, fijada=fijada, autor_id=autor.id, publicada_en=_dt(hoy - timedelta(days=dias), 9))
        db.add(n)
        db.flush()
        if area_id is None:
            for clave in ("direccion", "jefa_admision", "jefe_promocion", "carga", "mesa"):
                db.add(NovedadLectura(novedad_id=n.id, usuario_id=U[clave].id, confirmada_en=_dt(hoy - timedelta(days=dias - 1), 10)))

    # ------------------------------------------------------------ agenda: salidas, visitas y reuniones
    _agenda(db, U, tecnicos_area, casos + nuevos, areas, rnd, hoy)

    # ------------------------------------------------------------ personal: reloj, pedidos y quién no está hoy
    _personal(db, U, areas, almacen, rnd, hoy)


def _agenda(db: Session, U: dict[str, Usuario], tecnicos_area: dict[str, list[Usuario]], casos: list[Caso], areas: dict[str, Area], rnd: random.Random, hoy: date) -> None:
    """Actividades ficticias: algunas ya hechas (con su resultado en el caso), una sin resultado, otras de hoy y próximas."""
    por_area = {a.id: n for n, a in areas.items()}
    for area_nombre, tecnicos in tecnicos_area.items():
        del_area = [c for c in casos if por_area.get(c.area_id) == area_nombre] or casos
        for k, u in enumerate(tecnicos):
            c1, c2, c3 = rnd.sample(del_area, 3) if len(del_area) >= 3 else (del_area[0],) * 3

            def evento(dias, h, tipo, titulo, caso=None, estado="programado", resultado=None, otros=(), lugar=None, dur=1):
                e = EventoAgenda(
                    tipo=tipo, titulo=titulo, inicio=_dt(_habil(hoy + timedelta(days=dias)), h), fin=_dt(_habil(hoy + timedelta(days=dias)), h + dur),
                    lugar=lugar, area_id=u.area_id, persona_id=caso.persona_id if caso else None, caso_id=caso.id if caso else None,
                    estado=estado, resultado=resultado, creado_por=u.id,
                )
                if estado != "programado":
                    e.resuelto_por, e.resuelto_en = u.id, _dt(_habil(hoy + timedelta(days=dias)), h + dur + 1)
                e.participantes = [ParticipanteAgenda(usuario_id=x.id) for x in (u, *otros)]
                db.add(e)
                db.flush()
                if caso and estado in ("realizado", "no_realizado"):
                    db.add(CasoEvolucion(caso_id=caso.id, texto=f"{'Visita domiciliaria realizada' if estado == 'realizado' else 'Visita domiciliaria no realizada'}: {resultado} (ficticio)", fecha=e.inicio.date(), autor_id=u.id, usuario_id=u.id))

            colega = tecnicos[(k + 1) % len(tecnicos)] if len(tecnicos) > 1 else None
            evento(-9 - k, 10, "visita", "Visita domiciliaria", c1, "realizado", "Se la encontró bien; se acordó seguimiento telefónico.", lugar="Domicilio")
            evento(-5, 9, "visita", "Visita domiciliaria", c2, "no_realizado", "No había nadie en el domicilio; se dejó aviso.", lugar="Domicilio")
            evento(-2, 11, "entrevista", "Entrevista con familiar", c3, lugar="Oficina")  # pasó y falta el resultado
            evento(0, 9 + (k % 3), "salida", "Salida a domicilio", c1, otros=[colega] if colega else (), lugar="Zona sur")
            evento(2 + k % 3, 10, "reunion", "Reunión de equipo", otros=[colega] if colega else (), lugar="Sala de reuniones")
            evento(6 + k % 4, 14, "audiencia", "Audiencia en juzgado", c2, lugar="Tribunales")


def _con_grupos(codigos: list[str]) -> list[str]:
    salida: list[str] = []
    for c in codigos:
        for x in (c.split(".")[0], c):
            if x not in salida:
                salida.append(x)
    return salida


def _personal(db: Session, U: dict[str, Usuario], areas: dict[str, Area], almacen, rnd: random.Random, hoy: date) -> None:
    from .asistencia import leer_reloj

    inicio = f"{hoy.year - 1}-01-01"
    turno = {str(d): ["08:00", "14:00"] for d in range(5)}
    extra = [
        ("Ficticia Ordenanza Marta", ADMINISTRATIVA, "Maestranza", "950", {str(d): ["07:00", "13:00"] for d in range(5)}, True),
        ("Ficticio Chofer Raúl", DIRECCION, "Chofer", "951", {str(d): ["09:00", "15:00"] for d in range(5)}, False),
    ]
    for nombre, area, cargo, reloj, semana, conf in extra:
        a = Agente(nombre=nombre, area_id=areas[area].id, cargo=cargo, id_reloj=reloj, boleta=f"D-{reloj}", periodos=[{"desde": inicio, "hasta": None}])
        db.add(a)
        db.flush()
        db.add(Horario(agente_id=a.id, vigente_desde=date.fromisoformat(inicio), semana=semana, confirmado=conf,
                       fuente="Horario ficticio de demostración" if conf else "Pendiente de nota de la jefatura (ficticio)"))
    db.flush()
    agentes = {a.usuario_id: a for a in db.execute(select(Agente)).scalars() if a.usuario_id}
    todos = list(db.execute(select(Agente).where(Agente.id_reloj.is_not(None)).order_by(Agente.id_reloj)).scalars())
    horarios = {h.agente_id: h.semana for h in db.execute(select(Horario)).scalars()}
    A = {k: agentes[u.id] for k, u in U.items() if u.id in agentes}

    # Situaciones ficticias para que haya algo que revisar.
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    semanas = [lunes_actual - timedelta(weeks=k) for k in (3, 2, 1)]
    especiales: dict[tuple[int, date], tuple[str | None, str | None]] = {}
    d1, d2, d3 = semanas[2] + timedelta(days=1), semanas[2] + timedelta(days=3), semanas[1] + timedelta(days=2)
    especiales[(A["tecnica1"].id, d1)] = ("08:27:00", "14:01:00")  # tardanza
    especiales[(A["tecnico2"].id, d2)] = ("07:56:00", None)  # sin salida
    especiales[(A["carga"].id, d3)] = (None, None)  # no marcó
    especiales[(A["mesa"].id, d1)] = ("08:08:00", "14:12:00")  # tarde, recuperado
    especiales[(A["jefa_cuidados"].id, d2)] = ("07:55:00", "13:15:00")  # salida anticipada
    especiales[(A["adminarea"].id, d3)] = (None, None)  # ausente con justificativo CE

    for lunes in semanas:
        viernes = lunes + timedelta(days=4)
        filas = [
            f"<table><tr><td>{lunes.isoformat()} 00:00:00 - {viernes.isoformat()} 23:59:59</td></tr>",
            "<tr><th>ID de Persona</th><th>Nombre</th><th>Fecha</th><th>Primera Entrada</th><th>Última Salida</th></tr>",
        ]
        for a in todos:
            semana = horarios.get(a.id, turno)
            for k in range(5):
                dia = lunes + timedelta(days=k)
                t = semana.get(str(k))
                if not t:
                    continue
                if (a.id, dia) in especiales:
                    ent, sal = especiales[(a.id, dia)]
                    if ent is None and sal is None:
                        continue
                else:
                    h0, m0 = map(int, t[0].split(":"))
                    h1, m1 = map(int, t[1].split(":"))
                    e = datetime.combine(dia, time(h0, m0)) - timedelta(minutes=rnd.randint(0, 14))
                    s = datetime.combine(dia, time(h1, m1)) + timedelta(minutes=rnd.randint(0, 12))
                    ent, sal = e.strftime("%H:%M:%S"), s.strftime("%H:%M:%S")
                filas.append(f"<tr><td>{a.id_reloj}</td><td>{a.nombre}</td><td>{dia.isoformat()}</td><td>{ent or '-'}</td><td>{sal or '-'}</td></tr>")
        filas.append("</table>")
        contenido = "\n".join(filas).encode("utf-8")
        leido = leer_reloj(contenido.decode("utf-8"))
        g = almacen.guardar(io.BytesIO(contenido))
        identidades = list({(r["id_reloj"], r["nombre"]): {"id_reloj": r["id_reloj"], "nombre": r["nombre"]} for r in leido["registros"]}.values())
        imp = RelojImportacion(
            nombre_archivo=f"reloj-ficticio-{lunes.isoformat()}.xls", sha256=hashlib.sha256(contenido).hexdigest(), almacenamiento=almacen.nombre, clave=g.clave,
            desde=lunes, hasta=viernes, filas=len(leido["registros"]), errores=leido["errores"], avisos=leido["avisos"], identidades=identidades,
            incorporada=True, usuario_id=U["personal"].id,
        )
        db.add(imp)
        db.flush()
        por_reloj = {a.id_reloj: a for a in todos}
        for r in leido["registros"]:
            db.add(Marcacion(importacion_id=imp.id, agente_id=por_reloj[r["id_reloj"]].id, dia=date.fromisoformat(r["dia"]), entrada=r["entrada"], salida=r["salida"], fila=r["fila"]))
    db.flush()

    # Justificativo del ausente y revisión de la salida anticipada.
    db.add(Justificativo(agente_id=A["adminarea"].id, codigo="CE", desde=d3, hasta=d3, estado="aprobado", referencia="Certificado de prueba (ficticio)",
                         notas="Cargado por Personal", adjuntos=[], usuario_id=U["personal"].id))
    db.flush()
    from .routers.personal import _informe

    fila = next(f for f in _informe(db, d2, d2, A["jefa_cuidados"].id) if f["dia"] == d2.isoformat())
    db.add(RevisionJornada(agente_id=A["jefa_cuidados"].id, dia=d2, huella=fila["huella"], decision="sin_descuento", minutos=0,
                           fundamento="Salida autorizada por la Dirección para una reunión externa (ficticio).", usuario_id=U["personal"].id))

    # Pedidos en distintos estados.
    ahora = datetime.now().astimezone()

    def pedido(clave, tipo, desde, hasta, estado, *, clase=None, lugar=None, motivo=None, nueva=None, decide=None, respuesta=None, registra=False, horas=None):
        s = SolicitudPersonal(
            agente_id=A[clave].id, tipo=tipo, clase=clase, desde=desde, hasta=hasta, lugar=lugar, motivo=motivo, adjuntos=[], estado=estado,
            nueva_entrada=nueva[0] if nueva else None, nueva_salida=nueva[1] if nueva else None, hora_desde=horas[0] if horas else None,
            hora_hasta=horas[1] if horas else None, pedido_por=U[clave].id, pedido_en=ahora - timedelta(days=2),
        )
        if decide:
            s.decidido_por, s.decidido_en, s.respuesta = U[decide].id, ahora - timedelta(days=1), respuesta
        if registra:
            s.registrado_por, s.registrado_en = U["personal"].id, ahora - timedelta(hours=20)
        db.add(s)
        db.flush()
        if registra:
            db.add(Justificativo(agente_id=s.agente_id, codigo="CAMBIO" if tipo == "cambio_horario" else "LICENCIA", desde=desde, hasta=hasta, estado="aprobado",
                                 hora_desde=s.hora_desde, hora_hasta=s.hora_hasta, excepcion_desde=s.nueva_entrada, excepcion_hasta=s.nueva_salida,
                                 referencia=f"Pedido N° {s.id}", adjuntos=[], solicitud_id=s.id, usuario_id=U["personal"].id))
        return s

    pedido("tecnica1", "licencia", hoy + timedelta(days=14), hoy + timedelta(days=24), "pendiente", clase="anual", motivo="Vacaciones de invierno (ficticio)")
    pedido("tecnico2", "comision", hoy + timedelta(days=3), hoy + timedelta(days=3), "pendiente", lugar="Comuna de Alderetes, relevamiento (ficticio)")
    pedido("tecnica3", "cambio_horario", hoy + timedelta(days=7), hoy + timedelta(days=11), "pendiente", nueva=("10:00", "16:00"), motivo="Cursada (ficticio)")
    pedido("carga", "licencia", hoy + timedelta(days=5), hoy + timedelta(days=6), "aprobada", clase="particular", decide="jefa_admision")
    pedido("adminarea", "licencia", hoy - timedelta(days=2), hoy + timedelta(days=4), "registrada", clase="familiar", decide="jefa_cuidados", registra=True,
           motivo="Atención de familiar (ficticio)")
    pedido("tecnico4", "comision", hoy, hoy, "registrada", lugar="Capacitación en el Ministerio (ficticio)", decide="jefa_cuidados", registra=True)
    pedido("mesa", "cambio_horario", hoy - timedelta(days=10), hoy - timedelta(days=5), "rechazada", nueva=("09:00", "15:00"), decide="direccion",
           respuesta="No se puede cubrir la Mesa de Entrada en ese horario (ficticio).")
    pedido("registro", "licencia", hoy + timedelta(days=1), hoy + timedelta(days=2), "pendiente", clase="enfermedad",
           motivo="Control médico (ficticio, reservado)")

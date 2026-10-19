"""Datos iniciales (catálogos y roles) y datos de demostración ficticios."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Area, Rol, RolPermiso, TipoDocumental, TipoVinculo, Usuario
from .security import hash_password

# Organigrama vigente (2011). La propuesta de modificación no está aprobada.
AREAS = [
    "Dirección de Adultos Mayores",
    "Departamento Promoción Integral de Derechos",
    "División Participación y Sensibilización Ciudadana",
    "División Cuidados y Promoción de Autonomía",
    "Departamento Admisión de Casos y Recepción de Denuncias",
    "Departamento Planificación y Estadística",
    "División Asistencia Administrativa",
    # Guarda las carpetas en papel (nombre a confirmar con la Dirección).
    "Oficina de Registro",
]

# Documento de diseño, §6.2. Son administrables.
TIPOS_DOCUMENTALES = [
    "DNI (frente y dorso)",
    "Carátula",
    "Registro de demanda",
    "Informe socioambiental",
    "Informe social",
    "Informe de seguimiento",
    "Nota",
    "Certificación negativa ANSES",
    "Memorándum",
    "Acta de acción o intervención",
    "Elevación",
    "Oficio",
    "Expediente administrativo",
    "Documentación de subsidios",
    "Actualización de datos",
    "Otros documentos",
]

# Propuesta provisoria; a validar en el relevamiento.
TIPOS_VINCULO = [
    "Familiar",
    "Referente afectivo",
    "Conviviente",
    "Denunciante",
    "Representante legal o apoyo",
    "Institución",
    "Otro",
]

T, AR, AS, P = "todos", "area", "asignados", "propios"

# Roles iniciales (documento de diseño §5.3). La matriz definitiva se define
# institucionalmente; estos valores son editables desde Administración.
ROLES: dict[str, dict] = {
    "Dirección y Administración del Sistema": {
        "inicio": "direccion",
        "descripcion": "Gestión de permisos, plantillas, configuraciones y operaciones institucionales autorizadas.",
        "permisos": [
            ("agenda", "consultar", T), ("agenda", "crear", T), ("agenda", "modificar", T),
            ("participacion", "consultar", T), ("participacion", "crear", T), ("participacion", "modificar", T),
            ("participacion", "descargar", T), ("participacion", "administrar", T),
            ("personal", "consultar", T), ("personal", "administrar", T), ("personal", "aprobar", T), ("estadisticas", "consultar", T),
            ("novedades", "publicar", T),
            ("plantillas", "modificar", T),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("subsidios", "consultar", T), ("subsidios", "crear", T), ("subsidios", "modificar", T), ("subsidios", "administrar", T),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", T),
            ("personas", "administrar", T),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", T), ("casos", "derivar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T), ("expedientes", "modificar", T),
            ("mesa_entrada", "consultar", T), ("mesa_entrada", "crear", T), ("mesa_entrada", "modificar", T),
            ("documentos", "consultar", T), ("documentos", "crear", T), ("documentos", "descargar", T),
            ("documentos", "modificar", T), ("documentos", "administrar", T),
            ("auditoria", "consultar", T),
            ("administracion", "administrar", T),
        ],
    },
    "Directora": {
        "inicio": "direccion",
        "descripcion": "Conducción de la Dirección: ve todos los casos y la auditoría, y puede derivar y asignar. No administra usuarios ni permisos.",
        "permisos": [
            ("agenda", "consultar", T), ("agenda", "crear", T), ("agenda", "modificar", T),
            ("participacion", "consultar", T), ("participacion", "descargar", T),
            ("personal", "consultar", T), ("personal", "aprobar", T), ("estadisticas", "consultar", T),
            ("novedades", "publicar", T),
            ("plantillas", "modificar", T),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("subsidios", "consultar", T), ("subsidios", "crear", T), ("subsidios", "modificar", T), ("subsidios", "administrar", T),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", T),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", T), ("casos", "derivar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T), ("expedientes", "modificar", T),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", T), ("documentos", "descargar", T),
            ("documentos", "modificar", T),
            ("auditoria", "consultar", T),
        ],
    },
    "Jefe/a de departamento": {
        "inicio": "jefatura",
        "descripcion": "Conduce un departamento que maneja casos (Admisión o Promoción, según el área del usuario): abre carátulas y asigna técnicos en su área.",
        "permisos": [
            ("agenda", "consultar", AR), ("agenda", "crear", AR), ("agenda", "modificar", AR),
            ("personal", "aprobar", AR), ("estadisticas", "consultar", AR),
            ("novedades", "publicar", AR),
            ("plantillas", "modificar", AR),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("subsidios", "consultar", T), ("subsidios", "crear", T), ("subsidios", "modificar", T),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", AR),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", AR), ("casos", "derivar", AR),
            ("expedientes", "consultar", T), ("expedientes", "crear", AR), ("expedientes", "modificar", AR),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", AR), ("documentos", "descargar", AR),
            ("documentos", "modificar", AR),
        ],
    },
    "Jefe/a de división": {
        "inicio": "jefatura",
        "descripcion": "Conduce una división (Participación y Sensibilización Ciudadana, Cuidados y Promoción de Autonomía) o cumple esa función en un departamento. Mismos permisos que un jefe de departamento, sobre el área del usuario.",
        "permisos": [
            ("agenda", "consultar", AR), ("agenda", "crear", AR), ("agenda", "modificar", AR),
            ("personal", "aprobar", AR), ("estadisticas", "consultar", AR),
            ("novedades", "publicar", AR),
            ("plantillas", "modificar", AR),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("subsidios", "consultar", T), ("subsidios", "crear", T), ("subsidios", "modificar", T),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", AR),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", AR), ("casos", "derivar", AR),
            ("expedientes", "consultar", T), ("expedientes", "crear", AR), ("expedientes", "modificar", AR),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", AR), ("documentos", "descargar", AR),
            ("documentos", "modificar", AR),
        ],
    },
    "Participación y Sensibilización": {
        "inicio": "participacion",
        "descripcion": "Integrantes de la División Participación y Sensibilización Ciudadana: planifican la semana en la agenda, arman campañas con su material, registran asistentes y fotos de los eventos, exportan el brief para Comunicación, definen los tipos de evento y construyen el mapa de recursos. Se suma a otro rol (por ejemplo, el de jefatura o el de técnico).",
        "permisos": [
            ("agenda", "consultar", AR), ("agenda", "crear", AR), ("agenda", "modificar", AR),
            ("participacion", "consultar", AR), ("participacion", "crear", AR), ("participacion", "modificar", AR),
            ("participacion", "descargar", AR), ("participacion", "administrar", AR),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("estadisticas", "consultar", AR),
        ],
    },
    "Carga de Datos": {
        "inicio": "carga",
        "descripcion": "Acceso transversal a los legajos y herramientas de incorporación y actualización de información.",
        "permisos": [
            ("agenda", "consultar", P), ("agenda", "crear", P), ("agenda", "modificar", P),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", T),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", T),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", T),
            # "modificar" permite transcribir carátulas, registros de demanda y evoluciones en papel.
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T), ("expedientes", "modificar", T),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", T), ("documentos", "descargar", T),
            ("documentos", "modificar", T),
        ],
    },
    "Técnico": {
        "inicio": "tecnico",
        "descripcion": "Consulta general de legajos, con tablero centrado en sus casos asignados.",
        "permisos": [
            ("agenda", "consultar", AR), ("agenda", "crear", AR), ("agenda", "modificar", P),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", P),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", P),
            ("subsidios", "consultar", T), ("subsidios", "crear", T), ("subsidios", "modificar", P),
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", AS),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", AS),
            ("expedientes", "consultar", T), ("expedientes", "crear", AS),
            ("documentos", "consultar", T), ("documentos", "crear", AS), ("documentos", "descargar", T),
            ("documentos", "modificar", AS),
        ],
    },
    "Personal": {
        "inicio": "personal",
        "descripcion": "Encargada/o de personal: asistencias, horarios, justificativos, licencias y comisiones.",
        "permisos": [
            ("agenda", "consultar", P), ("agenda", "crear", P), ("agenda", "modificar", P),
            ("personal", "consultar", T), ("personal", "administrar", T),
            ("recursos", "consultar", T),
            ("residencias", "consultar", T),
        ],
    },
    "Mesa de Entrada": {
        "inicio": "mesa",
        "descripcion": "Registro de ingresos, números de expedientes y movimientos administrativos.",
        "permisos": [
            ("agenda", "consultar", P), ("agenda", "crear", P), ("agenda", "modificar", P),
            ("recursos", "consultar", T),
            ("residencias", "consultar", T),
            ("mesa_entrada", "consultar", T), ("mesa_entrada", "crear", T), ("mesa_entrada", "modificar", T),
            ("personas", "consultar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T),
            ("documentos", "consultar", P), ("documentos", "crear", T), ("documentos", "descargar", P),
        ],
    },
    "Administrativo de Área": {
        "inicio": "administrativo_area",
        "descripcion": "Funciones específicas del área, como documentación y gestión administrativa.",
        "permisos": [
            ("agenda", "consultar", AR), ("agenda", "crear", AR), ("agenda", "modificar", AR),
            ("recursos", "consultar", T), ("recursos", "crear", T), ("recursos", "modificar", P),
            ("residencias", "consultar", T), ("residencias", "crear", T), ("residencias", "modificar", P),
            ("subsidios", "consultar", AR), ("subsidios", "crear", AR), ("subsidios", "modificar", AR),
            ("personas", "consultar", AR),
            ("casos", "consultar", AR),
            ("expedientes", "consultar", AR), ("expedientes", "crear", AR),
            ("documentos", "consultar", AR), ("documentos", "crear", AR), ("documentos", "descargar", AR),
        ],
    },
}


def _asegurar(db: Session, modelo, nombres: list[str]) -> None:
    existentes = {x.nombre for x in db.execute(select(modelo)).scalars()}
    for i, nombre in enumerate(nombres):
        if nombre not in existentes:
            obj = modelo(nombre=nombre)
            if modelo is TipoDocumental:
                obj.orden = i
                # El DNI se pide en todo caso abierto; el resto lo decide la Dirección desde Administración.
                obj.requerido_en_caso_abierto = nombre.startswith("DNI")
            db.add(obj)


# Todos los roles pueden buscar antecedentes (nombre, documento, fecha de carátula y responsable, nada más).
for _d in ROLES.values():
    _d["permisos"].append(("antecedentes", "consultar", T))
    _d["permisos"].append(("chat", "usar", T))  # el chat interno es para todos los roles


def inicializar_catalogos(db: Session) -> None:
    """Idempotente: agrega lo que falte sin modificar lo existente."""
    _asegurar(db, Area, AREAS)
    _asegurar(db, TipoDocumental, TIPOS_DOCUMENTALES)
    _asegurar(db, TipoVinculo, TIPOS_VINCULO)
    existentes = {r.nombre for r in db.execute(select(Rol)).scalars()}
    for nombre, d in ROLES.items():
        if nombre in existentes:
            continue
        rol = Rol(nombre=nombre, descripcion=d["descripcion"], inicio=d.get("inicio"))
        rol.permisos = [RolPermiso(modulo=m, accion=a, alcance=al) for m, a, al in d["permisos"]]
        db.add(rol)
    db.flush()
    _permisos_de_modulos_nuevos(db, existentes)
    from .informes import crear_plantillas_iniciales

    crear_plantillas_iniciales(db)
    db.flush()


# Módulos agregados después de la primera instalación: sus permisos se suman UNA vez a los roles ya existentes
# (si después alguien los quita desde Administración, no se vuelven a poner).
MODULOS_NUEVOS = ("agenda", "participacion", "residencias", "subsidios", "antecedentes", "chat")


def _permisos_de_modulos_nuevos(db: Session, roles_previos: set[str]) -> None:
    from .models import Ajuste

    for modulo in MODULOS_NUEVOS:
        clave = f"permisos_iniciales_{modulo}"
        if db.get(Ajuste, clave) is not None:
            continue
        for rol in db.execute(select(Rol)).scalars():
            d = ROLES.get(rol.nombre)
            if d is None or rol.nombre not in roles_previos:
                continue  # los roles nuevos ya vienen completos; los creados a mano no se tocan
            if any(p.modulo == modulo for p in rol.permisos):
                continue
            for m, a, al in d["permisos"]:
                if m == modulo:
                    rol.permisos.append(RolPermiso(modulo=m, accion=a, alcance=al))
        db.add(Ajuste(clave=clave, valor=True))
    db.flush()


def crear_administrador(db: Session, usuario: str, nombre: str, password: str) -> Usuario:
    rol = db.execute(select(Rol).where(Rol.nombre == "Dirección y Administración del Sistema")).scalar_one()
    area = db.execute(select(Area).where(Area.nombre == "Dirección de Adultos Mayores")).scalar_one_or_none()
    u = Usuario(
        usuario=usuario.lower(),
        nombre_completo=nombre,
        password_hash=hash_password(password),
        debe_cambiar_password=True,
        area_id=area.id if area else None,
    )
    u.roles = [rol]
    db.add(u)
    db.flush()
    return u


# ---------------------------------------------------------------------------
# Datos de demostración (FICTICIOS)
# ---------------------------------------------------------------------------

PASSWORD_DEMO = "demo-sulam-2026"

USUARIOS_DEMO = [
    ("direccion", "Dirección (demo)", "Dirección y Administración del Sistema", "Dirección de Adultos Mayores"),
    ("carga", "Carga de Datos (demo)", "Carga de Datos", "Departamento Admisión de Casos y Recepción de Denuncias"),
    ("tecnica1", "Técnica Uno (demo)", "Técnico", "Departamento Admisión de Casos y Recepción de Denuncias"),
    ("tecnico2", "Técnico Dos (demo)", "Técnico", "Departamento Promoción Integral de Derechos"),
    ("directora", "Directora (demo)", "Directora", "Dirección de Adultos Mayores"),
    ("jefa_admision", "Jefa de Admisión (demo)", "Jefe/a de departamento", "Departamento Admisión de Casos y Recepción de Denuncias"),
    ("jefe_promocion", "Jefe de Promoción (demo)", "Jefe/a de departamento", "Departamento Promoción Integral de Derechos"),
    ("jefa_cuidados", "Jefa de Cuidados (demo)", "Jefe/a de división", "División Cuidados y Promoción de Autonomía"),
    ("mesa", "Mesa de Entrada (demo)", "Mesa de Entrada", "División Asistencia Administrativa"),
    ("adminarea", "Administrativo de Área (demo)", "Administrativo de Área", "División Cuidados y Promoción de Autonomía"),
    ("personal", "Personal (demo)", "Personal", "División Asistencia Administrativa"),
    ("registro", "Oficina de Registro (demo)", "Administrativo de Área", "Oficina de Registro"),
    ("tecnica3", "Técnica Tres (demo)", "Técnico", "Departamento Admisión de Casos y Recepción de Denuncias"),
    ("tecnico4", "Técnico Cuatro (demo)", "Técnico", "División Cuidados y Promoción de Autonomía"),
    ("participacion", "Participación y Sensibilización (demo)", "Participación y Sensibilización", "División Participación y Sensibilización Ciudadana"),
]

PERSONAS_DEMO = [
    ("PÉREZ", "Rosa Elvira", "DNI", "4123456", date(1941, 3, 12), "San Miguel de Tucumán"),
    ("GÓMEZ", "Juan Carlos", "DNI", "5987321", date(1946, 7, 2), "Yerba Buena"),
    ("FERNÁNDEZ DE LÓPEZ", "María Inés", "LC", "3456789", date(1938, 11, 23), "Tafí Viejo"),
    ("SUÁREZ", "Ramón", None, None, date(1944, 1, 1), "Famaillá"),
    ("ACOSTA", "Delia del Valle", "DNI", "6234511", date(1950, 5, 30), "Banda del Río Salí"),
    ("RUIZ", "Héctor Hugo", "DNI", "7012844", date(1952, 9, 14), "Concepción"),
]


def fichas_personal_demo(db: Session, usuarios: dict) -> int:
    """Fichas de personal FICTICIAS para los usuarios de demostración (idempotente)."""
    from .models import Agente, Horario

    creadas = 0
    turno = {str(d): ["08:00", "14:00"] for d in range(5)}
    for n, (usuario, nombre, _rol, _area) in enumerate(USUARIOS_DEMO, start=1):
        u = usuarios.get(usuario)
        if u is None or db.execute(select(Agente).where(Agente.usuario_id == u.id)).first() is not None:
            continue
        a = Agente(
            nombre=nombre.replace(" (demo)", ""), usuario_id=u.id, area_id=u.area_id,
            cargo=_rol, id_reloj=str(900 + n), boleta=f"D-{n:03d}", periodos=[{"desde": f"{date.today().year - 1}-01-01", "hasta": None}],
        )
        db.add(a)
        db.flush()
        db.add(Horario(agente_id=a.id, vigente_desde=date(date.today().year - 1, 1, 1), semana=turno, confirmado=True, fuente="Horario ficticio de demostración"))
        creadas += 1
    return creadas

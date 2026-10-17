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
]

# Documento de diseño, §6.2. Son administrables.
TIPOS_DOCUMENTALES = [
    "Carátula",
    "Registro de demanda",
    "Informe socioambiental",
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
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", T),
            ("personas", "administrar", T),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", T), ("casos", "derivar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T), ("expedientes", "modificar", T),
            ("mesa_entrada", "consultar", T), ("mesa_entrada", "crear", T), ("mesa_entrada", "modificar", T),
            ("documentos", "consultar", T), ("documentos", "crear", T), ("documentos", "descargar", T),
            ("documentos", "modificar", T), ("documentos", "administrar", T),
            ("reservados", "consultar", T),
            ("auditoria", "consultar", T),
            ("administracion", "administrar", T),
        ],
    },
    "Directora": {
        "inicio": "direccion",
        "descripcion": "Conducción de la Dirección: ve todos los casos, la información reservada y la auditoría, y puede derivar y asignar. No administra usuarios ni permisos.",
        "permisos": [
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", T),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", T), ("casos", "derivar", T),
            ("expedientes", "consultar", T), ("expedientes", "crear", T), ("expedientes", "modificar", T),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", T), ("documentos", "descargar", T),
            ("documentos", "modificar", T),
            ("reservados", "consultar", T),
            ("auditoria", "consultar", T),
        ],
    },
    "Jefe/a de departamento": {
        "inicio": "jefatura",
        "descripcion": "Conduce un departamento que maneja casos (Admisión o Promoción, según el área del usuario): abre carátulas, asigna técnicos y ve la información reservada de su área.",
        "permisos": [
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", AR),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", AR), ("casos", "derivar", AR),
            ("expedientes", "consultar", T), ("expedientes", "crear", AR), ("expedientes", "modificar", AR),
            ("mesa_entrada", "consultar", T),
            ("documentos", "consultar", T), ("documentos", "crear", AR), ("documentos", "descargar", AR),
            ("documentos", "modificar", AR),
            ("reservados", "consultar", AR),
        ],
    },
    "Carga de Datos": {
        "inicio": "carga",
        "descripcion": "Acceso transversal a los legajos y herramientas de incorporación y actualización de información.",
        "permisos": [
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
            ("personas", "consultar", T), ("personas", "crear", T), ("personas", "modificar", AS),
            ("casos", "consultar", T), ("casos", "crear", T), ("casos", "modificar", AS),
            ("expedientes", "consultar", T), ("expedientes", "crear", AS),
            ("documentos", "consultar", T), ("documentos", "crear", AS), ("documentos", "descargar", T),
            ("documentos", "modificar", AS),
        ],
    },
    "Mesa de Entrada": {
        "inicio": "mesa",
        "descripcion": "Registro de ingresos, números de expedientes y movimientos administrativos.",
        "permisos": [
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
            db.add(obj)


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
    ("mesa", "Mesa de Entrada (demo)", "Mesa de Entrada", "División Asistencia Administrativa"),
    ("adminarea", "Administrativo de Área (demo)", "Administrativo de Área", "División Cuidados y Promoción de Autonomía"),
]

PERSONAS_DEMO = [
    ("PÉREZ", "Rosa Elvira", "DNI", "4123456", date(1941, 3, 12), "San Miguel de Tucumán"),
    ("GÓMEZ", "Juan Carlos", "DNI", "5987321", date(1946, 7, 2), "Yerba Buena"),
    ("FERNÁNDEZ DE LÓPEZ", "María Inés", "LC", "3456789", date(1938, 11, 23), "Tafí Viejo"),
    ("SUÁREZ", "Ramón", None, None, date(1944, 1, 1), "Famaillá"),
    ("ACOSTA", "Delia del Valle", "DNI", "6234511", date(1950, 5, 30), "Banda del Río Salí"),
    ("RUIZ", "Héctor Hugo", "DNI", "7012844", date(1952, 9, 14), "Concepción"),
]

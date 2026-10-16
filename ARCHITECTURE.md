# Arquitectura técnica · SULAM 0.1

## Enfoque

**Monolito modular**: una sola aplicación y una sola base de datos, con módulos separados por responsabilidad. Es lo más simple de operar para un equipo chico y permite separar módulos más adelante si hiciera falta.

```
Navegador (React)  ──HTTP/JSON──►  FastAPI (Python)  ──►  PostgreSQL 16
                                        │
                                        └──►  Almacenamiento de archivos (interfaz propia;
                                              implementación local en 0.1)
```

| Capa | Tecnología | Motivo |
|---|---|---|
| Interfaz | React 19 + TypeScript, compilado con esbuild | Tipado, sin dependencias pesadas; un solo `app.js` estático |
| API | FastAPI (Python 3.11+) | Validación automática, documentación OpenAPI, simple de mantener |
| Datos | PostgreSQL 16 + SQLAlchemy 2 + Alembic | Integridad referencial, transacciones, migraciones versionadas |
| Archivos | Módulo `storage.py` con implementación local | Independiente del proveedor (ver D-008) |

El backend sirve también la interfaz compilada (`frontend/dist`), así que en producción hay un único proceso y un único puerto.

## Estructura del repositorio

```
backend/
  sulam/
    config.py         Configuración por variables de entorno / .env
    db.py             Motor y sesiones de base de datos
    models.py         Modelo de datos (todas las tablas)
    permissions.py    Catálogo de permisos, alcances y reglas de información reservada
    security.py       Contraseñas (scrypt) y sesiones
    deps.py           Autenticación por petición y verificación CSRF
    audit.py          Registro de auditoría
    duplicates.py     Detección de posibles legajos duplicados
    numbering.py      Numeración correlativa (legajos, casos, ingresos)
    storage.py        Almacenamiento de archivos (interfaz + implementación local)
    backup.py         Respaldo y restauración
    serializers.py    Salida JSON, con ocultamiento de lo reservado
    schemas.py        Validación de datos de entrada
    seed.py           Catálogos y roles iniciales; datos de demostración
    cli.py            Comandos de administración
    main.py           Aplicación web
    routers/          Un archivo por módulo funcional
      auth.py  personas.py  casos.py  expedientes.py  ingresos.py
      documentos.py  general.py (buscador, catálogos, auditoría)  admin.py
  alembic/            Migraciones de la base
  tests/              Pruebas automatizadas (PostgreSQL real)
frontend/
  src/
    api.ts            Cliente HTTP y tipos
    comun.tsx         Navegación, sesión y componentes compartidos
    app.tsx           Acceso, estructura y rutas
    paginas/          Una página por módulo
```

## Modelo de datos

```
personas ─┬─< casos ─┬─< casos_asignaciones >── usuarios ─< usuarios_roles >── roles ─< roles_permisos
          │          └─< casos_estados_historial
          ├─< expedientes (opcionalmente ligados a un caso)
          ├─< personas_vinculadas >── tipos_vinculo
          ├─< documentos >── tipos_documentales
          └─< ingresos (Mesa de Entrada; persona_id puede ser NULL)
auditoria (solo agregado)     sesiones     areas     contadores
```

- **Identificador interno**: UUID en `personas.id`, independiente del documento. El número de legajo (`L-000123`) es el identificador visible.
- **Documento único**: índice único parcial sobre (tipo, número) para legajos activos (no unificados).
- **Unificación**: el legajo absorbido conserva sus datos y apunta al vigente (`unificada_en_id`); casos, expedientes, ingresos, documentos y vinculados se trasladan.
- **Nada se borra**: casos se cierran, documentos se dan de baja lógica, vinculados se desactivan.

## Seguridad

| Aspecto | Implementación |
|---|---|
| Contraseñas | scrypt (biblioteca estándar), sal aleatoria, mínimo 10 caracteres combinados |
| Sesiones | Token opaco en cookie `HttpOnly`, `SameSite=Strict`; en la base solo se guarda su SHA-256. Vencimiento absoluto (10 h) y por inactividad (60 min) |
| CSRF | Toda operación que modifica datos exige la cabecera `X-CSRF-Token` de la sesión |
| Fuerza bruta | Bloqueo temporal tras 5 intentos fallidos; mismo mensaje para usuario inexistente |
| Primer ingreso | Cambio de contraseña obligatorio antes de usar el sistema |
| Permisos | Verificados en el servidor en cada operación (el frontend solo oculta botones por comodidad) |
| Información reservada | Casos, documentos y vinculados reservados se devuelven sin contenido a quien no corresponde |
| Auditoría | Tabla de solo agregado: triggers en PostgreSQL impiden `UPDATE`, `DELETE` y `TRUNCATE` |
| Archivos | Se valida el tipo por contenido (no por extensión), tamaño máximo configurable, SHA-256 de cada archivo |
| Cabeceras | `nosniff`, `X-Frame-Options: DENY`, CSP restrictiva, `Cache-Control: no-store` en la API |

### Permisos: módulo × acción × alcance

`personas`, `casos`, `expedientes`, `mesa_entrada`, `documentos`, `reservados`, `auditoria`, `administracion` × `consultar`, `crear`, `modificar`, `descargar`, `derivar`, `administrar` × alcance:

| Alcance | Casos | Legajos / documentos / expedientes |
|---|---|---|
| `propios` | creados por el usuario | creados por el usuario |
| `asignados` | con asignación vigente al usuario | personas con un caso asignado al usuario |
| `area` | del área del usuario (o asignados) | personas con un caso del área |
| `todos` | todos | todos |

Un usuario puede tener varios roles; vale el alcance más amplio. Los roles se editan desde *Administración › Roles y permisos* y cada cambio queda auditado con el antes y el después.

## Almacenamiento de archivos

`storage.py` define la interfaz (`guardar`, `abrir`, `existe`, `verificar`, `eliminar`, `claves`). La implementación local guarda cada archivo con su SHA-256 como nombre (`ab/cd/abcd…`), lo que:

- detecta archivos idénticos sin ocupar espacio adicional;
- permite verificar integridad (`sulam verificar-archivos`);
- deja preparado el procedimiento de migración (`sulam migrar-archivos`): copia, verifica hash, actualiza referencias y **nunca** borra el origen.

Agregar otro proveedor (servidor institucional, S3 compatible, Google Drive) es escribir otra clase con la misma interfaz y registrarla en `almacenamiento_por_nombre`.

## Respaldo

`sulam respaldar` genera un único `.tar.gz` con el volcado de PostgreSQL (`pg_dump`, formato personalizado), los archivos y un manifiesto con el SHA-256 de cada componente. `sulam restaurar` verifica el manifiesto completo antes de tocar nada. La prueba automatizada `test_respaldo_y_restauracion` lo ejercita de punta a punta.

## Pruebas

`backend/tests` contiene pruebas contra PostgreSQL real, organizadas según los criterios de aceptación de la 0.1 (`test_aceptacion.py`) y los controles de seguridad (`test_seguridad.py`).

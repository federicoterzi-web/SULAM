# SULAM · Sistema Único de Legajos de Adultos Mayores

Sistema de la **Dirección de Adultos Mayores de Tucumán** para centralizar el legajo único de cada persona mayor atendida: identificación, casos, expedientes, ingresos de Mesa de Entrada, documentación digital y trazabilidad de cada intervención.

> **Estado: versión 0.1 (prototipo funcional).** Usar **solo con datos ficticios** hasta que se cumplan las condiciones de [DECISIONS.md › D-009](DECISIONS.md#d-009-datos-reales).

| Documento | Contenido |
|---|---|
| [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md) | Reglas funcionales implementadas |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura técnica y estructura del código |
| [DECISIONS.md](DECISIONS.md) | Decisiones de diseño y pendientes |
| [TASKS.md](TASKS.md) | Estado de implementación y próximos pasos |

---

## Opción A · Con Docker (recomendada)

Requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS o Linux).

```bash
git clone <url-del-repositorio> sulam
cd sulam
copy .env.example .env        # en Linux/macOS: cp .env.example .env
# editar .env y cambiar las dos contraseñas
docker compose up -d --build
```

Abrir **http://localhost:8000**. Con `SULAM_DATOS_DEMO=1` (valor por defecto del ejemplo) se cargan usuarios y legajos ficticios: ver [Usuarios de demostración](#usuarios-de-demostración).

Comandos útiles:

```bash
docker compose logs -f app                                   # ver el registro
docker compose exec app python -m sulam.cli respaldar        # generar respaldo
docker compose down                                          # detener (los datos se conservan)
```

## Opción B · Sin Docker (Windows)

1. Instalar:
   - **Python 3.12** o superior: <https://www.python.org/downloads/> (marcar *Add python.exe to PATH*).
   - **Node.js 20** o superior (LTS): <https://nodejs.org/>.
   - **PostgreSQL 16**: <https://www.postgresql.org/download/windows/>. Anotar la contraseña del usuario `postgres`.
2. Crear la base (en *SQL Shell (psql)* o pgAdmin):
   ```sql
   CREATE USER sulam WITH PASSWORD 'elegir-una-clave';
   CREATE DATABASE sulam OWNER sulam;
   ```
3. En una terminal (PowerShell), dentro de la carpeta del proyecto:
   ```powershell
   copy .env.example .env
   # editar .env: descomentar SULAM_DATABASE_URL con la clave elegida

   cd frontend
   npm install
   npm run build
   cd ..\backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e ".[dev]"
   python -m sulam.cli migrar
   python -m sulam.cli inicializar          # pide la contraseña del usuario admin
   python -m sulam.cli datos-demo           # opcional: datos ficticios
   python -m sulam.cli servidor
   ```
4. Abrir **http://localhost:8000**.

Para iniciarlo otro día: `cd backend`, `.venv\Scripts\activate`, `python -m sulam.cli servidor`.

Para los respaldos sin Docker, `pg_dump` y `pg_restore` deben estar en el PATH (vienen con PostgreSQL, en `C:\Program Files\PostgreSQL\16\bin`).

## Usuarios de demostración

Creados por `datos-demo`. Contraseña de todos: `demo-sulam-2026`.

| Usuario | Rol | Para probar |
|---|---|---|
| `direccion` | Dirección y Administración | Todo, incluida administración, auditoría y unificación |
| `carga` | Carga de Datos | Alta y actualización de legajos y documentos |
| `tecnica1` | Técnico (Admisión) | Tablero con casos asignados, incluido uno reservado |
| `tecnico2` | Técnico (Promoción) | Ver cómo se oculta el contenido de un caso reservado ajeno |
| `mesa` | Mesa de Entrada | Ingresos sin legajo y su vinculación posterior |
| `adminarea` | Administrativo de Área | Alcance limitado a su área |

Además existe `admin` con la contraseña definida al inicializar.

## Comandos de administración

```text
python -m sulam.cli migrar              Crea o actualiza las tablas
python -m sulam.cli inicializar         Catálogos, roles y primer administrador
python -m sulam.cli datos-demo          Datos ficticios (no disponible con SULAM_ENV=produccion)
python -m sulam.cli servidor            Inicia la aplicación (http://127.0.0.1:8000)
python -m sulam.cli respaldar           Respaldo completo (base + archivos) en un .tar.gz
python -m sulam.cli restaurar ARCHIVO --confirmar
python -m sulam.cli verificar-archivos  Comprueba la integridad (SHA-256) de cada documento
python -m sulam.cli migrar-archivos --raiz OTRA_CARPETA
```

## Desarrollo

```bash
# Pruebas (usan una base PostgreSQL aparte, que se vacía en cada prueba)
createdb -O sulam sulam_test
cd backend && pytest
# Variable opcional: SULAM_TEST_DATABASE_URL

# Frontend con recarga automática en http://localhost:5173 (con el backend corriendo en :8000)
cd frontend && npm run dev
npm run typecheck
```

La documentación interactiva de la API está en `http://localhost:8000/api/docs` (desactivada con `SULAM_ENV=produccion`).

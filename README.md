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

## Probar en casa (datos ficticios, paso a paso)

Sirve para recorrer SULAM desde todos los roles con datos **inventados**. No hace falta saber programar.

1. **Instalar Docker Desktop** desde <https://www.docker.com/products/docker-desktop/> (Windows o Mac). En Windows, si lo pide, aceptar la instalación de WSL y reiniciar.
2. **Abrir Docker Desktop** y esperar a que abajo a la izquierda diga *Engine running*.
3. **Bajar SULAM**: en la página del repositorio en GitHub, botón verde **Code → Download ZIP**. Descomprimir el ZIP (por ejemplo, en *Documentos*).
4. **Iniciar**: dentro de la carpeta, doble clic en **`probar-en-casa.bat`** (en Mac o Linux: `./probar-en-casa.sh` desde la terminal). La primera vez tarda entre 5 y 15 minutos porque descarga lo necesario; las siguientes, segundos.
5. Se abre **http://localhost:8000**. Entrar con cualquiera de los [usuarios de demostración](#usuarios-de-demostración); la contraseña de todos es `demo-sulam-2026`.

Para **apagarlo**: en la carpeta, clic derecho → *Abrir en Terminal* y escribir `docker compose down` (los datos quedan para la próxima). Para **empezar de cero** con datos nuevos: `docker compose down -v` y volver a abrir `probar-en-casa.bat`.

**Desde el celular, en la misma wifi**: en el archivo `.env` (se crea en la carpeta al iniciar) agregar `SULAM_URL_PUBLICA=http://IP-DE-LA-COMPUTADORA:8000`, y agregar la línea `SULAM_ESCUCHA=0.0.0.0` (el iniciador de prueba ya la pone), y volver a iniciar. La IP se ve en Windows con `ipconfig` (dirección IPv4).

Los datos de prueba incluyen unas 30 personas con casos repartidos en el año (indicadores, registros de demanda, evoluciones, reiteraciones), recursos y contactos en el mapa, ingresos de Mesa de Entrada, novedades, carpetas en papel con pases pendientes, negativas de ANSES (una vencida), un informe en borrador, tres semanas del reloj con incidencias, y pedidos de licencia, comisión y cambio de horario en todos los estados.

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

## Uso desde el celular

SULAM tiene una versión para celular en la misma dirección: al ingresar desde un teléfono se abre sola (también se puede elegir con *Versión para celular* en el menú). Permite buscar por DNI o apellido, ver legajos y casos, llamar a la persona o a sus referentes, agregar evolución, registrar reiteraciones, crear legajo y carátula paso a paso y sacar fotos de fichas y documentos (varias hojas se guardan como un solo PDF).

- **Se instala como app** desde el navegador: *Agregar a la pantalla de inicio* (Chrome en Android o Safari en iPhone). No hace falta ninguna tienda de aplicaciones.
- **No guarda datos en el teléfono**: ni fichas, ni fotos (no pasan por la galería), ni respuestas del servidor. Sin señal muestra un aviso; lo que se estaba escribiendo sigue en pantalla para guardarlo al volver la conexión.
- **Sesión corta**: desde el celular la sesión se cierra tras 15 minutos sin uso (`SULAM_SESSION_IDLE_MINUTES_MOVIL`). Al volver se pide solo la contraseña, sin perder lo cargado.

**Dirección oficial.** Conviene fijarla en `.env` con `SULAM_URL_PUBLICA` (por ejemplo `http://192.168.0.20:8000`): es la que llevan los QR de las carátulas impresas, así funcionan aunque se imprima desde la máquina donde corre SULAM. Con Docker es necesaria; con `SULAM_DOMINIO` no hace falta.

**Dentro de la oficina** alcanza con que el celular esté en la misma red wifi que la computadora donde corre SULAM: hay que iniciarlo escuchando en la red (`python -m sulam.cli servidor --host 0.0.0.0`, o en Docker poner `SULAM_ESCUCHA=0.0.0.0` en `.env`) y abrir `http://IP-DE-LA-COMPUTADORA:8000`. Sin HTTPS la cámara funciona, pero no se puede instalar como app.

**Fuera de la oficina (datos móviles)** SULAM tiene que estar publicado con HTTPS. Es una decisión del área informática (D-012, D-020). Con Docker:

1. Un dominio (por ejemplo `sulam.ejemplo.gob.ar`) que apunte a la IP pública del servidor, con los puertos 80 y 443 abiertos.
2. En `.env`: `SULAM_DOMINIO=sulam.ejemplo.gob.ar`, `SULAM_COOKIE_SECURE=1` y `SULAM_ENV=produccion`.
3. `docker compose --profile publico up -d --build`. El certificado se obtiene y renueva solo (servicio `https`, archivo `Caddyfile`).

Alternativa más cerrada: no exponer SULAM a internet y entrar por una VPN institucional; la versión celular funciona igual.

## Usuarios de demostración

Creados por `datos-demo`. Contraseña de todos: `demo-sulam-2026`.

| Usuario | Rol | Para probar |
|---|---|---|
| `direccion` | Dirección y Administración | Todo: administración, auditoría, estadísticas de toda la Dirección, aprobar pedidos de personal |
| `directora` | Directora | Inicio con el resumen de la Dirección, estadísticas, publicar novedades |
| `jefa_admision` / `jefe_promocion` | Jefe/a de departamento | Casos para asignar, equipo, casos sin movimiento; aprobar pedidos de su gente (Mi asistencia); estadísticas de su área |
| `jefa_cuidados` | Jefe/a de división | Lo mismo para la División Cuidados |
| `tecnica1`, `tecnica3` (Admisión), `tecnico2` (Promoción), `tecnico4` (Cuidados) | Técnico | Mis casos por urgencia, evoluciones, informe en borrador, pedir carpetas, pedir licencias; también desde el celular |
| `carga` | Carga de Datos | Casos sin registro de demanda, carga desde papel |
| `mesa` | Mesa de Entrada | Ingresos sin legajo y su vinculación |
| `registro` | Oficina de Registro | Carpetas para entregar y recibir (pases) |
| `personal` | Personal | Planta, horarios, reloj, revisión de jornadas, pedidos para registrar, quién no está hoy, Excel de incidencias |
| `adminarea` | Administrativo de Área | Alcance limitado a su área (hoy figura de licencia) |

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

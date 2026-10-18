# Tareas y estado · SULAM

Actualizado: 16/10/2026 · Versión 0.1

## Versión 0.1 — completada

Alcance del documento de diseño §13.1, más los agregados de la revisión.

| # | Funcionalidad | Estado |
|---|---|---|
| 1 | Inicio de sesión con usuarios individuales, cambio obligatorio de contraseña, bloqueo por intentos | ✅ |
| 2 | Roles y permisos configurables (módulo × acción × alcance) desde el panel | ✅ |
| 3 | Registro de ingresos por Mesa de Entrada, con o sin legajo | ✅ |
| 4 | Alta y consulta de legajos únicos | ✅ |
| 5 | Personas sin documento y corrección de documento con motivo | ✅ |
| 6 | Casos y expedientes vinculados | ✅ |
| 7 | Asignación y reasignación de responsables con historial | ✅ |
| 8 | Tablero de casos asignados, con alerta de inactividad | ✅ |
| 9 | Carga, consulta y descarga de documentos (PDF/JPG/PNG) | ✅ |
| 10 | Buscador general | ✅ |
| 11 | Historial de actividad por legajo y auditoría general | ✅ |
| + | Personas e instituciones vinculadas | ✅ |
| + | ~~Casos, documentos y vinculados reservados~~ (quitado por D-021) | — |
| + | Registro de consultas en la auditoría | ✅ |
| + | Detección de duplicados con criterios explícitos y unificación de legajos | ✅ |
| + | Respaldo y restauración verificables | ✅ |
| + | Auditoría inmutable a nivel de base de datos | ✅ |

### Verificación realizada
- 25 pruebas automatizadas contra PostgreSQL 16, todas aprobadas (incluye los 8 criterios de aceptación y los formularios institucionales).
- Recorrido completo de la interfaz en navegador con cada rol de demostración (alta con duplicado, carga de documento, ingreso vinculado, matriz de roles, vista móvil).
- Pendiente de verificar en una máquina con acceso normal a internet: `docker compose up --build` y `npm install` (el entorno de desarrollo no tenía acceso a los registros de paquetes; el código se probó con las mismas bibliotecas obtenidas de sus repositorios oficiales).

## Versión 0.2 — en curso

| Funcionalidad | Estado |
|---|---|
| Carátula de legajo con los campos del modelo institucional, al crear el caso | ✅ |
| Registro de demanda (secciones 1 a 8) precargado desde la carátula y el legajo | ✅ |
| Evolución del caso | ✅ |
| Vistas imprimibles de carátula y registro de demanda | ✅ |
| Datos del legajo ampliados (género, barrio, departamento, coberturas, CUD, discapacidad) | ✅ |
| Actuación N° automática por año, con continuidad de la numeración en papel | ✅ |
| Carga desde papel: receptor ≠ quien carga, fecha y autor de cada evolución, escaneo del original | ✅ |
| Legajo = DNI (SD provisorio sin documento) | ✅ |
| Una actuación por persona por año; reiteraciones | ✅ |
| Circuito: Mesa deriva al departamento → jefe/a de departamento crea la carátula en pantalla (número automático) → Registro digitaliza | ⏳ a definir con la Dirección |
| Roles «Jefe/a de departamento» y «Directora» (propuesta) | ✅ |
| Página de inicio por rol | ✅ |
| Rol «Jefe/a de división» (mismos permisos que jefe de departamento) | ✅ |
| Rol «Oficina de Registro» | ⏳ a definir con la Dirección |

## Versión para celular

| Funcionalidad | Estado |
|---|---|
| Pantallas para celular: inicio con mis casos, búsqueda, legajo, caso con llamadas | ✅ |
| Evolución, reiteración, alta de legajo y carátula por pasos | ✅ |
| Fotos de documentos (varias hojas → un PDF, sin galería ni metadatos) | ✅ |
| Todo lo que se carga en la versión completa, también desde el celular (demanda, articulación, estado, asignación, carátula, vinculados, expedientes, Mesa de Entrada, recursos y contactos) | ✅ |
| Instalable como app (PWA) sin guardar datos; sesión de 15 min; reingreso sin perder lo escrito | ✅ |
| Publicación con HTTPS (Caddy, perfil `publico`) | ✅ preparado · ⏳ dominio y servidor a definir con informática |
| Probar en teléfonos reales del equipo (Android e iPhone) | ⏳ |
| Cola de impresión: carátulas nuevas pendientes, impresión en tanda (una por hoja) | ✅ |

## Red de recursos

| Funcionalidad | Estado |
|---|---|
| Mapa de recursos: centros de día, centros de jubilados, residencias, instituciones, cuidadores formados | ✅ |
| Directorio de contactos (técnicos de gobiernos locales y otras instituciones) | ✅ |
| Casos en el mapa (todos los técnicos) y salidas de visita con recorrido y hoja imprimible | ✅ |
| Origen de cada dato (capacitaciones, articulaciones, relevamiento…) y articulaciones registradas en cada caso | ✅ |
| Registrar articulaciones desde el celular | ✅ |
| Carga en lote de lo relevado en una capacitación (planilla) | ⏳ |
| Recursos cercanos a un caso (p. ej., cuidadores que viven cerca) | ⏳ |
| Cuidadores de cada caso (vínculo del legajo con un cuidador, formado o no) | ⏳ |
| Registro de la División de Participación y Sensibilización Ciudadana (talleres, campañas, capacitaciones, centros de jubilados) | ⏳ a relevar con la División |
| Carga inicial de recursos (hoy en papel o dispersos) | ⏳ |

## Informes

| Funcionalidad | Estado |
|---|---|
| Editor de informes con plantilla y datos de la persona completados solos (computadora y celular) | ✅ |
| Datos y secciones agregables, quitables y reordenables; insertar evoluciones, articulaciones y demanda | ✅ |
| Firma con PDF con membrete en el legajo; versiones para corregir | ✅ |
| Plantillas editables por Dirección y jefaturas | ✅ |
| Validar las plantillas iniciales con los equipos técnicos | ⏳ |

## Casos y constancias

| Funcionalidad | Estado |
|---|---|
| Varios técnicos a cargo de un caso (todos responsables) | ✅ |
| Certificación negativa de ANSES: CUIL, acceso a ANSES, lectura del PDF, vencimiento, avisos | ✅ |
| Calibrar la lectura con negativas reales (con datos autorizados) | ⏳ |
| Otras constancias de organismos | ⏳ a definir |

## Comunicación interna

| Funcionalidad | Estado |
|---|---|
| Novedades de la Dirección y de las áreas, circulares adjuntas, confirmación de lectura | ✅ |
| Carpetas en papel: ubicación y pases (pedir, entregar, devolver), carga inicial por número de legajo | ✅ |
| Nombre del área de archivo y quiénes la integran | ⏳ a confirmar con la Dirección |

## Filtros y estadísticas

| Funcionalidad | Estado |
|---|---|
| Filtros por cualquier campo en Casos, Legajos, Expedientes, Mesa de Entrada, Recursos y Contactos | ✅ |
| Estadísticas de casos (con filtros, por área, tocar un número abre los casos) | ✅ |
| Estadísticas de funcionamiento interno (carga y tiempos, asistencia, circuitos, comunicación) | ✅ |
| Excel y PDF de estadísticas | ✅ |
| Rol para el Departamento Planificación y Estadística | ⏳ a definir (hoy se asigna el permiso «Estadísticas» desde Administración) |
| Estadísticas en la versión para celular | ⏳ |

## Personal y asistencia

| Funcionalidad | Estado |
|---|---|
| Fichas de personal ligadas a usuarios (alta, baja, reingreso, área y cargo) | ✅ |
| Horarios con vigencia y confirmación | ✅ |
| Importación del reloj con vista previa, identificación de ID y sin duplicados | ✅ |
| Cálculo de incidencias con las reglas de la app original (mismos casos de prueba) | ✅ |
| Revisión de jornadas con huella; justificativos con adjuntos | ✅ |
| Pedidos de licencia, comisión y cambio de horario (persona → jefatura → Personal) | ✅ |
| «Quién está hoy» en equipo de casos, carpetas e inicio | ✅ |
| Significado de CT, CE, CS, VAO, DF, C3, SESOP y reglas por tipo de licencia | ⏳ a confirmar con Personal |
| Excel de incidencias | ✅ |
| Avisos del navegador (casos, novedades, carpetas, pedidos) | ✅ |
| Informe mensual en PDF por persona | ⏳ etapa 2 |
| Importar los datos de la app de Google (en el servidor de la Dirección) | ⏳ etapa 2 |

## Digitalización con el celular

| Funcionalidad | Estado |
|---|---|
| Bandeja de fotos por persona, armado de documentos con varias hojas | ✅ |
| Tipos documentales nuevos con plantilla (vencimiento, número, campos propios) | ✅ |
| Vencimiento visible en el legajo | ✅ |
| Editar la plantilla de un tipo existente (desde la clasificación de hojas; no se quitan datos ya definidos) | ✅ |
| Lectura automática (OCR local, Tesseract español): sugiere legajo por DNI/CUIL, tipo por palabras del nombre, emisión, vencimiento y número; la persona confirma | ✅ |
| Reconocimiento: el tipo también se sugiere por las palabras que repiten los documentos ya cargados de cada tipo; la bandeja detecta hojas del mismo documento («Página X de Y») | ✅ |
| Calibrar el reconocimiento con documentos reales (DNI, certificados) y con el idioma español | ⏳ |
| Texto de cada documento guardado (PDF con texto u OCR), buscador «Buscar en documentos» respetando permisos y auditado, vista del texto con marcas en nombre/DNI/CUIL de la persona y menciones a la Dirección, alerta si el legajo no coincide; comando `indexar-textos` para los ya cargados | ✅ |
| Resaltar sobre la imagen de la hoja (se ubican las palabras al abrir la vista; requiere permiso de descarga y queda auditado) | ✅ |
| Sugerir el tipo leyendo la foto (OCR local) | ⏳ |
| Limpieza de fotos descartadas | ⏳ |

## Digitalización de fichas — en curso

| Funcionalidad | Estado |
|---|---|
| Fichas en papel v1 (carátula, registro de demanda, hoja de evolución) con marcas y QR | ✅ |
| Lectura: enderezado, identificación por QR, casillas, recortes (validado con fotos simuladas) | ✅ |
| Captura desde el celular con QR (por caso y por lotes) | ⏳ rama `captura-celular` (su migración pasa a ser la 0020) |
| Pantalla de revisión campo por campo (recorte + valor + aprobar/corregir) | ⏳ |
| Reconocimiento de dígitos manuscritos en cuadrículas (local) | ⏳ |
| Lectura de las fichas anteriores (sin marcas) | ⏳ necesita fotos reales |
| Calibrar con fotos reales de las fichas nuevas completadas | ⏳ |

## Próximos pasos

### Antes de mostrar al equipo
- [x] Datos de demostración para todos los roles y `probar-en-casa.bat` (README › Probar en casa).
- [ ] Levantar con Docker en una computadora de la Dirección y recorrer con los usuarios de demostración.
- [ ] Revisar con Ivana, Cristina y Nancy los roles propuestos y el texto de las pantallas.

### Con el relevamiento (octubre–noviembre)
- [ ] P-003: cargar la matriz definitiva de permisos.
- [ ] P-004: reglas de derivación automática.
- [ ] Validar catálogos (tipos de vínculo, tipos documentales).

### Con el área informática
- [ ] Revisar ARCHITECTURE.md y DECISIONS.md (D-002, D-008, D-012).
- [ ] Definir alojamiento, HTTPS, respaldos programados (por ejemplo, `sulam respaldar` diario + copia fuera del servidor) y monitoreo.
- [ ] Prueba de restauración en un servidor distinto.

### Fase 2 en adelante (documento de diseño §16)
- [ ] Captura por QR desde el celular para la lectura automática de fichas.
- [ ] Optimización de imágenes (perspectiva, recorte, compresión) y OCR asistido.
- [ ] Plantillas institucionales e informes con estados (borrador, finalizado, copia física firmada).
- [x] Archivo físico: ubicaciones y pases de carpetas (pedido, entrega, devolución).
- [ ] Autorizaciones con passkeys (WebAuthn).
- [ ] Área de Cuidados: subsidios.
- [ ] Estadísticas institucionales.
- [ ] Segundo proveedor de almacenamiento (D-008).

## Convenciones de trabajo
- Cada cambio de esquema va en una migración nueva de Alembic (`backend/alembic/versions`), nunca editando una existente.
- Cada regla funcional nueva se documenta en FUNCTIONAL_SPEC.md y, si implica una elección, en DECISIONS.md.
- No se agregan campos administrativos que no surjan del relevamiento.
- Las pruebas deben pasar antes de integrar cambios: `cd backend && pytest`.

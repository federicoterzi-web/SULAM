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
| + | Casos, documentos y vinculados reservados | ✅ |
| + | Registro de consultas en la auditoría | ✅ |
| + | Detección de duplicados con criterios explícitos y unificación de legajos | ✅ |
| + | Respaldo y restauración verificables | ✅ |
| + | Auditoría inmutable a nivel de base de datos | ✅ |

### Verificación realizada
- 25 pruebas automatizadas contra PostgreSQL 16, todas aprobadas (incluye los 8 criterios de aceptación y los formularios institucionales).
- Recorrido completo de la interfaz en navegador con cada rol de demostración (alta con duplicado, carga de documento, ingreso vinculado, caso reservado visto por otro técnico, matriz de roles, vista móvil).
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

## Digitalización de fichas — en curso

| Funcionalidad | Estado |
|---|---|
| Fichas en papel v1 (carátula, registro de demanda, hoja de evolución) con marcas y QR | ✅ |
| Lectura: enderezado, identificación por QR, casillas, recortes (validado con fotos simuladas) | ✅ |
| Captura desde el celular con QR (por caso y por lotes) | ⏳ rama `captura-celular` |
| Pantalla de revisión campo por campo (recorte + valor + aprobar/corregir) | ⏳ |
| Reconocimiento de dígitos manuscritos en cuadrículas (local) | ⏳ |
| Lectura de las fichas anteriores (sin marcas) | ⏳ necesita fotos reales |
| Calibrar con fotos reales de las fichas nuevas completadas | ⏳ |

## Próximos pasos

### Antes de mostrar al equipo
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
- [ ] Captura por QR desde el celular.
- [ ] Optimización de imágenes (perspectiva, recorte, compresión) y OCR asistido.
- [ ] Plantillas institucionales e informes con estados (borrador, finalizado, copia física firmada).
- [ ] Archivo físico: ubicaciones, movimientos, préstamos.
- [ ] Autorizaciones con passkeys (WebAuthn).
- [ ] Área de Cuidados: subsidios.
- [ ] Estadísticas institucionales.
- [ ] Segundo proveedor de almacenamiento (D-008).

## Convenciones de trabajo
- Cada cambio de esquema va en una migración nueva de Alembic (`backend/alembic/versions`), nunca editando una existente.
- Cada regla funcional nueva se documenta en FUNCTIONAL_SPEC.md y, si implica una elección, en DECISIONS.md.
- No se agregan campos administrativos que no surjan del relevamiento.
- Las pruebas deben pasar antes de integrar cambios: `cd backend && pytest`.

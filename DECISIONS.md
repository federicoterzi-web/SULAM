# Decisiones de diseño · SULAM

Cada decisión indica su estado: **Vigente**, **Provisoria** (a revisar con el relevamiento o con el área informática) o **Pendiente**.

---

## Decisiones tomadas

### D-001 · Monolito modular — *Vigente*
Una aplicación, una base, módulos con responsabilidades separadas. Más simple de instalar, respaldar y mantener que microservicios para el tamaño de la institución.

### D-002 · Stack: React + FastAPI + PostgreSQL — *Provisoria*
Elegido por madurez, costo cero de licencias y facilidad para encontrar quien lo mantenga. **Queda sujeto a la evaluación del área informática** (ver D-012), en particular hosting, versión de PostgreSQL y política de actualizaciones.

### D-003 · Identificador interno independiente del documento — *Vigente*
UUID interno + número de legajo visible **igual al DNI** (documento de diseño §3.1); «SD-NNNNNN» provisorio para quien no tiene documento, conservado para búsquedas cuando se obtiene el DNI. Permite personas sin documento, correcciones de DNI y unificación sin perder historial.

### D-004 · Persona, caso y expediente como entidades distintas — *Vigente*
Según el documento de diseño (§3.3).

### D-005 · Nada se borra físicamente — *Vigente*
Casos se cierran, documentos se dan de baja lógica, vínculos se desactivan, legajos se unifican. La eliminación definitiva queda sujeta a la política de conservación documental (pendiente P-007).

### D-006 · Auditoría de solo agregado, incluidas las consultas — *Vigente*
Se registran también aperturas de legajos, búsquedas y descargas. Motivo: los legajos contienen **datos sensibles** en los términos de la Ley 25.326 (art. 2, por ejemplo información referente a la salud) e información sobre situaciones de violencia, y la institución debe poder responder *quién vio qué*. La inmutabilidad se garantiza en la base con triggers, no solo en la aplicación.

### D-007 · Información reservada — *Reemplazada por D-021*
Además del alcance por rol, existe una marca de **reserva** para casos, tipos documentales, documentos y personas vinculadas. Un caso reservado muestra su existencia (para evitar intervenciones duplicadas) pero no su contenido. Acceso: responsables asignados, quien lo creó y el permiso *Información reservada › Consultar*.

### D-008 · Almacenamiento local en la 0.1; Google Drive postergado — *Provisoria*
El documento de diseño preveía Google Drive gratuito para pruebas. Se implementó primero el almacenamiento **local**, detrás de la misma interfaz, porque:
- las cuentas de servicio de Google no tienen cuota propia en cuentas gratuitas, de modo que la integración debería usar OAuth de una persona: los archivos quedarían atados a una cuenta personal;
- el almacenamiento local permite probar desde el primer día el procedimiento de migración entre proveedores (`sulam migrar-archivos`), que es lo que realmente importa.
Agregar Google Drive u otro proveedor es una clase nueva en `storage.py`. **Decidir con informática** el destino definitivo (servidor institucional, almacenamiento S3 compatible, etc.).

### D-009 · Datos reales — *Vigente*
**No se cargan datos reales** hasta que se verifiquen: autorización institucional; normativa de protección de datos; condiciones del alojamiento; acceso por HTTPS (`SULAM_COOKIE_SECURE=1`); respaldos programados y probados; responsable de seguridad designado (P-008).

### D-010 · Sesiones por cookie HttpOnly + CSRF — *Vigente*
Sesiones revocables desde el servidor (al desactivar un usuario o restablecer su contraseña). No se usan tokens JWT de larga vida.

### D-011 · Detección de duplicados con criterios explícitos — *Vigente*
Criterios documentados en FUNCTIONAL_SPEC §3.1. Mismo documento bloquea; el resto avisa y exige confirmación auditada. Los umbrales pueden ajustarse con la experiencia de uso.

### D-012 · Participación del área informática — *Vigente*
Para dar al área informática un rol real sin reabrir decisiones funcionales, se separan:
- **Propuestas sujetas a su evaluación**: hosting, almacenamiento definitivo, copias de seguridad programadas, monitoreo, certificados HTTPS, integración con cuentas institucionales, endurecimiento del servidor.
- **Principios no negociables** (definidos por la Dirección): legajo único, permisos verificados en el servidor, auditoría inmutable, nada se borra, sin datos reales sin las condiciones de D-009.

### D-013 · Catálogos iniciales — *Provisoria*
- **Áreas**: organigrama vigente (2011). La propuesta de modificación no está aprobada y no se usa.
- **Tipos documentales**: los del documento de diseño §6.2.
- **Tipos de vínculo**: propuesta inicial (Familiar, Referente afectivo, Conviviente, Denunciante, Representante legal o apoyo, Institución, Otro). A validar en el relevamiento.
Todos son editables desde *Administración › Catálogos*.

### D-014 · Roles iniciales — *Provisoria*
Los cinco roles del documento de diseño §5.3, con una matriz de permisos propuesta (FUNCTIONAL_SPEC §9). La matriz definitiva es institucional (P-003).

### D-015 · Dependencias mínimas — *Vigente*
Contraseñas con scrypt (biblioteca estándar), enrutamiento propio en el frontend y compilación con esbuild: menos paquetes externos que actualizar y auditar.

### D-016 · Carátula y registro de demanda según los modelos institucionales — *Vigente*
Se incorporaron los campos exactos de los dos modelos (resuelve P-001). La carátula vive en el caso; el registro de demanda es una entidad propia ligada al caso, cargada después de la carátula y precargada con ella. Los datos estables de la persona (género, coberturas, CUD, discapacidad, barrio, departamento) se guardan en el legajo y se reutilizan, para no cargarlos dos veces. Las opciones se guardan como códigos estables con los textos del modelo, pensando en las estadísticas.

### D-017 · Actuación N° = número de caso por año — *Vigente*
Según la Dirección, la Actuación N° es el número de caso iniciado / carátula generada en el año. Se unificó con el número de caso (`C-AAAA-NNNNN`), se asigna automáticamente, es única por año, admite cargar carátulas anteriores con su número y se puede fijar el próximo número para continuar la numeración en papel.

### D-018 · Fichas nuevas con marcas; lectura local con revisión humana — *Vigente*
- Desde la implementación se usan las fichas impresas por SULAM (versión 1), con marcas de esquina, QR y cuadrículas, porque permiten ubicar cada campo con precisión en una foto.
- Las fichas anteriores (unos seis meses de registros en los modelos previos) también deben poder digitalizarse: se ubicarán los campos por los textos impresos del formulario. Requiere muestras reales para calibrar.
- La lectura de texto manuscrito es **solo local** (sin servicios externos), por tratarse de datos sensibles. Toda lectura automática pasa por revisión humana, campo por campo, mostrando el recorte.
- Si en el futuro cambia una ficha, se crea una versión nueva (el QR indica la versión) y el lector mantiene las anteriores.

### D-019 · Una actuación por persona por año; los nuevos ingresos son reiteraciones — *Vigente*
Definido por la Dirección. Áreas que manejan casos: Departamento de Admisión de Casos y Recepción de Denuncias y Departamento de Promoción Integral de Derechos (roles por área: pendiente P-003).

### D-020 · Versión para celular: la misma aplicación, sin datos en el teléfono — *Vigente*
Pedido de la Dirección para agilizar las cargas, también en visitas (con datos móviles).
- Es la misma SULAM con pantallas propias para el celular (`#/m`), instalable como app web (PWA), no una app de tienda: un solo sistema, los mismos permisos y la misma auditoría.
- Tareas: consulta de legajos y casos, evolución, reiteración, alta de legajo y carátula por pasos, fotos de documentos y fichas. Lo demás (registro de demanda, administración, Mesa de Entrada) queda en la versión completa.
- **Nada queda en el teléfono**: el service worker no guarda respuestas; las fotos se toman desde SULAM (no van a la galería), se reducen y se les quitan los metadatos (ubicación) antes de enviarlas, y el servidor las vuelve a procesar.
- Sesiones iniciadas desde el celular: cierre por inactividad a los 15 minutos (configurable). Al vencer se pide la contraseña sin perder lo escrito.
- Sin carga sin conexión por ahora (requeriría guardar datos sensibles en el teléfono). Se reevalúa si en las visitas la falta de señal resulta frecuente.
- Uso fuera de la oficina: requiere publicar con HTTPS (preparado con Caddy en `docker-compose`, perfil `publico`) o una VPN. Lo define informática (P-009).

### D-021 · Sin categoría de información reservada — *Vigente*
Decisión de la Dirección (17/10/2026): se elimina la marca de reserva de casos, documentos, tipos documentales y personas vinculadas, y el permiso *Información reservada*. Quien puede consultar un caso ve todo su contenido, también en el mapa y las salidas. Lo que sigue limitando el acceso es el alcance de cada rol (consultar / modificar) y la auditoría, que registra cada consulta. La migración 0012 elimina las columnas.

### D-022 · Informes redactados en SULAM: borrador editable, firmado inmodificable con versiones — *Vigente*

Los informes se redactan dentro de SULAM a partir de plantillas que traen los datos de la persona. Mientras es borrador se edita (con guardado automático); al **firmarlo** se genera el PDF con membrete y queda como documento del legajo, sin cambios posteriores. Para corregir se abre una **nueva versión** del mismo informe; la anterior queda «reemplazada» y se conserva (pedido de la Dirección, 17/10/2026). El texto con formato se limpia en el servidor (solo párrafos, listas, negrita, cursiva y subrayado). Las plantillas las editan la Dirección (todas) y las jefaturas (las de su área). El modelo de informe aportado por la Dirección se usó solo como estructura; su contenido no se cargó en SULAM.


### D-023 · Varios técnicos a cargo, todos responsables — *Vigente*
Pedido de la Dirección (17/10/2026): un caso puede tener varios técnicos a cargo, sin responsable principal. Se usa la tabla de asignaciones existente (una fila por técnico, con desde/hasta); `PUT /casos/{id}/equipo` deja el equipo indicado.

### D-024 · Negativa de ANSES asistida, sin consultas automáticas a ANSES — *Vigente*
SULAM no consulta ANSES desde el servidor: el servicio está pensado para uso desde el navegador (con controles anti-robots) y no se envían datos de los legajos a sitios externos. SULAM calcula el CUIL, abre el servicio, lee el PDF descargado (propuesta que la persona revisa), lo guarda en el legajo y controla el vencimiento. La tabla `constancias` admite otros tipos de constancias a futuro.

### D-025 · Asistencia dentro de SULAM, con las reglas de la app original y sin datos reales en el repositorio — *Vigente*
Las reglas de cálculo se portan tal cual (segundos ignorados, ventana de 30 min, tolerancia de 10 min recuperada el mismo día, cobertura por tramos, CAMBIO reemplaza el turno) y se prueban con los mismos casos que la app original. SULAM no ejecuta descuentos: solo revisa y propone. El repositorio es público, así que la planta real, los ID del reloj, los horarios y los archivos del reloj nunca se copian a él: se cargan en el servidor de la Dirección. La ficha de personal es la fuente del área de cada usuario y la baja desactiva su acceso. Los pedidos siguen el circuito persona → jefatura → Personal. Los motivos de salud quedan reservados a la persona, Personal y la Dirección.

### D-026 · Un solo catálogo de filtros para listas y estadísticas — *Vigente*
Los campos filtrables se declaran una vez (`sulam/filtros.py`) y los usan las seis listas y las estadísticas. Así, cada número de una estadística trae el filtro que lo reproduce y «tocar el número» abre exactamente esos casos (lo verifica una prueba). Los filtros viajan en la dirección de la página (`?f=`), no se guardan en el navegador. Las estadísticas se calculan en el momento, sobre la base, con el alcance de quien consulta (Dirección: todo; jefaturas: su área; Personal: solo asistencia). Las descargas quedan en la auditoría. La edad se calcula a hoy, igual que en el filtro.
---

### D-027 · Avisos del navegador con texto genérico — *Vigente*
Las notificaciones usan la API del navegador y no llevan nombres ni datos de personas (solo cantidades por tipo). Lo avisado se recuerda en el propio navegador. Las notificaciones push con SULAM cerrado pasan por servicios de Google, Apple o Mozilla: se harán solo con el mismo criterio de texto genérico y cuando exista el servidor con HTTPS (D-012).

### D-028 · Captura por lotes con bandeja personal y tipos documentales con plantilla — *Vigente*
Se reemplaza el diseño anterior de captura por QR (rama `captura-celular`, sin terminar): las fotos van a una bandeja personal y se clasifican después, en el celular o la computadora. Las plantillas de tipo (vencimiento, número, campos propios) las puede crear cualquier usuario que carga documentos, con auditoría. Los vencimientos se muestran solo dentro del legajo. Las fotos descartadas no se borran del almacenamiento (es por contenido y puede compartirse); su limpieza queda para una tarea de mantenimiento.

## Pendientes (no se inventan)

| Id | Tema | Depende de |
|---|---|---|
| ~~P-001~~ | ~~Campos de carátula y registro de demanda~~ — resuelto en D-016 | — |
| ~~P-012~~ | ~~Origen de la Actuación N°~~ — resuelto: correlativo de carátulas por año = número de caso (D-017) | — |
| P-002 | Formularios y modelos documentales (informes, plantillas) | Relevamiento |
| P-003 | Matriz definitiva de roles y permisos | Dirección |
| P-004 | Reglas de asignación y derivación automática | Relevamiento de circuitos |
| P-005 | Estados y circuitos específicos de expedientes | Relevamiento |
| P-006 | Organización del archivo físico | Relevamiento |
| P-007 | Conservación y eliminación documental | Normativa y Dirección |
| P-008 | Responsables institucionales de seguridad y respaldo | Dirección / informática |
| P-009 | Alojamiento definitivo y almacenamiento de archivos | Informática (D-008, D-012) |
| P-010 | Procedimiento de recuperación ante incidentes | Informática |
| P-011 | Umbral de "sin actividad" del tablero (hoy 30 días) | Equipo técnico |


## D-029 — Lectura automática de documentos fotografiados
OCR local con Tesseract (idioma español, instalado en la imagen Docker); ninguna imagen sale del servidor. El resultado son sugerencias que rellenan solo campos vacíos del formulario de clasificación; nunca se guarda ni clasifica sin confirmación. Se lee al abrir «Armar documento» (hasta 20 hojas). Si Tesseract no está, la función se omite sin error.

## D-030 — Texto de los documentos: guardado, búsqueda y resaltado
El texto leído se guarda en `documentos.texto` (hojas separadas por salto de página) y en una versión sin tildes para el índice de búsqueda de PostgreSQL. Se lee en segundo plano al cargar; los anteriores se leen con `indexar-textos`. La búsqueda y la vista del texto aplican el mismo control de acceso que abrir el documento; las búsquedas se auditan (texto buscado y cantidad, no el contenido). Las menciones institucionales se configuran con `SULAM_MENCIONES` (separadas por «;»). El resaltado sobre la imagen queda para una etapa posterior.

## D-031 — Marcas sobre la imagen de la hoja
Las cajas se calculan al abrir la vista (se dibuja la hoja y se ubican las palabras con OCR), sin guardar coordenadas: no hay datos nuevos que proteger ni migrar. Ver la hoja como imagen exige el permiso de descarga y se audita; las marcas solo, el de consulta.

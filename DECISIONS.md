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

## D-032 — Calibración del reconocimiento y historial de pases en Administración
La calibración es opcional y la enciende el administrador (tabla `ajustes`). Compara lo sugerido con lo confirmado y guarda solo la diferencia (campo, resultado, tipo documental) en `calibracion_casos`. El fragmento de texto, también opcional, se guarda con todos los números tapados y toda palabra que empiece con mayúscula tapada salvo palabras clave de fechas y la Dirección. La lectura sugerida se recuerda en memoria del servidor hasta 2 horas para poder compararla; si el servidor se reinicia en ese lapso, ese caso no se registra. El informe exportable y el vaciado quedan auditados. El historial de pases es de solo lectura y solo para quien administra.

## D-033 — Agenda
Interna, sin compartir con otras instituciones. Cada persona ve las actividades en que participa o que cargó y, con alcance «área», las de su área. Los títulos no deben llevar nombres: el legajo ligado se muestra solo a quien tiene acceso a él y, si no, aparece como «Legajo reservado». Los avisos del navegador alcanzan únicamente a los participantes y no incluyen datos. El resultado de una salida o visita ligada a un caso se copia a la evolución del caso. El módulo es nuevo: sus permisos se agregan una sola vez a los roles que ya existían (registro en `ajustes`); si después se quitan desde Administración, no se vuelven a poner.

**Ampliación.** Las actividades repetidas se guardan como actividades reales (una por fecha, unidas por una serie), cada una con su propio resultado; se puede editar o cancelar «solo esta» o «esta y las siguientes», pero el resultado se carga siempre de a una. Todo cambio de día, hora, lugar, participantes o legajo queda en un historial por actividad (quién, cuándo, motivo opcional). Vencimientos de documentos y ausencias del personal se muestran junto a la agenda solo para lectura: los vencimientos únicamente de los legajos que la persona puede ver (sin los ya renovados), y las ausencias (licencias y comisiones aprobadas) de su área; la licencia por enfermedad figura como «Ausente», sin la clase.

## D-034 — Participación y Sensibilización Ciudadana
Los eventos de la división **son actividades de la agenda** (clase «evento»): comparten día, hora, lugar, participantes, estado, repetición e historial; los datos propios (flyer, tipo, instituciones, resumen, campaña, organización a cargo, presencia de la Directora sugerida, asistentes) viven en una tabla aparte. Un evento no se crea ni se edita por la vía general de la agenda. Sin flyer, el título es el nombre del tipo; los tipos los define el área. Las campañas reúnen material y eventos; cada evento puede estar a cargo de otra organización. Los asistentes y las fotos (hasta 2 por evento) se cargan una vez realizado el evento. **A pedido del Director: las fotos se suben sin casilla de autorización de imagen** (conviene que el área cuente con ella por fuera del sistema); el brief para Comunicación sale **solo en Word**. Los eventos no llevan datos de personas. Permisos: módulo «participacion» (consultar, crear, modificar, descargar = brief, administrar = tipos); el rol «Participación y Sensibilización» se suma a otro rol; Dirección y Directora lo ven todo (la Directora, además, descarga el brief). Estadísticas: pestaña propia, con el alcance de Participación o, si no, el de Estadísticas.

## D-035 — Participación: el flyer es una imagen y las instituciones se vinculan al mapa de recursos
**A pedido del Director (18/10/2026).** El flyer no tiene título: es una **imagen** que se sube al evento, antes o después de realizado (y, si el evento es parte de una serie, puede copiarse a las fechas siguientes). El evento se registra **siempre con el nombre de su tipo**; la migración 0026 quita el «nombre del flyer» y repone el título de los eventos ya cargados. Las instituciones con las que se coordina un evento se **eligen del mapa de recursos** (queda el vínculo, que se ve en el detalle y cuenta en las estadísticas) y, solo si no están cargadas, se pueden escribir a mano. El flyer sale en el brief (Word y PDF).

## D-036 — Menú agrupado en solapas
**A pedido del Director (18/10/2026).** El menú lateral pasó de 22 entradas a 11 grupos: Legajos y casos; Mesa y expedientes (con pases de carpetas); Agenda y salidas (con el mapa de casos); Documentos (digitalización, búsqueda y fichas en papel); Red de recursos (recursos y contactos); Personal y asistencia; y Administración (con plantillas de informes y auditoría), además de Tablero, Novedades, Participación y Estadísticas. Cada pantalla conserva su dirección (los enlaces y marcadores siguen valiendo); las del mismo grupo se ven como solapas arriba del contenido, y cada rol solo ve las que sus permisos habilitan. La versión para celular no cambia.

## D-037 — Tableros armados como widgets, por perfil
**A pedido del Director (18/10/2026).** Cada perfil de tablero (Dirección, Jefatura, Técnico/a, Carga, Mesa, Administrativo de área, Personal, Participación) es una grilla de 12 columnas con bloques (widgets). Desde Administración › Tableros se arrastran para ordenar, se estiran desde el borde derecho (o se elige el ancho: 1/4, 1/3, 1/2, 2/3, 3/4, completo) y se ocultan o muestran. El diseño es **por perfil** (lo usan todos los roles que comparten ese perfil), se guarda en `ajustes` (clave «tableros») y se puede volver al original. Los bloques que se agreguen en versiones futuras se suman al final. Se audita cada cambio. La versión para celular no cambia.

## D-038 — Residencias de larga estadía e internaciones (primera etapa)
**A pedido del Director (18/10/2026).** Las residencias son recursos del mapa (tipo «Residencia de larga estadía») y suman una ficha de **documentación** (habilitación SIPROSA y fiscalización sanitaria obligatorias; habilitación municipal, bomberos, director/a técnico/a, seguro y otros opcionales) con número, emisión, vencimiento y copia escaneada opcional. Cuenta el documento más reciente de cada tipo: una renovación reemplaza al vencido. Estados: vigente, por vencer (60 días), vencido, sin fecha, falta. El navegador avisa de lo vencido o que vence en 30 días. La **internación** es un registro del legajo (residencia del mapa o lugar escrito, modalidad, desde, hasta y motivo de egreso); una sola vigente por persona, con historial. Módulo de permisos nuevo «residencias» (consultar / crear / modificar); para ver personas internadas se exige además el alcance sobre el legajo. Pantalla «Residencias e internaciones» dentro de Red de recursos. **Pendiente (próximas etapas):** subsidios (internación, alimentarios, materiales) con papeles presentados, meses y pagos; cuidadores (desde cuándo, horas, pagos).

## D-039 — Subsidios con papeles y pagos mensuales
**A pedido del Director (18/10/2026), sobre dos documentos de la Dirección:** la propuesta al Ministro de Desarrollo Social (1/6/2026) con los requisitos del subsidio de cuidados y del de residencia, y la circular a los referentes de Residencias de Larga Estadía (15/5/2026) con la documentación mensual para pagar las estadías. Un **subsidio** pertenece a una persona (tipos: residencia, cuidador/a, alimentario, materiales, otro) y tiene: estado del trámite (en trámite, elevado, aprobado, rechazado, suspendido, finalizado), resolución y vigencia, monto mensual y, según el tipo, residencia o cuidador del mapa (o escrito) y horas por semana. Al crearlo copia la **lista de papeles** del catálogo (`subsidios_catalogo.py`, editable en el código): cada papel se marca falta / presentado / no corresponde, y se pueden sumar papeles propios. Los de residencia y cuidados tienen **pagos mensuales**, cada uno con su lista (en residencias, los 8 papeles del residente; los 8 de la institución están en D-040): con todos presentados el mes pasa solo a «documentación completa»; no se liquida con papeles faltantes salvo confirmación explícita, que queda auditada. «Generar los pagos del mes» crea el mes de todos los subsidios aprobados y vigentes. Módulo de permisos «subsidios» (consultar / crear / modificar / administrar): administrar aprueba o rechaza, carga la resolución y la vigencia y pasa los pagos a liquidación o pagado. Para alimentarios y materiales no hay lista oficial: queda vacía para completar con lo que se pida. **Pendiente de validar con la Dirección:** la documentación mensual de cuidados (hoy solo comprobantes del mes),.

## D-040 — Papeles de la institución: una vez por residencia y mes
**A pedido del Director (18/10/2026):** los papeles que presenta la residencia (nota de reintegro, habilitación SIPROSA, categorización, cumplimiento fiscal, constancia de inscripción, CBU, factura, CAE) se cargan **una sola vez por residencia y mes** y quedan vinculados a los requisitos del subsidio de cada residente. Tabla `recurso_periodo_requisitos`; la lista del mes se arma sola al crear el primer pago de un residente de esa residencia (o a mano desde la ficha de la residencia, «Documentación del mes para el subsidio»). Al marcar un papel, se recalcula el mes de todos los residentes. Si el subsidio tiene la residencia escrita a mano (no del mapa), los papeles de la institución quedan en cada pago, como antes. La migración 0030 pasa lo ya cargado al nuevo esquema.

## D-041 — Departamento y localidad: desplegable buscable en cascada
**A pedido del Director (18/10/2026):** donde haya departamento y localidad (legajo, carátula y demanda de la ficha, recursos, contactos y carga móvil) se elige **primero el departamento** y la localidad se busca solo entre las de ese departamento (sin tildes ni mayúsculas, con teclado o toque). Sin departamento, la búsqueda recorre todas y al elegir una completa el departamento. Al cambiar de departamento, una localidad que no le corresponde se vacía. **Siempre se puede escribir una localidad que no esté en la lista.** La lista de partida (`localidades.py`) está armada a mano con las localidades más conocidas de cada departamento: **no es el listado oficial completo**; se completa sola con las localidades que se van cargando en legajos, recursos y contactos (`GET /api/localidades`) y se corrige editando ese archivo. Pendiente: reemplazarla por el listado oficial (INDEC/Provincia) cuando se consiga.

## D-042 — Baja de un usuario con casos a cargo
**A pedido del Director (18/10/2026):** al dar de baja a un usuario con casos abiertos a su cargo, el sistema no lo permite hasta decidir **caso por caso** a quién pasa cada uno (cualquier persona activa) o si queda **para asignar**; hay un atajo para pasarlos todos a una sola persona (aparecen en «casos sin responsable» de la jefatura). Las asignaciones del usuario se cierran con fecha y motivo «Baja del usuario» y quedan en el historial; los casos cerrados no se tocan. Queda en la auditoría. El alcance de lo que ve cada cuenta se define por rol (Personas › Consultar: todos, área, asignados o propios), no por cuenta.

## D-043 — Antecedentes para todos los roles
**A pedido del Director (18/10/2026):** todos los roles pueden buscar si una persona ya tiene legajo (módulo «antecedentes», alcance siempre «todos»), por apellido y nombre o por documento. La respuesta muestra **solo** nombre, documento, fecha de carátula de cada caso y responsable: ni número de caso, ni estado, ni datos del legajo, ni acceso a documentos. Mínimo de 3 caracteres, hasta 20 personas, y cada consulta queda en la auditoría. Está en el menú (grupo «Antecedentes») y en el menú del celular. Se suma una vez a los roles existentes al actualizar.

## D-044 — Foto de la persona desde el DNI y documentación del caso abierto
**A pedido del Director (18/10/2026):** (1) del DNI cargado en el legajo se recorta la foto de la persona: el servidor busca la cara y **propone** un recorte; quien carga lo confirma o lo dibuja a mano arrastrando sobre la imagen. La foto (JPEG chico) queda en el legajo y se ve en su encabezado; solo la cambian quienes pueden modificar legajos y queda auditado. La detección usa el detector clásico de OpenCV 4 (sin red; OpenCV 5 no lo trae, por eso se fija `<5`) y **todavía no se calibró con DNI reales**: si no encuentra la cara, el recorte manual funciona igual. (2) Si la persona tiene un caso abierto, el legajo muestra **qué documentos requeridos hay y cuáles faltan** (presente, vencido o falta), lo que ya está cargado y los papeles pendientes del trámite de subsidios. Qué documentos se exigen lo marca la Dirección en la plantilla de cada tipo («Se exige en todo caso abierto»); de fábrica solo el DNI. No se inventó una lista de requisitos: la define la Dirección.

## D-045 — Novedades dirigidas por rol
**A pedido del Director (18/10/2026):** además de publicar para toda la Dirección o para un área, una novedad se puede dirigir a **uno o más roles** (por ejemplo, solo jefaturas de departamento). Con roles marcados, la reciben y la ven **solo** quienes tienen alguno de esos roles, dentro del destino elegido (toda la Dirección o un área); sin roles marcados nada cambia. La confirmación de lectura, el «leída por X de Y», los avisos del navegador, el inicio y las estadísticas cuentan únicamente a esos destinatarios; quien publica la ve siempre. Quien publica solo para su área (jefaturas) puede elegir roles pero únicamente dentro de su área. Tabla `novedades_roles` (migración 0032). La tarjeta muestra «Para: …». Los destinatarios se calculan al leer (si alguien cambia de rol después, cambia lo que recibe).

## D-046 — Chat interno
**A pedido del Director (18/10/2026):** mensajería interna dentro de SULAM (escritorio y celular): conversaciones **1 a 1** (una sola por par de personas) y **grupos** (nombre, hasta 50 personas; quien lo crea suma gente; cualquiera puede salir). Módulo de permisos «chat» (usar, alcance siempre «todos»); se suma a todos los roles existentes una sola vez y se puede quitar a un rol desde Administración. Cualquier persona activa puede escribirle a cualquier otra. **Privacidad:** solo ven una conversación quienes participan (ni la administración); la auditoría registra que se creó, se sumó o se borró algo, **nunca el texto**; cada uno puede borrar sus propios mensajes (queda «Mensaje borrado»); quien se suma a un grupo no ve lo anterior; texto plano de hasta 2000 caracteres. **Sin tiempo real:** la pantalla consulta cada 5 s (lista 8 s, insignia del menú 20 s) y los mensajes sin leer salen en los avisos del navegador sin el texto. Sin adjuntos ni referencias a legajos (a propósito: los datos de casos no deben circular por chat). Tablas `chat_conversaciones`, `chat_participantes`, `chat_mensajes` (migración 0032). **Para decidir con la Dirección:** si los mensajes son parte del registro institucional (y por cuánto tiempo se conservan) y si hace falta que alguien con autoridad pueda auditarlos; hoy no puede nadie.

## D-047 — Orden de salida en comisión
**A pedido del Director (18/10/2026):** desde cualquier actividad de la Agenda (salida, visita, entrevista, reunión, trámite, evento de Participación; no recordatorios) se descarga en Word la **orden de salida en comisión** completada sobre el formulario oficial de la Dirección (hoja oficio con tres órdenes: una por persona; si participan más de tres, se suman hojas). Se completan la fecha de emisión, el nombre de cada participante, la **tarjeta** (hoy se toma el «ID del reloj» de su ficha de personal; si la tarjeta es otro número habrá que cargarlo aparte), el día y la hora, el destino, el departamento, el objeto y la hora de regreso (solo si la actividad tiene hora de fin). Lo que no se sabe queda con los puntos originales. Las firmas son siempre en papel. En una salida de varias visitas es **una orden por persona con todos los domicilios del recorrido**. **Privacidad:** el objeto es genérico («Visitas domiciliarias a personas adultas mayores (N)»), sin nombres; el domicilio sale del legajo solo si quien descarga puede verlo; cada descarga queda auditada («comision_exportada»). La plantilla está en `backend/sulam/papel/comision_de_servicio.docx`: para cambiar el formulario se reemplaza ese archivo.

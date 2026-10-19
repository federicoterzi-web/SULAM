# Especificación funcional · SULAM 0.1

Reglas que el sistema **implementa hoy**. Lo que falta definir está en [DECISIONS.md](DECISIONS.md) (pendientes) y no se inventa: los campos de carátula y de registro de demanda, por ejemplo, se incorporarán cuando el relevamiento los establezca.

## 1. Legajo único

1. Cada persona mayor tiene **un único legajo** con:
   - identificador interno permanente (UUID), invisible para el usuario;
   - **número de legajo = DNI** (para otros documentos, con el tipo adelante: «LC 3456789»).
   - **Sin DNI**: el sistema asigna un número provisorio «SD-000001». Cuando se carga el DNI, el legajo pasa a ser el DNI y el número provisorio se conserva: sigue sirviendo para buscarlo (carpetas o papeles rotulados con él). Los cambios quedan en la auditoría.
2. Datos de identificación de la 0.1: apellidos, nombres, tipo y número de documento, situación sin documento (con motivo), fecha de nacimiento (exacta o aproximada), domicilio, localidad, teléfono y observaciones.
3. **Personas sin documento**: se registran marcando *sin documento*; no puede cargarse un número a la vez.
4. **Corrección de documento**: cambiar un número ya cargado exige indicar el motivo; queda en la auditoría con el valor anterior y el nuevo.
5. El número de documento se normaliza (se quitan puntos, espacios y guiones).
6. El legajo **no se elimina**. Puede **unificarse** con otro (ver §3.4).

## 2. Personas e instituciones vinculadas

1. Cada legajo puede tener familiares, referentes, convivientes, denunciantes, representantes, instituciones u otros vínculos (catálogo administrable).
2. Los vínculos no se borran: se marcan como no vigentes.

## 3. Duplicados y unificación

### 3.1. Al dar de alta o corregir identidad, el sistema busca legajos parecidos

| Criterio | Nivel | Efecto |
|---|---|---|
| Mismo tipo y número de documento | Bloqueante | No permite guardar |
| Mismo número con otro tipo de documento | Alta | Pide confirmación |
| Apellidos y nombres casi idénticos (≥ 90 %, sin tildes, en cualquier orden) | Alta | Pide confirmación |
| Nombre parecido (≥ 75 %) y misma fecha de nacimiento (o mismo año si es aproximada) | Alta | Pide confirmación |
| Mismo primer apellido y misma fecha de nacimiento | Media | Pide confirmación |

### 3.2. La búsqueda se hace mientras se completa el formulario, antes de guardar.
### 3.3. Para guardar con coincidencias no bloqueantes, el usuario confirma que revisó los legajos y puede indicar cómo lo verificó. La confirmación queda auditada con los legajos que se descartaron.
### 3.4. Unificación

- Requiere el permiso *Legajos › Administrar* con alcance *Todos*.
- Se elige el legajo que se conserva y el que se absorbe, con motivo obligatorio.
- Casos, expedientes, ingresos, documentos y vinculados pasan al legajo conservado.
- El legajo absorbido queda inactivo, conserva sus datos originales y redirige al vigente.
- Se registra en la auditoría de ambos legajos, con una copia de los datos del absorbido.

## 4. Mesa de Entrada

1. Un ingreso se registra **aunque todavía no exista el legajo**, con número correlativo anual (`ME-2026-00001`), fecha y hora automáticas, asunto, remitente, tipo, folios, persona y documento mencionados, número de expediente externo y observaciones.
2. Se puede adjuntar el escaneo al ingreso antes de vincularlo.
3. El sistema **sugiere legajos** por el documento mencionado o por coincidencia de apellidos.
4. Al **vincular** el ingreso a un legajo (y opcionalmente a un caso o expediente), sus documentos pasan al legajo. **Los datos originales del ingreso no se modifican**: se conserva el registro de origen. Si se corrige una vinculación, la anterior queda en la auditoría.
5. Desde un ingreso vinculado se puede abrir un caso nuevo, que queda asociado al ingreso.

## 5. Casos

1. Un caso es un período o proceso de intervención sobre una persona. Una persona puede tener varios.
2. Número correlativo anual (`C-2026-00001`), área, descripción breve y responsables.
3. **Estados**: Abierto, En seguimiento, Pausado, Cerrado.
   - Pausar, cerrar o reabrir exige **motivo**.
   - Cada cambio guarda estado anterior, nuevo, usuario, fecha y motivo. El historial nunca se modifica.
4. **Asignación**: uno o varios responsables. Reasignar finaliza la asignación anterior (con fecha y usuario) sin borrarla.
5. **Sin información reservada** (D-021): no hay casos, documentos ni vinculados reservados. Quien puede consultar un caso ve todo su contenido; modificarlo depende del alcance de su rol (por ejemplo, el técnico modifica solo sus casos asignados).
6. El tablero de cada usuario muestra sus casos activos asignados y señala los que llevan **más de 30 días sin movimientos**.

## 5. bis-0. Una actuación por persona por año; reiteraciones

- Si la persona ya tiene un caso (actuación) en el año, **no se abre otra carátula**: un nuevo ingreso se registra como **reiteración** de ese caso, con fecha, motivo y tipo de ingreso. Si el caso estaba cerrado, se reabre (queda en el historial de estados).
- «Nuevo caso» avisa al abrirse y ofrece «Registrar como reiteración».
- Un ingreso de Mesa de Entrada vinculado a una persona con caso en el año se asocia a ese caso como reiteración automáticamente.
- Excepción: solo Administración puede abrir otra actuación en el mismo año, con motivo (queda en la auditoría).
- Las reiteraciones se listan en el caso y se cuentan para estadísticas.

## 5 bis. Carátula de legajo y registro de demanda

Implementados según los modelos institucionales («Modelo de carátula de legajo» y «Registro de demanda», octubre 2026). Los textos de las opciones son los de los modelos (`backend/sulam/formularios.py`).

**Orden de carga** (como en la práctica de la Dirección):

1. **Carátula**: se completa al crear el caso. Contiene:
   - Legajo N° (automático) y **Actuación N° / año**: número correlativo de carátula por año, igual al número de caso (Actuación 351/2026 = caso C-2026-00351). Se asigna solo.
     - Para continuar la numeración que se llevaba en papel, Administración fija el próximo número del año (no puede ser menor o igual al mayor registrado).
     - Una carátula anterior puede cargarse con su número original; el sistema impide repetirlo y la numeración automática saltea los números ya usados.
     - Una vez creada, la Actuación N° no se modifica.
   - Datos de la persona: género, obra social / cobertura de salud, CUD, domicilio, localidad, departamento y teléfono. **Estos datos actualizan el legajo** (con auditoría).
   - Información administrativa: fecha de ingreso, antecedentes y fecha del último ingreso, motivo de ingreso, tipo de ingreso (Espontáneo presencial/no presencial, Mesa de Entrada/Amparo, Portal SAE, Derivada), indicadores y tipo de intervención (con texto para «Derivación» y «Otro»).
   - **Antecedentes**: si no se indican, se completan con los ingresos previos registrados en SULAM. Si la carátula dice «No» y el sistema encuentra un ingreso anterior, se muestra un aviso.
2. **Registro de demanda**: se carga después, sobre el caso, y llega **precargado** con la carátula (indicadores, intervenciones, tipo de ingreso, motivo como solicitud expresa) y con el legajo (género, teléfono, domicilio, coberturas, CUD, discapacidad). Secciones 1 a 8 del modelo, observaciones, lugar y fecha. El **receptor** es el usuario que lo carga.
   - Los datos que también pertenecen al legajo lo actualizan (se puede desmarcar).
   - Guarda una copia de los datos de identificación de la persona al momento del registro.
   - Un caso puede tener más de un registro.
3. **Evolución del caso**: cada entrada tiene la **fecha de la intervención** y **quién la realizó** (usuario de SULAM u otra persona), y por separado quién la cargó y cuándo. Se ordenan por fecha de intervención. No se editan ni se borran.

**Carga desde papel.** Lo habitual es que los formularios se completen y firmen en papel y otra persona los transcriba:
- El registro de demanda distingue el **receptor** (quien recibió la demanda y firma; usuario de SULAM u otra persona) de **quien lo cargó**. La fecha es la del formulario.
- Se adjunta el **escaneo del original firmado** al registro de demanda y a la carátula; la lista de registros señala los que tienen escaneo pendiente.
- La impresión aclara que es una transcripción del original en papel y quién la cargó.
- El rol Carga de Datos puede transcribir carátulas, registros y evoluciones.


**Carátula para carpeta**: versión de lectura rápida para la carpeta física. Muestra solo lo cargado y destaca lo importante: N° de actuación grande, nombre, legajo (DNI), edad; en blanco y negro y sin rellenos (poca tinta): alertas graves —maltrato, negligencia, situación de calle— en mayúsculas, negrita, con ▲ y borde doble; antecedentes, reiteraciones; motivo, ingreso, intervención, domicilio, cobertura y responsables. Lleva un QR que abre el caso en SULAM (no contiene datos personales; requiere iniciar sesión).

**Impresión**: la carátula y el registro de demanda (con la evolución) tienen una vista imprimible en A4 con la estructura de los modelos y las casillas marcadas (☒/☐).

Al marcar una subopción (por ejemplo «Maltrato › Económico/Patrimonial») se guarda también el grupo, para poder contar después por grupo o por subtipo.

## 5 ter. Fichas en papel con lectura automática

SULAM genera las fichas oficiales en papel (*Fichas en papel* en el menú, o `sulam fichas`):

| Ficha | Hojas | Uso |
|---|---|---|
| Carátula de legajo | 1 | Al ingresar el caso |
| Registro de demanda | 2 | Después de la primera verificación |
| Hoja de evolución | 1 (5 intervenciones) | Registro manual de intervenciones; se usan las que hagan falta |

- Mismos campos y textos que los modelos de la Dirección; las opciones se imprimen desde el mismo catálogo que usa la pantalla.
- Cada hoja lleva **cuatro marcas de esquina**, un **QR** (ficha, versión y hoja), **casillas** para marcar con X y **cuadrículas de un dígito por casilla** para DNI, fechas, teléfonos y números de legajo y actuación.
- Todas las hojas llevan **Legajo N° (DNI)** con 8 casilleros y la casilla «Sin DNI», y **Actuación N° / año**, para asociarlas al caso.
- En años y fechas, el siglo va preimpreso («20» para fechas del trámite, «19» para la fecha de nacimiento): se completan solo los dos últimos dígitos.
- **Lectura** (`sulam/papel/lectura.py`): ubica las marcas, endereza la foto (perspectiva y giro, incluso al revés), identifica la hoja por el QR y mide cada casilla. Las casillas con poca tinta o los grupos de opción única con más de una marca se marcan como **dudosos** para revisión. Recorta cada celda de dígitos y cada recuadro de texto para la revisión humana.
- Validación con 60 fotos simuladas (perspectiva, giros, sombra, ruido, desenfoque): 60/60 hojas leídas y 0 errores en 1.815 casillas.
- **Pendiente**: captura con el celular por QR, pantalla de revisión campo por campo, reconocimiento de dígitos y de texto (solo local, D-018), y lectura de las fichas anteriores sin marcas.

## 5 octies. Red de recursos y mapa

*Recursos y mapa* reúne centros de día, centros de jubilados, residencias de larga estadía, instituciones con las que se articula (salud, municipios y comunas, desarrollo social, justicia, seguridad, educación, organizaciones sociales) y cuidadores domiciliarios formados.

- Cada recurso tiene tipo, nombre, dirección, localidad, departamento, ubicación en el mapa, teléfonos, correo, horario, referente, servicios y observaciones. Los cuidadores, además, los departamentos donde trabajan, su formación y su disponibilidad; para ellos se marca su domicilio, para saber quién vive cerca de cada caso.
- Mapa con un color y una letra por tipo; lista al costado con llamar y «cómo llegar». Filtros por tipo, departamento (un cuidador aparece también donde trabaja) y texto.
- La ubicación se marca tocando el mapa o con «Buscar la dirección», que consulta OpenStreetMap (Nominatim) **solo para recursos**; los domicilios de los casos nunca se envían a servicios externos. Configurable (`SULAM_MAPA_TESELAS`, `SULAM_GEOCODIFICADOR_URL`, vacío = desactivado).
- En el celular: pestaña *Recursos* con búsqueda, filtros, llamar, cómo llegar y mapa.
- Permisos (módulo «recursos»): consultan todos los roles iniciales; cargan Dirección, jefaturas, Carga de Datos, técnicos y administrativos de área; técnicos y administrativos de área modifican solo lo que cargaron. Las bajas son lógicas y todo cambio queda en la auditoría.

## 5 nonies. Directorio de contactos

Técnicos de municipios y comunas y referentes de otras instituciones: nombre, cargo, institución (opcionalmente vinculada a un recurso del mapa), tipo de institución, localidad, departamento, teléfonos, WhatsApp, correo, temas con los que se articula y observaciones. Búsqueda por nombre, institución, cargo, localidad o tema; filtros por departamento y tipo. Botones para llamar, escribir por WhatsApp (el número se normaliza: «381 15 400-1111» → 5493814001111) y enviar correo. La ficha de cada institución del mapa muestra sus contactos. En el celular, *Recursos › Contactos*. Mismos permisos que la red de recursos; quien deja la institución se da de baja, no se borra.

### Base institucional desde todas las fuentes

Contactos y recursos registran **cómo se obtuvo el dato**: relevamiento de la Dirección, capacitación (Participación y Sensibilización Ciudadana), articulación en un caso, derivación o nota recibida, referencia de otra institución u otro, con un detalle (por ejemplo, el nombre y la fecha de la capacitación).

**Articulación en casos**: cada caso tiene la sección *Articulación con otras instituciones* (fecha, con quién, motivo y resultado). Se elige un contacto del directorio o, si no está, se lo agrega en el momento: queda en el directorio con origen «Articulación en un caso» y el número de actuación. El directorio muestra en cuántos casos se articuló con cada contacto. Registrar requiere poder modificar el caso; queda en la auditoría.

## 5 decies. Casos en el mapa y salidas de visita

- **Ubicación del domicilio** (legajo): se marca en el mapa o, durante una visita, con «Estoy en el domicilio: usar mi ubicación» (GPS del celular). Nunca se consulta a servicios externos con domicilios de casos. Queda en la auditoría.
- **Mapa de casos** (*Mapa de casos y salidas*; en el celular desde el inicio): casos activos con ubicación, de «Mis casos», «Mi área» o «Todos», a la vista de todos los técnicos. Rojo: maltrato; naranja: sin movimiento hace más de 30 días. Se pueden mostrar también los recursos.
- **Salida**: se eligen los casos a visitar; SULAM sugiere el orden (vecino más cercano y mejora 2-opt, en línea recta desde el punto de partida `SULAM_PUNTO_PARTIDA`, o desde la ubicación del celular), muestra los kilómetros aproximados, abre el recorrido en Google Maps (en tramos si son más de 10 paradas) e imprime la **hoja de salida** (orden, persona, domicilio, teléfono, caso, responsables y espacio para hora y observaciones).
- Los casos sin ubicación se listan para completarlos.

## 5 decies bis. Orden de salida en comisión
Desde el detalle de una actividad de la Agenda (o de un evento de Participación) se descarga en Word la **orden de salida en comisión**, completada sobre el formulario oficial de la Dirección: una orden por persona que participa (tres por hoja oficio). Lleva fecha de emisión, nombre, tarjeta (ID del reloj de la ficha de personal), día y hora, destino, departamento, objeto y regreso; lo que no se conoce queda con los puntos para completar a mano, y las firmas son en papel. En una salida de visitas, cada orden incluye todos los domicilios del recorrido. El objeto es genérico, sin nombres de personas visitadas, y el domicilio solo aparece si quien descarga puede ver el legajo. Cada descarga se audita. Ver D-047.

## 5 septies. Página de inicio por rol

Cada rol tiene una página de inicio (se elige en *Administración › Roles*). Quien tiene varios roles puede cambiar de inicio; SULAM recuerda el último elegido en ese navegador. Todo respeta el alcance de consulta de cada rol.

| Inicio | Roles iniciales | Qué muestra |
|---|---|---|
| Dirección | Directora; Dirección y Administración | Año en curso: actuaciones nuevas, reiteraciones, activos y cerrados, en total y por departamento; maltrato del mes por tipo; casos sin responsable y sin movimiento; actividad reciente |
| Jefatura | Jefe/a de departamento; Jefe/a de división | Su área: casos sin responsable (para asignar), equipo con su carga de casos, casos sin movimiento, actuaciones y reiteraciones del mes, carátulas por imprimir |
| Técnico/a | Técnico | Sus casos por urgencia (maltrato, volvió a consultar en los últimos 30 días, sin movimiento, asignado esta semana) con la última evolución |
| Carga de datos | Carga de Datos | Casos sin registro de demanda, registros desde papel sin escaneo, carátulas por imprimir, lo cargado hoy |
| Mesa de Entrada | Mesa de Entrada | Ingresos de hoy, ingresos sin vincular, sus últimos ingresos |
| Administrativo de área | Administrativo de Área | Casos del área, expedientes recientes, documentos que cargó, carátulas por imprimir |

Roles nuevos (propuesta, editables): **Directora** (ve todo, incluida la auditoría; no administra usuarios), **Jefe/a de departamento** y **Jefe/a de división** (mismos permisos; el departamento o la división sale del área del usuario: Participación y Sensibilización Ciudadana, Cuidados y Promoción de Autonomía, o quien cumple esa función en un departamento).


**Revisión del 17/10/2026**
- Dirección: columna «sin técnico» por departamento (enlaza a la lista filtrada), informes firmados en el mes y actividad reciente compacta; sin listas largas.
- Jefaturas: el equipo (casos por persona) arriba; «Para asignar» con los 10 más antiguos y botón **Asignar equipo** en cada fila; enlace a la lista completa.
- Técnico/a: bloque **Para terminar** con sus informes en borrador y los casos sin registro de demanda.
- Carga de datos: primero los casos que ya tienen técnico a cargo; listas de 10.
- Celular: inicio propio de cada perfil (números clave y su lista principal). «Agregar un lugar al mapa» solo para técnicos, jefaturas y Dirección. «Mis casos» muestra solo casos activos.
- **Los vencimientos (negativa de ANSES, CUD y similares) no se muestran en los inicios**: si corresponde renovarlos depende del caso; se ven solo en el legajo.
## 5 sexies. Membrete institucional

Las impresiones en **formato oficial** (carátula de legajo y registro de demanda) llevan el membrete de la Dirección (Ministerio de Desarrollo Social · Dirección de Adultos Mayores · Gobierno de Tucumán), centrado y del mismo tamaño que en el modelo de Word (11,3 × 2,5 cm). La carátula para carpeta y las fichas para escanear no lo llevan: la primera es de bajo consumo de tinta y en las fichas el logo podría confundir la lectura automática. Para actualizar el membrete se reemplaza `frontend/src/recursos/membrete-2024.jpg`.

## 5 quinquies. Impresión de carátulas en tanda

- Todo caso nuevo (cargado en la computadora o en el celular) queda **pendiente de impresión** de su carátula.
- *Imprimir carátulas* lista las pendientes: las que creó el usuario, las de su área o todas (según sus permisos de consulta), en orden de actuación. Por defecto vienen todas elegidas; se pueden destildar.
- Se imprimen juntas, una por hoja, en formato para carpeta o en formato oficial.
- Después de imprimir, SULAM pregunta si salieron bien: al confirmar, salen de la cola. Si no, se vuelven a imprimir.
- Cada impresión queda en la auditoría; la fecha de la **primera** impresión se guarda en el caso y se muestra en su carátula. Imprimir de nuevo desde el caso no lo vuelve a poner en la cola.

## 5 quater. Versión para celular

Misma aplicación, pantallas en `#/m` (D-020). Se abre sola al ingresar desde un teléfono; desde la versión completa se llega con *Versión para celular* y a la inversa con *Ver en la versión completa*.

- **Inicio**: buscador (DNI, apellido o N° de legajo; botón para teclado numérico) y *Mis casos* (asignados); si no hay, los de actividad reciente.
- **Legajo**: datos de identificación y domicilio, botones para llamar a la persona y a sus vinculados con teléfono, casos. Si ya tiene actuación en el año ofrece *Nueva demanda (reiteración)*; si no, *Nueva carátula*.
- **Caso**: actuación, estado, indicadores y motivo, llamar, *Agregar evolución*, *Sacar fotos*, *Fotografiar registro de demanda* (si alguno no tiene escaneo) y *Registrar reiteración*; últimas entradas de evolución y documentos.
- **Nuevo caso**: DNI primero (avisa al instante si ya tiene legajo); opción sin DNI con número «SD-»; control de posibles duplicados con motivo obligatorio para confirmar. Sigue la **carátula en 6 pasos** (ingreso, persona, domicilio, indicadores, intervención, confirmar con resumen editable). El botón «atrás» del teléfono vuelve al paso anterior sin perder lo cargado. La actuación se numera al crear; si la persona ya tiene una en el año, se ofrece la reiteración (regla de §5).
- **Fotos**: una o varias hojas con la cámara (o elegidas del teléfono), reordenables; se guardan como **un PDF** asociado al legajo, al caso y, si corresponde, al registro de demanda como escaneo del original. Las fotos se reducen a 2000 px y se envían sin metadatos; el servidor vuelve a procesarlas (máx. 2400 px, sin EXIF) y muestra el avance del envío.
- **Todo se carga también desde el celular**, con los mismos formularios, reglas y permisos que la versión completa, adaptados a una columna con campos y botones grandes:
  - *Caso*: registro de demanda (nuevo y editar), articulación con otra institución (con alta de contacto), reiteración, cambiar estado, asignar/derivar, editar carátula y editar datos del caso. Muestra los registros de demanda y las articulaciones.
  - *Legajo*: editar datos personales, agregar y editar vinculados, vincular expediente, marcar la ubicación del domicilio.
  - *Mesa de Entrada*: registrar un ingreso desde el inicio.
  - *Recursos y contactos*: agregar y editar (quien puede según su rol), con «Estoy en el lugar: usar mi ubicación» para ubicar el recurso con el GPS.
  - Queda solo en la versión completa lo que es de oficina: administración, auditoría, impresión de carátulas y tableros.
- **Sesión**: las iniciadas desde el celular vencen a los 15 minutos sin uso. Al vencer cualquier sesión con la pantalla abierta, se pide la contraseña encima y se conserva lo escrito.
- **Sin conexión**: aviso; no se guardan datos en el teléfono.
- **QR de la carátula para carpeta**: lleva un enlace `#/c/<id interno del caso>`, sin datos personales. Escaneado con el celular abre el caso en la versión celular; desde una computadora, en la versión completa. Siempre pide iniciar sesión y respeta los permisos. La dirección del enlace es la oficial (`SULAM_URL_PUBLICA`, o `https://SULAM_DOMINIO`), sin importar desde qué computadora se imprima. Sin configurarla, se usa la dirección con que se abrió SULAM y, si es «localhost», la IP de red de la máquina; si tampoco se puede (Docker), la vista de impresión avisa que el QR no funcionará desde un celular.

## 5 undecies. Informes redactados en SULAM

- **Redactar informe** desde el caso (o desde el legajo, para notas sin caso), en computadora o celular. Se elige una plantilla: *Informe socioambiental*, *Informe social / de situación*, *Informe de seguimiento*, *Nota / oficio a otra institución* o *Documento en blanco*.
- La hoja se ve como el papel: membrete, área, lugar y fecha, destinatario (si corresponde), título, **datos de la persona completados solos** (nombre, nacimiento, edad, DNI, obra social, estado civil, domicilio, CUD, legajo, actuación, referente, vivienda, etc., tomados del legajo, del caso y del último registro de demanda) y secciones con guía de qué escribir.
- **Todo es agregable y quitable**: datos (de la lista o uno libre), secciones (las sugeridas de la plantilla o nuevas), firmantes. Las secciones se reordenan. Si el legajo cambió, *Actualizar datos con el legajo*.
- Texto con formato básico (negrita, cursiva, subrayado, listas). Lo pegado de Word o de una página se pega como texto. Panel **Insertar del caso**: motivo de ingreso, registro de demanda, evoluciones y articulaciones, para no volver a escribirlos.
- **Guardado automático** del borrador; si otra persona guardó cambios mientras tanto, no se pisan (se avisa).
- **Firmar**: genera el PDF (Arial/Liberation Sans, membrete, pie institucional y «Página n de m») y lo guarda en los documentos del caso con el tipo documental de la plantilla. Avisa antes las secciones vacías (no se imprimen) y los datos en blanco. Firmado, **no se modifica**: *Corregir (nueva versión)* abre un borrador nuevo del mismo informe; al firmarlo, la versión anterior queda como «reemplazada» y se conserva con su PDF.
- Vista previa en PDF del borrador en cualquier momento. Los borradores se pueden descartar.
- Permisos: lo ve quien puede consultar el caso; lo redacta, firma o corrige quien puede modificarlo (los mismos que escriben evoluciones).
- **Plantillas** (*Plantillas de informes*): la Dirección edita todas y crea generales; cada jefatura edita y crea las de su área (permiso `plantillas.modificar`, alcance «área»). Se definen datos, secciones con guía y texto inicial, título impreso, destinatario y tipo documental. Los cambios valen para informes nuevos.

## 5 duodecies. Equipo a cargo de un caso

- Un caso puede tener **varios técnicos a cargo, todos responsables por igual** (sin referente principal, decisión de la Dirección 17/10/2026). Todos lo ven en «Mis casos», en el mapa y pueden trabajarlo.
- Se eligen al crear la carátula (computadora y celular) y se cambian con **Equipo a cargo**: se marcan y desmarcan técnicos y se guardan los cambios de una vez, con motivo opcional. Requiere el permiso de asignar/derivar.
- El historial del caso conserva quién estuvo a cargo, desde y hasta cuándo.

## 5 terdecies. Certificación negativa de ANSES

- En el legajo y en el caso (computadora y celular): estado de la última negativa («no registra · vence …», «registra …», «vencida», «ANSES no la emitió» o «sin registrar»).
- **CUIL**: si el legajo no lo tiene, SULAM lo calcula del DNI y el género (con ambos prefijos si falta el género) para copiarlo con un toque. **Abrir ANSES** abre el servicio oficial (configurable con `SULAM_URL_NEGATIVA_ANSES`). SULAM **no consulta ANSES por su cuenta ni le envía datos**: la consulta la hace el técnico en su navegador.
- **Subir el PDF**: SULAM lee CUIL, fecha de emisión, código de validación y si registra o no; quien carga **revisa** y confirma el resultado. Si el CUIL del PDF no corresponde al DNI o al CUIL del legajo, no se guarda (es de otra persona). El PDF queda en los documentos (del caso, si se carga desde el caso) como «Certificación negativa ANSES», y el CUIL confirmado pasa al legajo.
- Vence a los 30 días de la emisión (`SULAM_DIAS_VIGENCIA_NEGATIVA`). «ANSES no emitió la negativa» se registra sin PDF.
- Permisos: la ve quien consulta el legajo; la registra quien puede cargar documentos en él. El CUIL y la negativa se pueden agregar como datos en los informes.
- La lectura automática se probó con PDF simulados: falta calibrarla con negativas reales.

## 5 quattuordecies. Novedades

- Página **Novedades** (menú, con la cantidad sin confirmar) que mezcla las de la **Dirección (para todos)** y las de **cada área** (cada persona ve las generales y las de su área). Filtros: todas, sin confirmar, de la Dirección, de las áreas.
- **Publican** la Directora y Dirección (para todos o para un área) y las jefaturas de departamento y de división (solo para su área); permiso `novedades.publicar`. Texto con formato, **circular adjunta** (PDF, JPG o PNG), opción de fijarla arriba.
- **Confirmación de lectura** («Leí y estoy al tanto»): una vez por persona, con fecha y hora. Quien publica ve «Leída por X de Y» y la lista de quién falta. Se puede publicar sin pedir confirmación.
- Las no confirmadas aparecen arriba del inicio de cada perfil, en computadora y celular. Retirar una novedad la oculta (queda registrada en la auditoría).

## 5 quindecies. Carpetas en papel y pases

- Cada legajo y cada expediente tiene registrada **dónde está su carpeta en papel**: en un área (p. ej., Oficina de Registro) o en poder de una persona. Se ve en el legajo, en el caso (línea compacta), en cada expediente («Dónde está») y en el celular.
- **Pedir la carpeta**: un toque (motivo opcional). Lo ve quien la tiene —o cualquiera de su área— en el inicio y en **Pases de carpetas**; al dársela toca **Entregado** y la carpeta pasa a quien la pidió. Si no puede, toca **No se puede** con el motivo.
- **Devolver a Registro** / **Pasar a…** (otra área o persona): lo confirma quien la recibe con **Recibido**.
- Un pase pendiente por carpeta. Quien la pidió puede cancelar. Cada movimiento queda en el historial de la carpeta y en la auditoría.
- Si todavía no se sabe dónde está, cualquiera la registra; corregir una ubicación ya registrada lo hace quien la tiene (o Administración).
- **Carga inicial**: en Pases de carpetas, cada área anota de una vez las carpetas que tiene pegando los números de legajo.
- Área nueva «Oficina de Registro» (nombre a confirmar con la Dirección).

## 5 sexdecies. Personal y asistencia (antes «Asistencia DAM»)

La app de asistencia en Google pasa a SULAM con **las mismas reglas fijas** (`sulam/asistencia.py`, mismos 22 casos de prueba).

- **Ficha de cada persona de la planta**: nombre, área, cargo, ID del reloj, boleta, períodos de alta. Puede vincularse a un usuario de SULAM o crearlo en el alta. El área de la ficha se refleja en el usuario. La **baja** desactiva el usuario y cierra sus sesiones; el **reingreso** lo reactiva. No se borra nada.
- **Horarios con vigencia**: cada versión tiene fecha de inicio, referencia y la marca «confirmado». Una versión nueva cierra la anterior.
- **Reloj**: se sube el «.xls» (tabla HTML). Primero hay vista previa: período, filas, errores e ID sin identificar con sugerencias por nombre. Se incorpora recién al confirmar. Un mismo archivo no se incorpora dos veces y el original se guarda.
- **Resumen** (pestaña principal de Personal): jornadas por período, con estado pendiente / revisado / justificado / aprobado automáticamente / sin datos. Personal **revisa** cada jornada pendiente con fundamento: «sin descuento», «mantener pendiente» o «proponer minutos» (nunca más que la diferencia técnica). La revisión queda atada a una huella del cálculo; si los datos cambian, vuelve a pendiente. No se ejecutan descuentos.
- **Justificativos** con los códigos de la app (CT, CE, CS, VAO, DF, C3, SESOP, LICENCIA, CAMBIO), por día completo o por tramo, con adjuntos. Se aplican al cargarse; pueden rechazarse con fundamento.
- **Pedidos (Mi asistencia)**: cada persona pide **licencia** (con tipo), **comisión** (con destino) o **cambio de horario** (con el nuevo horario), con certificado opcional. Lo **aprueba su jefatura** (de su área; nadie aprueba lo propio; la Dirección y la Directora, a todos). **Personal lo registra** y se convierte en justificativo, con los adjuntos copiados. En licencias por enfermedad, el motivo y el certificado los ven solo la persona, Personal y la Dirección; la jefatura aprueba sin verlos.
- **Quién está hoy**: «De licencia», «En comisión» o «Ausente con justificativo», sin motivos. Se muestra al armar el equipo de un caso, en las carpetas en papel y en el inicio de Personal.
- Nuevo rol **Personal**, con su inicio: pedidos para registrar, jornadas pendientes, horarios sin confirmar, personas sin ID del reloj y quién no está hoy. Las jefaturas ven en su inicio los pedidos para aprobar.
- Datos reales: **no van al repositorio**. Se importan en el servidor de la Dirección (etapa 2: importador desde la app de Google, informe mensual en PDF y Excel de incidencias).

## 5 septdecies. Filtros por cualquier campo

- En **Casos, Legajos, Expedientes, Mesa de Entrada, Recursos y Contactos** se puede filtrar por cualquier dato cargado: «+ Filtro» → campo → comparación → valor.
- Comparaciones según el tipo de dato: texto (contiene / no contiene / sin dato / con algún dato), opción (es / no es), listas como indicadores o coberturas (incluye alguno / incluye todos / no incluye), fechas y números (entre, con atajos: este mes, este año, 60 a 69 años…), sí/no.
- En casos se combinan datos del caso, del registro de demanda y de la persona (edad, género, departamento, coberturas, CUD, discapacidad, negativa de ANSES, dónde está la carpeta). En legajos, además, datos de sus casos (casos activos, área, técnico/a a cargo, indicadores).
- Los filtros se suman («y»), quedan como etiquetas que se tocan para cambiarlas y viajan en la dirección de la página: se pueden compartir y se usan desde Estadísticas. Se muestra el total de resultados.
- El catálogo de campos está en `sulam/filtros.py` (`GET /api/filtros/{lista}`); cada lista recibe los filtros en el parámetro `f`. Filtrar casos o legajos queda en la auditoría (qué campos, no los valores).

## 5 octodecies. Estadísticas

Menú **Estadísticas**, con dos pestañas, un período (con atajos) y, para la Dirección, el área:

- **Casos** (casos con fecha de ingreso en el período; admite todos los filtros de casos): ingresados, personas distintas, con maltrato, cerrados, activos hoy, reiteraciones; ingresos y cierres por mes; estado, área, técnico/a, tipo de ingreso, derivación; indicadores e intervenciones (grupo y detalle); edad, género, departamento, coberturas, CUD, discapacidad; vivienda, estado funcional, autonomía, estado civil e hijos según el último registro de demanda. Cada barra o número abre la lista de esos casos con los filtros equivalentes.
- **Funcionamiento interno**: carga de trabajo y tiempos (por técnico/a y por área, días hasta asignar, duración de los casos, sin movimiento), asistencia del personal (jornadas, incidencias por tipo, por área y por persona, licencias y comisiones, justificativos; hasta un año), circuitos administrativos (Mesa de Entrada y tiempo hasta vincular, pases de carpetas y demoras, dónde están las carpetas, informes firmados, documentos digitalizados) y comunicación interna (novedades y porcentaje de lectura confirmada).
- Alcance: Dirección y Directora ven todo; cada jefatura, su área. Personal ve solo la asistencia.
- **Descargas**: Excel (resumen, una hoja por bloque con fórmulas de totales y porcentajes, y el detalle caso por caso con autofiltro) e informe PDF con membrete. Quedan en la auditoría.
- En Personal › Resumen, **Excel de incidencias** con las 16 columnas de la app «Asistencia DAM».

## 5 undevicies. Avisos del navegador

Botón **Activar avisos** en la barra superior (y en el menú de la versión para celular). Cada persona lo activa en su navegador y recibe una notificación del sistema cuando, con SULAM abierto pero en otra pestaña o en segundo plano, aparece algo nuevo:

- casos asignados a la persona y, para quien deriva, casos activos sin asignar;
- novedades que piden confirmar lectura;
- carpetas para entregar o recibir;
- pedidos de personal para aprobar o registrar y respuestas a los pedidos propios.

El texto es siempre genérico (por ejemplo «Hay 2 carpetas para entregar»): nunca lleva nombres ni datos de personas, y los vencimientos del legajo no se avisan. Se consulta `GET /api/avisos` (solo identificadores) cada minuto y al volver a la pestaña; lo ya avisado se recuerda en el navegador, y al activar no se avisa lo que ya estaba pendiente. Con SULAM a la vista alcanzan los contadores del menú. El título de la pestaña muestra la cantidad pendiente. Requiere `localhost` o HTTPS. Las notificaciones con SULAM cerrado (push) quedan para cuando exista el servidor con HTTPS.

## 5 vicies. Digitalización de documentos con el celular

Menú **Digitalización de documentos** (y «Capturar documentos» en el celular), para quien puede cargar documentos:

1. **Fotos seguidas.** Se sacan o se suben todas las fotos que hagan falta (en el celular se achican antes de enviarlas y se les quitan los metadatos). Quedan en la **bandeja personal** de quien las sacó, que nadie más ve.
2. **Armar documentos.** Se tocan, en orden, las hojas de un mismo documento y se pulsa *Armar documento*: se indica el legajo (y el caso, si corresponde), el tipo y los datos que pide su plantilla. Las hojas se unen en un solo PDF y se guardan en el legajo. Las demás fotos siguen esperando para el siguiente documento. Se puede reordenar las hojas y descartar fotos (no se guardan).
3. **Tipo nuevo con plantilla.** Si el tipo no existe, se crea en el mismo paso: nombre, para qué sirve, si **caduca** (con vigencia habitual en meses, que sugiere el vencimiento desde la emisión), si lleva **número o código** y **otros datos propios** (texto, fecha o número). Cualquier usuario que carga documentos puede crearlo; queda auditado. La plantilla se aplica después a toda carga de ese tipo, también desde *Cargar documento* en el legajo; la Dirección puede desactivar tipos desde Administración › Catálogos.

Los datos de cada documento (emisión, vencimiento, número, datos propios) se ven **solo dentro del legajo**: «Vence dd/mm/aaaa» en verde, o «Vencido el…» en rojo. No hay avisos de vencimiento en las pantallas de inicio. Las fotos clasificadas quedan vinculadas al documento creado; el nombre del archivo y el resultado pasan por los mismos controles que cualquier documento (permisos por legajo, archivos idénticos, auditoría).

## 6. Expedientes

1. Actuación administrativa o judicial vinculada a la persona y, si corresponde, a uno de sus casos.
2. Datos: número (texto libre), tipo, organismo, carátula y observaciones.
3. Una persona puede tener varios expedientes. No puede vincularse un expediente al caso de otra persona.

## 7. Documentos

1. Formatos admitidos en la 0.1: **PDF, JPG y PNG**, validados por su contenido real. Tamaño máximo configurable (20 MB por defecto).
2. Cada documento tiene: identificador interno, legajo, caso o expediente opcional, ingreso de origen, tipo documental, título, descripción, nombre original, tamaño, SHA-256, usuario y fecha de carga.
3. **Archivos idénticos**: se aceptan, se avisa al usuario y no ocupan espacio adicional.
4. **Baja lógica** con motivo obligatorio y permiso específico: el documento deja de mostrarse, pero el archivo y su registro se conservan.
5. Cada descarga o visualización queda registrada.
6. **Fotos desde el celular**: varias fotos JPG/PNG (hasta 30 hojas) se unen en un único PDF al cargarlas (§5 quater); se aplican los mismos permisos y la misma auditoría que a cualquier documento.

## 8. Búsqueda

- **Buscador general** (barra superior): legajos por apellido/nombre (sin importar tildes ni orden), documento o número de legajo; casos por número; expedientes por número; ingresos por número o expediente externo. Solo devuelve lo que el usuario puede ver.
- Cada búsqueda queda registrada con el texto buscado.

## 9. Usuarios, roles y permisos

1. Cuentas individuales. La contraseña inicial la define un administrador y debe cambiarse en el primer ingreso.
2. Bloqueo temporal tras 5 intentos fallidos. Un administrador puede restablecer la contraseña (cierra las sesiones abiertas).
3. Desactivar un usuario cierra sus sesiones de inmediato.
4. Roles configurables desde el panel: módulo × acción × alcance (ver ARCHITECTURE.md). Un usuario puede tener varios roles.
5. El sistema **no permite quedar sin ningún administrador activo**.
6. **Roles iniciales** (editables; la matriz definitiva es institucional):

| Rol | Resumen de la propuesta |
|---|---|
| Dirección y Administración del Sistema | Todo, con auditoría y administración |
| Carga de Datos | Alta y actualización transversal de legajos, casos, expedientes y documentos |
| Técnico | Consulta general; modifica legajos, casos y documentos de sus casos asignados |
| Mesa de Entrada | Ingresos y su vinculación; consulta de legajos; alta de expedientes; documentos propios |
| Administrativo de Área | Consulta y carga documental limitada a los casos de su área |

## 10. Auditoría

1. Se registran **operaciones** (alta, modificación con valores anteriores y nuevos, cambios de estado, asignaciones, vinculaciones, unificaciones, bajas, cambios de permisos, ingresos y salidas del sistema) **y consultas** (apertura de legajos, casos e ingresos; búsquedas; descargas; consultas a la propia auditoría).
2. Cada fila guarda usuario, fecha y hora, acción, entidad, legajo afectado, detalle e IP.
3. La auditoría **no puede modificarse ni borrarse**, ni siquiera desde la base con el usuario de la aplicación.
4. En el legajo, la *Actividad* muestra las operaciones a cualquier usuario con acceso; las consultas de otros usuarios solo las ve quien tiene permiso de auditoría.

## 11. Respaldo

Un comando genera un respaldo completo y verificable (base + archivos + manifiesto con hashes). La restauración comprueba la integridad antes de reemplazar los datos.

## 12. Criterios de aceptación de la 0.1

Cada criterio del documento de diseño (§13.3) tiene una prueba automatizada:

| Criterio | Prueba |
|---|---|
| Registrar una persona sin generar duplicados evidentes | `test_registrar_persona_sin_duplicados_evidentes` |
| Asociar un ingreso previo a un legajo | `test_asociar_ingreso_previo_a_legajo` |
| Crear y cerrar un caso sin eliminar el historial | `test_crear_y_cerrar_caso_sin_eliminar_historial` |
| Vincular varios expedientes a una misma persona | `test_varios_expedientes_para_una_persona` |
| Adjuntar y recuperar un documento | `test_adjuntar_y_recuperar_documento` |
| Restringir una acción según los permisos del usuario | `test_restringir_acciones_segun_permisos`, `test_permisos_configurables_desde_panel` |
| Registrar la autoría de las operaciones | `test_registrar_autoria_de_las_operaciones`, `test_auditoria_inmutable` |
| Recuperar la información después de reiniciar | `test_recuperar_informacion_despues_de_reiniciar` |
| *(agregado)* Respaldo y restauración | `test_respaldo_y_restauracion` |
| *(agregado)* Sin información reservada (D-021) | `test_sin_informacion_reservada` |
| *(agregado)* Registro de consultas | `test_las_consultas_quedan_registradas` |

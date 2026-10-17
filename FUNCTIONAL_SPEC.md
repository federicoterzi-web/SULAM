# Especificación funcional · SULAM 0.1

Reglas que el sistema **implementa hoy**. Lo que falta definir está en [DECISIONS.md](DECISIONS.md) (pendientes) y no se inventa: los campos de carátula y de registro de demanda, por ejemplo, se incorporarán cuando el relevamiento los establezca.

## 1. Legajo único

1. Cada persona mayor tiene **un único legajo** con:
   - identificador interno permanente (UUID), invisible para el usuario;
   - **número de legajo** visible y correlativo (`L-000001`).
2. Datos de identificación de la 0.1: apellidos, nombres, tipo y número de documento, situación sin documento (con motivo), fecha de nacimiento (exacta o aproximada), domicilio, localidad, teléfono y observaciones.
3. **Personas sin documento**: se registran marcando *sin documento*; no puede cargarse un número a la vez.
4. **Corrección de documento**: cambiar un número ya cargado exige indicar el motivo; queda en la auditoría con el valor anterior y el nuevo.
5. El número de documento se normaliza (se quitan puntos, espacios y guiones).
6. El legajo **no se elimina**. Puede **unificarse** con otro (ver §3.4).

## 2. Personas e instituciones vinculadas

1. Cada legajo puede tener familiares, referentes, convivientes, denunciantes, representantes, instituciones u otros vínculos (catálogo administrable).
2. Un vinculado puede marcarse **reservado** (por ejemplo, la identidad de un denunciante): solo lo ven quienes tienen acceso a información reservada o un caso asignado de esa persona. Los demás ven que existe un vínculo de ese tipo, sin datos.
3. Los vínculos no se borran: se marcan como no vigentes.

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
5. **Casos reservados** (por ejemplo, denuncias de maltrato): cualquiera con acceso al legajo ve que el caso existe, su número, estado, área y responsables —para evitar intervenciones duplicadas— pero **no** su descripción, documentos, motivos de cambios de estado ni la carátula de sus expedientes. El contenido lo ven los responsables asignados, quien lo creó y quienes tienen el permiso *Información reservada › Consultar*.
6. El tablero de cada usuario muestra sus casos activos asignados y señala los que llevan **más de 30 días sin movimientos**.

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
   - Si se marca un indicador de **maltrato**, el sistema sugiere registrar el caso como reservado.
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

**Reserva**: en un caso reservado, quien no tiene acceso ve que existe un registro de demanda (fecha y receptor) pero no su contenido; tampoco ve indicadores, intervenciones ni la evolución.

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
- Todas las hojas llevan Legajo N° y Actuación N°/año, para asociarlas al caso.
- **Lectura** (`sulam/papel/lectura.py`): ubica las marcas, endereza la foto (perspectiva y giro, incluso al revés), identifica la hoja por el QR y mide cada casilla. Las casillas con poca tinta o los grupos de opción única con más de una marca se marcan como **dudosos** para revisión. Recorta cada celda de dígitos y cada recuadro de texto para la revisión humana.
- Validación con 60 fotos simuladas (perspectiva, giros, sombra, ruido, desenfoque): 60/60 hojas leídas y 0 errores en 1.815 casillas.
- **Pendiente**: captura con el celular por QR, pantalla de revisión campo por campo, reconocimiento de dígitos y de texto (solo local, D-018), y lectura de las fichas anteriores sin marcas.

## 6. Expedientes

1. Actuación administrativa o judicial vinculada a la persona y, si corresponde, a uno de sus casos.
2. Datos: número (texto libre), tipo, organismo, carátula y observaciones.
3. Una persona puede tener varios expedientes. No puede vincularse un expediente al caso de otra persona.

## 7. Documentos

1. Formatos admitidos en la 0.1: **PDF, JPG y PNG**, validados por su contenido real. Tamaño máximo configurable (20 MB por defecto).
2. Cada documento tiene: identificador interno, legajo, caso o expediente opcional, ingreso de origen, tipo documental, título, descripción, nombre original, tamaño, SHA-256, usuario y fecha de carga.
3. **Archivos idénticos**: se aceptan, se avisa al usuario y no ocupan espacio adicional.
4. **Reservados**: un documento es reservado si se marca así, si su tipo documental es reservado o si pertenece a un caso reservado.
5. **Baja lógica** con motivo obligatorio y permiso específico: el documento deja de mostrarse, pero el archivo y su registro se conservan.
6. Cada descarga o visualización queda registrada.

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
| Dirección y Administración del Sistema | Todo, con información reservada, auditoría y administración |
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
| *(agregado)* Información reservada | `test_caso_reservado_y_vinculado_reservado` |
| *(agregado)* Registro de consultas | `test_las_consultas_quedan_registradas` |

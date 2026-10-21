# SULAM · Expedientes del Ministerio (extensión de Chrome)

Lee la **Bandeja de Entrada** de la Dirección en el Sistema de Expedientes del Ministerio de Desarrollo Social
(`desarrollosocialtuc.gob.ar/seds`) y registra en SULAM:

- cada expediente, con sus datos y sus pases, en **Mesa y expedientes › Expedientes del Ministerio**;
- cada pase que **llegó a la Dirección** como **ingreso de Mesa de Entrada** (una sola vez por pase), con el
  beneficiario y su DNI para sugerir el legajo. La vinculación al legajo la confirma una persona, como con cualquier
  ingreso (así se respetan las reglas de reiteración).

## Qué hace y qué no

- Usa la sesión que la persona ya tiene abierta en el Sistema de Expedientes: **solo lee lo que esa persona puede ver**.
- **No recepciona, no da pases, no carga solicitudes** ni escribe nada en el Sistema de Expedientes.
- No guarda la contraseña del Ministerio. La clave de SULAM queda en el almacenamiento local de la extensión y se puede
  revocar desde SULAM en cualquier momento.
- Lee las páginas de a poco (3 a la vez, con pausas) para no cargar el servidor del Ministerio.

## Instalar (modo desarrollador)

1. En Chrome, abrir `chrome://extensions` y activar **Modo de desarrollador** (arriba a la derecha).
2. **Cargar extensión sin empaquetar** → elegir esta carpeta (`extension-expedientes`).
3. En SULAM: **Mesa y expedientes › Expedientes del Ministerio › Conectar la extensión de Chrome** → **Generar clave**
   y copiarla (se muestra una sola vez). Hace falta un usuario que pueda registrar ingresos de Mesa de Entrada.
4. Tocar el ícono de la extensión (la «S» verde) → pegar la dirección de SULAM (por ejemplo `http://localhost:8000`) y la
   clave → **Guardar y probar conexión**. Chrome pide permiso para que la extensión hable con esa dirección: aceptar.
5. Abrir la **Bandeja de Entrada** del Sistema de Expedientes. Arriba de la tabla aparece la franja de SULAM con el botón
   **Sincronizar con SULAM**; cada fila muestra si ya está en SULAM y con qué número de ingreso.

En la **Vista de Expediente** aparece la misma franja con **Enviar a SULAM / Actualizar en SULAM** para un solo expediente.

## Opciones

- **Registrar como ingresos los pases que llegaron desde**: los pases anteriores se guardan igual, pero no generan
  ingresos (sirve para no cargar de golpe todo lo viejo de la bandeja). Por defecto, 30 días atrás.
- **Sincronizar automáticamente al abrir la Bandeja de Entrada**: como máximo cada 15 minutos.

## Si algo no anda

- *«La bandeja muestra solo los expedientes de …»*: está activo el filtro «Mostrar los expedientes propios»; tocar
  «Mostrar todos los expedientes» para leer toda la oficina.
- *«La sesión del Sistema de Expedientes venció»*: volver a ingresar al Sistema y repetir.
- *«No se pudo conectar con SULAM»*: revisar que SULAM esté encendido y que la dirección sea la misma que se usa en el
  navegador.
- Si el Ministerio cambia sus pantallas, la lectura puede fallar: todo lo que depende de esas pantallas está en
  `parser.js`.

## Archivos

| Archivo | Qué hace |
|---|---|
| `manifest.json` | Declaración de la extensión (Manifest V3) |
| `parser.js` | Lectura de la bandeja y de la vista de expediente (funciones puras) |
| `content.js` | Franja de SULAM en las pantallas del Ministerio, sincronización por lotes |
| `background.js` | Configuración y llamadas a la API de SULAM (la clave nunca llega a la página del Ministerio) |
| `opciones.html`, `opciones.js` | Pantalla de configuración |

API de SULAM que usa (con `Authorization: Bearer <clave>`): `GET /api/integracion/yo`,
`POST /api/integracion/ministerio/sincronizar`, `GET /api/integracion/ministerio/estado?claves=…`.

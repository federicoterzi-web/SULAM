// Service worker de SULAM.
// Permite instalar SULAM como app en el celular. A propósito NO guarda en el
// teléfono datos de personas ni respuestas de la API: todo se pide siempre al
// servidor. Sin conexión solo se muestra un aviso.
const AVISO_SIN_CONEXION = `<!doctype html><html lang="es-AR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SULAM · Sin conexión</title>
<style>body{font-family:system-ui,sans-serif;background:#f4f5f7;color:#1d2430;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;text-align:center}
button{font:inherit;font-size:1.1rem;padding:14px 22px;border-radius:8px;border:0;background:#1f4e79;color:#fff}</style></head>
<body><main><h1>Sin conexión</h1><p>SULAM necesita internet: los datos no se guardan en el teléfono.</p>
<p>Lo que estaba escribiendo sigue en la pantalla anterior; vuelva atrás y guárdelo cuando tenga señal.</p>
<button onclick="location.reload()">Reintentar</button></main></body></html>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return; // el resto va directo a la red, sin caché
  e.respondWith(
    fetch(e.request).catch(
      () => new Response(AVISO_SIN_CONEXION, { headers: { "Content-Type": "text/html; charset=utf-8" } }),
    ),
  );
});

// Aviso tocado (notificaciones del navegador): se trae SULAM al frente y se abre la sección.
// El texto de los avisos es genérico; no incluye datos de personas.
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const ruta = (e.notification.data && e.notification.data.ruta) || "/";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ventanas) => {
      const v = ventanas[0];
      if (v) {
        v.postMessage({ tipo: "sulam:ir", ruta });
        return v.focus();
      }
      return self.clients.openWindow("/#" + ruta);
    }),
  );
});

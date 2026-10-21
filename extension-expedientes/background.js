// Service worker: guarda la configuración y habla con la API de SULAM.
// Las pantallas del Ministerio nunca ven la clave: solo piden «enviá esto a SULAM».
"use strict";

const PREDETERMINADA = { url: "", token: "", desde: "", auto: false };

async function configuracion() {
  const c = await chrome.storage.local.get(PREDETERMINADA);
  if (!c.desde) {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    c.desde = d.toISOString().slice(0, 10);
  }
  c.url = (c.url || "").trim().replace(/\/+$/, "");
  return c;
}

async function api(metodo, ruta, cuerpo) {
  const c = await configuracion();
  if (!c.url || !c.token) throw new Error("Falta configurar la extensión: dirección de SULAM y clave.");
  let r;
  try {
    r = await fetch(c.url + "/api" + ruta, {
      method: metodo,
      headers: {
        Authorization: "Bearer " + c.token,
        ...(cuerpo !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
      credentials: "omit",
    });
  } catch (e) {
    throw new Error(`No se pudo conectar con SULAM en ${c.url}. ¿Está encendido? ¿La dirección es correcta?`);
  }
  let datos = null;
  try {
    datos = await r.json();
  } catch (e) {
    datos = null;
  }
  if (!r.ok) {
    const d = datos && datos.detail;
    const texto = typeof d === "string" ? d : d && d.mensaje ? d.mensaje : Array.isArray(d) ? d.map((x) => x.msg).join(" · ") : `Error ${r.status}`;
    throw new Error(`SULAM: ${texto}`);
  }
  return datos;
}

chrome.runtime.onMessage.addListener((msg, _remitente, responder) => {
  (async () => {
    try {
      if (msg.tipo === "config") {
        const c = await configuracion();
        return { ok: true, datos: { url: c.url, configurada: !!(c.url && c.token), desde: c.desde, auto: !!c.auto } };
      }
      if (msg.tipo === "api") {
        return { ok: true, datos: await api(msg.metodo || "GET", msg.ruta, msg.cuerpo) };
      }
      if (msg.tipo === "marcarSincronizado") {
        await chrome.storage.local.set({ ultimaSincronizacion: Date.now() });
        return { ok: true };
      }
      if (msg.tipo === "ultimaSincronizacion") {
        const { ultimaSincronizacion } = await chrome.storage.local.get({ ultimaSincronizacion: 0 });
        return { ok: true, datos: ultimaSincronizacion };
      }
      if (msg.tipo === "abrirOpciones") {
        await chrome.runtime.openOptionsPage();
        return { ok: true };
      }
      return { ok: false, error: "Mensaje desconocido." };
    } catch (e) {
      return { ok: false, error: e && e.message ? e.message : String(e) };
    }
  })().then(responder);
  return true; // respuesta asíncrona
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());

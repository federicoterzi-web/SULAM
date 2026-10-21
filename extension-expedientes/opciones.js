"use strict";

const $ = (id) => document.getElementById(id);

function mostrar(texto, tipo) {
  const e = $("estado");
  e.textContent = texto;
  e.className = tipo;
}

async function cargar() {
  const c = await chrome.storage.local.get({ url: "", token: "", desde: "", auto: false });
  $("url").value = c.url;
  $("token").value = c.token;
  if (!c.desde) {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    c.desde = d.toISOString().slice(0, 10);
  }
  $("desde").value = c.desde;
  $("auto").checked = !!c.auto;
}

$("form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  let origen;
  try {
    const u = new URL($("url").value.trim());
    origen = `${u.protocol}//${u.host}/*`;
  } catch (e) {
    mostrar("La dirección de SULAM no es válida (ejemplo: http://localhost:8000).", "error");
    return;
  }
  // El permiso para hablar con SULAM se pide en el mismo clic (Chrome lo exige así).
  chrome.permissions.request({ origins: [origen] }, async (otorgado) => {
    if (!otorgado) {
      mostrar("Sin ese permiso la extensión no puede enviar datos a SULAM.", "error");
      return;
    }
    await chrome.storage.local.set({
      url: $("url").value.trim().replace(/\/+$/, ""),
      token: $("token").value.trim(),
      desde: $("desde").value,
      auto: $("auto").checked,
    });
    const r = await chrome.runtime.sendMessage({ tipo: "api", ruta: "/integracion/yo" });
    if (!r || !r.ok) {
      mostrar((r && r.error) || "No se pudo probar la conexión.", "error");
      return;
    }
    const yo = r.datos;
    mostrar(
      `Conectado a SULAM como ${yo.nombre} (${yo.usuario}).` +
        (yo.puede_cargar ? " Ya puede abrir la Bandeja de Entrada y sincronizar." : " Atención: su usuario no puede registrar ingresos de Mesa de Entrada."),
      yo.puede_cargar ? "ok" : "error",
    );
  });
});

cargar();

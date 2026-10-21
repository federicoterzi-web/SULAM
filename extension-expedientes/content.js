// Se ejecuta en las pantallas del Sistema de Expedientes del Ministerio.
// Lee la bandeja y los expedientes con la sesión abierta de la persona (solo lectura)
// y le pide al service worker que los envíe a SULAM.
(function () {
  "use strict";
  const P = globalThis.SulamParser;
  const LOTE = 25;
  const SIMULTANEOS = 3;
  const AUTO_CADA_MS = 15 * 60 * 1000;

  // ------------------------------------------------------------------ utilidades

  async function pedir(msg) {
    const r = await chrome.runtime.sendMessage(msg);
    if (!r || !r.ok) throw new Error((r && r.error) || "La extensión no respondió.");
    return r.datos;
  }

  function el(etiqueta, props, ...hijos) {
    const e = document.createElement(etiqueta);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null) e.setAttribute(k, v);
    }
    for (const h of hijos.flat()) if (h !== null && h !== undefined && h !== false) e.append(h);
    return e;
  }

  const espera = (ms) => new Promise((r) => setTimeout(r, ms));

  async function enParalelo(items, n, f) {
    const res = new Array(items.length);
    let i = 0;
    const trabajador = async () => {
      while (i < items.length) {
        const k = i++;
        res[k] = await f(items[k], k);
        await espera(120); // no apurar al servidor del Ministerio
      }
    };
    await Promise.all(Array.from({ length: Math.min(n, items.length) }, trabajador));
    return res;
  }

  function enlaceSulam(conf, ruta, texto) {
    return el("a", { href: `${conf.url}/#${ruta}`, target: "_blank", rel: "noopener" }, texto);
  }

  // ------------------------------------------------------------------ panel

  function crearPanel(antesDe) {
    const panel = el("div", { class: "sulam-panel", role: "region", "aria-label": "SULAM" });
    const titulo = el("strong", {}, "SULAM");
    const estado = el("span", { class: "sulam-estado" }, "");
    const acciones = el("span", { class: "sulam-acciones" });
    panel.append(titulo, estado, acciones);
    antesDe.parentNode.insertBefore(panel, antesDe);
    return {
      panel,
      texto(t, tipo) {
        estado.textContent = t;
        estado.className = "sulam-estado" + (tipo ? " sulam-" + tipo : "");
      },
      acciones,
    };
  }

  function insignia(conf, r) {
    if (!r) return el("span", { class: "sulam-insignia sulam-nuevo", title: "Todavía no está en SULAM" }, "No está en SULAM");
    const partes = [];
    if (r.ingresos && r.ingresos.length) {
      const ultimo = r.ingresos[r.ingresos.length - 1];
      partes.push(enlaceSulam(conf, `/mesa/${ultimo.id}`, ultimo.numero));
    } else {
      partes.push(el("span", { title: "Guardado en SULAM; el pase llegó antes de la fecha desde la que se cargan ingresos" }, "En SULAM"));
    }
    if (r.persona) {
      partes.push(" · ", enlaceSulam(conf, `/legajos/${r.persona.id}`, "Legajo " + r.persona.numero_legajo));
    } else if (r.persona_sugerida) {
      partes.push(" · ", el("span", { title: "Hay un legajo con ese DNI: vincular desde el ingreso" }, "legajo sugerido"));
    }
    return el("span", { class: "sulam-insignia sulam-ok" }, ...partes);
  }

  function marcarFilas(conf, filas, estados) {
    for (const f of filas) {
      if (!f.fila || !f.fila.cells.length) continue;
      const celda = f.fila.cells[0];
      celda.querySelectorAll(".sulam-insignia").forEach((x) => x.remove());
      celda.append(insignia(conf, estados[f.clave]));
    }
  }

  async function estados(claves) {
    const res = {};
    for (let i = 0; i < claves.length; i += 100) {
      const parte = claves.slice(i, i + 100);
      Object.assign(res, await pedir({ tipo: "api", ruta: "/integracion/ministerio/estado?claves=" + encodeURIComponent(parte.join(",")) }));
    }
    return res;
  }

  // ------------------------------------------------------------------ bandeja de entrada

  async function iniciarBandeja() {
    const b = P.bandeja(document, location.href);
    const ancla = document.getElementById("tramitesEnMiOficinaPaginado") || document.querySelector("form[action*='tramitesList']");
    if (!ancla) return;
    const ui = crearPanel(ancla);
    let conf;
    try {
      conf = await pedir({ tipo: "config" });
    } catch (e) {
      ui.texto(e.message, "error");
      return;
    }
    if (!conf.configurada) {
      ui.texto("Falta configurar la extensión (dirección de SULAM y clave).", "aviso");
      ui.acciones.append(el("button", { type: "button", class: "sulam-boton", onclick: () => pedir({ tipo: "abrirOpciones" }) }, "Configurar"));
      return;
    }
    const boton = el("button", { type: "button", class: "sulam-boton sulam-primario" }, "Sincronizar con SULAM");
    boton.addEventListener("click", () => sincronizar(conf, ui, boton, false));
    ui.acciones.append(boton);

    if (!b.esDeLaOficina) {
      ui.texto(`La bandeja muestra solo los expedientes de ${b.titulo}. Para leer los de toda la oficina, toque «Mostrar todos los expedientes».`, "aviso");
    } else {
      ui.texto(`${b.total} expedientes en ${b.oficina || "la oficina"}. Ingresos nuevos desde el ${fechaLocal(conf.desde)}.`);
    }
    try {
      marcarFilas(conf, b.filas, await estados(b.filas.map((f) => f.clave)));
    } catch (e) {
      ui.texto(e.message, "error");
      return;
    }
    if (conf.auto && b.esDeLaOficina) {
      const ultima = await pedir({ tipo: "ultimaSincronizacion" });
      if (Date.now() - ultima > AUTO_CADA_MS) sincronizar(conf, ui, boton, true);
    }
  }

  function fechaLocal(iso) {
    const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
  }

  let ocupado = false;

  async function sincronizar(conf, ui, boton, automatico) {
    if (ocupado) return;
    const b0 = P.bandeja(document, location.href);
    if (!b0.esDeLaOficina && !automatico) {
      const seguir = confirm(
        "La bandeja muestra solo sus expedientes propios. Para leer toda la oficina, cancele y toque «Mostrar todos los expedientes».\n\n¿Sincronizar igual solo estos?",
      );
      if (!seguir) return;
    }
    ocupado = true;
    boton.disabled = true;
    try {
      // 1. Todas las páginas de la bandeja.
      const filas = new Map();
      for (const f of b0.filas) filas.set(f.clave, f);
      for (let p = 1; p <= b0.paginas; p++) {
        ui.texto(`Leyendo la bandeja: página ${p} de ${b0.paginas}…`);
        const doc = await P.traer(new URL(`tramitesList.do?page=${p}`, location.href).toString());
        const b = P.bandeja(doc, location.href);
        for (const f of b.filas) if (!filas.has(f.clave)) filas.set(f.clave, { ...f, fila: null });
      }
      const lista = Array.from(filas.values());
      const completa = b0.esDeLaOficina && lista.length >= b0.total;

      // 2. El detalle (datos y pases) de cada expediente.
      let leidos = 0;
      const expedientes = await enParalelo(lista, SIMULTANEOS, async (f) => {
        try {
          const exp = P.expediente(await P.traer(f.url), location.href);
          return exp ? { clave: exp.clave, url: exp.url, en_bandeja: true, bandeja: f.bandeja, detalle: exp.detalle, movimientos: exp.movimientos } : null;
        } catch (e) {
          if (/sesión/i.test(e.message)) throw e;
          return { clave: f.clave, url: f.url, en_bandeja: true, bandeja: f.bandeja, movimientos: [] };
        } finally {
          leidos++;
          ui.texto(`Leyendo expedientes: ${leidos} de ${lista.length}…`);
        }
      });
      const validos = expedientes.filter(Boolean);

      // 3. Envío a SULAM por lotes.
      let creados = 0;
      const nuevos = [];
      const estadoPorClave = {};
      for (let i = 0; i < validos.length; i += LOTE) {
        ui.texto(`Enviando a SULAM: ${Math.min(i + LOTE, validos.length)} de ${validos.length}…`);
        const ultimo = i + LOTE >= validos.length;
        const r = await pedir({
          tipo: "api",
          metodo: "POST",
          ruta: "/integracion/ministerio/sincronizar",
          cuerpo: {
            oficina: b0.oficina,
            crear_ingresos_desde: conf.desde || null,
            expedientes: validos.slice(i, i + LOTE),
            claves_en_bandeja: ultimo && completa ? lista.map((f) => f.clave) : null,
          },
        });
        creados += r.ingresos_creados;
        for (const x of r.resultados) {
          estadoPorClave[x.clave] = x;
          nuevos.push(...x.ingresos_creados);
        }
      }
      await pedir({ tipo: "marcarSincronizado" });
      // 4. Verificación: se le pregunta a SULAM qué quedó guardado, en vez de suponerlo.
      const guardado = await estados(validos.map((x) => x.clave));
      const faltan = validos.map((x) => x.clave).filter((c) => !guardado[c]);
      marcarFilas(conf, b0.filas, guardado);
      const resumen =
        `Listo: ${validos.length} expedientes leídos` +
        (creados ? `, ${creados} ingreso${creados === 1 ? "" : "s"} nuevo${creados === 1 ? "" : "s"} en Mesa de Entrada (${nuevos.slice(0, 5).join(", ")}${nuevos.length > 5 ? "…" : ""}).` : ". No había pases nuevos.");
      if (faltan.length) {
        ui.texto(
          `${resumen} Atención: SULAM no guardó ${faltan.length} (${faltan.slice(0, 6).join(", ")}${faltan.length > 6 ? "…" : ""}). ` +
            `Se leyeron ${lista.length} en la bandeja, se enviaron ${validos.length} y SULAM respondió por ${Object.keys(estadoPorClave).length}.`,
          "error",
        );
      } else {
        ui.texto(`${resumen} Verificado: todos están en SULAM.`, "exito");
      }
    } catch (e) {
      ui.texto(e.message, "error");
    } finally {
      ocupado = false;
      boton.disabled = false;
    }
  }

  // ------------------------------------------------------------------ vista de un expediente

  async function iniciarExpediente() {
    const exp = P.expediente(document, location.href);
    if (!exp) return;
    const ancla = document.querySelector(".contenedorP") || document.querySelector(".card");
    if (!ancla) return;
    const ui = crearPanel(ancla);
    let conf;
    try {
      conf = await pedir({ tipo: "config" });
    } catch (e) {
      ui.texto(e.message, "error");
      return;
    }
    if (!conf.configurada) {
      ui.texto("Falta configurar la extensión.", "aviso");
      ui.acciones.append(el("button", { type: "button", class: "sulam-boton", onclick: () => pedir({ tipo: "abrirOpciones" }) }, "Configurar"));
      return;
    }
    const mostrar = (r) => {
      ui.acciones.replaceChildren();
      const ins = insignia(conf, r);
      ui.texto("");
      ui.acciones.append(ins);
      const boton = el("button", { type: "button", class: "sulam-boton" }, r ? "Actualizar en SULAM" : "Enviar a SULAM");
      boton.addEventListener("click", async () => {
        boton.disabled = true;
        try {
          const oficina = P.oficina(document);
          const res = await pedir({
            tipo: "api",
            metodo: "POST",
            ruta: "/integracion/ministerio/sincronizar",
            cuerpo: {
              oficina,
              crear_ingresos_desde: conf.desde || null,
              expedientes: [{ clave: exp.clave, url: exp.url, en_bandeja: P.estaEnOficina(exp, oficina), detalle: exp.detalle, movimientos: exp.movimientos }],
            },
          });
          mostrar(res.resultados[0]);
          ui.texto(res.ingresos_creados ? "Se registró el ingreso en Mesa de Entrada." : "Datos actualizados.", "exito");
        } catch (e) {
          ui.texto(e.message, "error");
          boton.disabled = false;
        }
      });
      ui.acciones.append(boton);
    };
    try {
      const est = await estados([exp.clave]);
      mostrar(est[exp.clave]);
    } catch (e) {
      ui.texto(e.message, "error");
    }
  }

  if (/tramitesList\.do/i.test(location.pathname)) iniciarBandeja();
  else if (/expedienteVer\.do/i.test(location.pathname)) iniciarExpediente();
})();

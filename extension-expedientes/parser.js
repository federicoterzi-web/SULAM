// Lectura de las pantallas del Sistema de Expedientes del Ministerio de Desarrollo Social.
// Funciones puras sobre un Document: se usan en la página (content script) y en las pruebas.
(function (global) {
  "use strict";

  const ZONA = "-03:00"; // Tucumán no tiene horario de verano.

  function limpio(t) {
    if (t === null || t === undefined) return null;
    const s = String(t).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
    return s || null;
  }

  function sinTildes(t) {
    return (limpio(t) || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toUpperCase();
  }

  function entero(t) {
    const m = String(t || "").match(/-?\d+/);
    return m ? parseInt(m[0], 10) : null;
  }

  function dos(n) {
    return String(n).padStart(2, "0");
  }

  /** «13/10/2026» → «2026-10-13» */
  function fechaIso(t) {
    const m = String(t || "").match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    return m ? `${m[3]}-${dos(m[2])}-${dos(m[1])}` : null;
  }

  /** «1310» → «13:10», «923» → «09:23», «9:23» → «09:23» */
  function hora(t) {
    const s = String(t || "").trim();
    let m = s.match(/^(\d{1,2})[:.](\d{2})/);
    if (m) return `${dos(m[1])}:${m[2]}`;
    m = s.match(/^(\d{1,4})$/);
    if (!m) return null;
    const v = m[1].padStart(4, "0");
    const hh = parseInt(v.slice(0, 2), 10);
    const mm = parseInt(v.slice(2), 10);
    if (hh > 23 || mm > 59) return null;
    return `${dos(hh)}:${dos(mm)}`;
  }

  /** «09/10/2026-1310-CABRERAC» → { fecha: ISO, usuario, texto } */
  function marca(t) {
    const texto = limpio(t);
    if (!texto) return null;
    const m = texto.match(/^(\d{1,2}\/\d{1,2}\/\d{4})\s*-\s*([\d:.]{1,5})\s*-\s*(.*)$/);
    if (!m) return { fecha: null, usuario: null, texto: texto.slice(0, 100) };
    const f = fechaIso(m[1]);
    const h = hora(m[2]);
    return {
      fecha: f && h ? `${f}T${h}:00${ZONA}` : f ? `${f}T00:00:00${ZONA}` : null,
      usuario: limpio(m[3]),
      texto: texto.slice(0, 100),
    };
  }

  /** «21768/425-AM-2026» o parámetros del enlace → partes y clave normalizada. */
  function clave(numero, codigo, letra, anio) {
    // El Ministerio guarda la letra con espacios de relleno («S » en vez de «S»).
    letra = String(letra || "").replace(/\s+/g, "");
    if (!numero || !codigo || !letra || !anio) return null;
    return `${parseInt(numero, 10)}/${parseInt(codigo, 10)}-${letra.toUpperCase()}-${String(anio).trim()}`;
  }

  function claveDeTexto(t) {
    const m = String(t || "").match(/(\d+)\s*\/\s*(\d+)\s*-\s*([A-Za-z]+)\s*-\s*(\d{4})/);
    return m ? clave(m[1], m[2], m[3], m[4]) : null;
  }

  function claveDeEnlace(href, base) {
    try {
      const u = new URL(href, base);
      const p = u.searchParams;
      return clave(p.get("expNum"), p.get("expCod"), p.get("expLetra"), p.get("expAnio"));
    } catch (e) {
      return null;
    }
  }

  function urlExpediente(c, base) {
    const m = String(c).match(/^(\d+)\/(\d+)-([A-Z]+)-(\d{4})$/);
    if (!m) return null;
    const u = new URL("/seds/expe/expedienteVer.do", base);
    u.searchParams.set("expNum", m[1]);
    u.searchParams.set("expLetra", m[3]);
    u.searchParams.set("expCod", m[2]);
    u.searchParams.set("expAnio", m[4]);
    return u.toString();
  }

  /** Oficina del usuario, del pie de todas las pantallas («Oficina: DIRECCION DE ADULTOS MAYORES»). */
  function oficina(doc) {
    const texto = doc.body ? doc.body.textContent || "" : "";
    const m = texto.match(/(?:^|\n)[ \t]*Oficina:[ \t]*\n?[ \t]*([^\n]+)/);
    return m ? limpio(m[1]) : null;
  }

  function encabezados(tabla) {
    const fila = tabla.tHead ? tabla.tHead.rows[0] : tabla.rows[0];
    return fila ? Array.from(fila.cells).map((c) => sinTildes(c.textContent)) : [];
  }

  function indice(heads, ...nombres) {
    for (const n of nombres) {
      const i = heads.indexOf(sinTildes(n));
      if (i >= 0) return i;
    }
    return -1;
  }

  /** Bandeja de Entrada (tramitesList.do). */
  function bandeja(doc, base) {
    const tabla = doc.getElementById("tramitesEnMiOficinaPaginado");
    const texto = doc.body ? doc.body.textContent || "" : "";
    const tit = texto.match(/Bandeja de Entrada de\s+([^\n]+)/);
    const total = texto.match(/(\d+)\s+Registros encontrados/);
    const res = {
      oficina: oficina(doc),
      titulo: tit ? limpio(tit[1]) : null,
      total: total ? parseInt(total[1], 10) : 0,
      paginas: 1,
      filas: [],
    };
    res.esDeLaOficina = !res.titulo || !res.oficina || sinTildes(res.titulo) === sinTildes(res.oficina);
    if (!tabla) {
      res.total = 0;
      return res;
    }
    const h = encabezados(tabla);
    const col = {
      asignado: indice(h, "Asignado"),
      fecha_asignacion: indice(h, "Fec. Asignación", "Fec. Asignacion"),
      formato: indice(h, "Formato"),
      expediente: indice(h, "Expediente"),
      fecha_ingreso: indice(h, "F. Ingreso"),
      nomenclador: indice(h, "Nomenclador"),
      asunto: indice(h, "Asunto"),
      causante: indice(h, "Causante"),
      estado: indice(h, "Estado"),
    };
    const celda = (fila, k) => (col[k] >= 0 && fila.cells[col[k]] ? limpio(fila.cells[col[k]].textContent) : null);
    const filas = tabla.tBodies.length ? Array.from(tabla.tBodies[0].rows) : Array.from(tabla.rows).slice(1);
    for (const fila of filas) {
      if (fila.cells.length < 5) continue;
      const a = fila.querySelector('a[href*="expedienteVer.do"]');
      const c = (a && claveDeEnlace(a.getAttribute("href"), base)) || claveDeTexto(celda(fila, "expediente"));
      if (!c) continue;
      res.filas.push({
        clave: c,
        url: urlExpediente(c, base),
        fila,
        bandeja: {
          asignado: celda(fila, "asignado"),
          fecha_asignacion: fechaIso(celda(fila, "fecha_asignacion")),
          formato: celda(fila, "formato"),
          fecha_ingreso: fechaIso(celda(fila, "fecha_ingreso")),
          nomenclador: celda(fila, "nomenclador"),
          asunto: celda(fila, "asunto"),
          causante: celda(fila, "causante"),
          estado: celda(fila, "estado"),
        },
      });
    }
    // Páginas: el número más alto de los enlaces del paginador, o el total dividido por filas.
    let max = 1;
    for (const a of Array.from(doc.querySelectorAll("a[href*='page=']"))) {
      const m = (a.getAttribute("href") || "").match(/[?&]page=(\d+)/);
      if (m) max = Math.max(max, parseInt(m[1], 10));
    }
    if (res.filas.length && res.total) max = Math.max(max, Math.ceil(res.total / res.filas.length));
    res.paginas = max;
    return res;
  }

  /** Vista de Expediente (expedienteVer.do). */
  function expediente(doc, base) {
    const datos = {};
    for (const label of Array.from(doc.querySelectorAll(".contenedorCI label"))) {
      const strong = label.querySelector("strong");
      const etiqueta = sinTildes((label.firstChild && label.firstChild.textContent) || "").replace(/:$/, "");
      if (etiqueta) datos[etiqueta] = strong ? strong.textContent : "";
    }
    const cab = limpio((doc.querySelector(".contenedorT") || {}).textContent || "") || "";
    const c = claveDeTexto(cab);
    if (!c) return null;
    const asignado = cab.match(/Asignado a:\s*(\S+)/i);
    const formato = cab.match(/FORMATO\s+([A-ZÁÉÍÓÚ]+)/i);

    let fechaIngreso = null;
    const fi = String(datos["FECHA Y HORA DE INGRESO"] || "").match(/(\d{4})-(\d{2})-(\d{2})\s+([\d:.]{1,5})/);
    if (fi) {
      const h = hora(fi[4]);
      fechaIngreso = `${fi[1]}-${fi[2]}-${fi[3]}T${h || "00:00"}:00${ZONA}`;
    }
    const benef = limpio(datos["BENEFICIARIO"]);
    let beneficiario = benef;
    let documento = null;
    if (benef) {
      const m = benef.match(/^(.*?)\s*-\s*D\.?\s*N\.?\s*I\.?\s*:?\s*([\d.]+)\s*$/i);
      if (m) {
        beneficiario = limpio(m[1]);
        documento = m[2].replace(/\D/g, "") || null;
      }
      if (/^sin beneficiario/i.test(benef)) beneficiario = null;
    }
    const prioridad = limpio((String(datos["PRIORIDAD"] || "").split(" - ")[0]) || "");

    const movimientos = [];
    const t = doc.getElementById("t01");
    if (t) {
      const h = encabezados(t);
      const col = {
        ingreso: indice(h, "Ingreso"),
        fojas_ingreso: indice(h, "Fojas Ing."),
        oficina_origen: indice(h, "Oficina Origen"),
        nota: indice(h, "Nota"),
        oficina: indice(h, "Oficina"),
        recepcion: indice(h, "Recepcion of.", "Recepción of."),
        reparticion: indice(h, "Reparticion", "Repartición"),
        comentarios: indice(h, "Comentarios"),
        egreso: indice(h, "Egreso"),
        fojas_egreso: indice(h, "Fojas Egreso"),
        estado: indice(h, "Estado"),
        dias_sin_recepcion: indice(h, "Dias sin recep", "Días sin recep"),
        dias_pendiente: indice(h, "Dias pendiente", "Días pendiente"),
      };
      for (const fila of Array.from(t.rows).slice(1)) {
        if (fila.cells.length < h.length - 1) continue;
        const v = (k) => (col[k] >= 0 && fila.cells[col[k]] ? limpio(fila.cells[col[k]].textContent) : null);
        const mov = {
          ingreso: marca(v("ingreso")),
          fojas_ingreso: entero(v("fojas_ingreso")),
          oficina_origen: v("oficina_origen"),
          nota: v("nota"),
          oficina: v("oficina"),
          recepcion: marca(v("recepcion")),
          reparticion: v("reparticion"),
          comentarios: v("comentarios"),
          egreso: marca(v("egreso")),
          fojas_egreso: entero(v("fojas_egreso")),
          estado: v("estado"),
          dias_sin_recepcion: entero(v("dias_sin_recepcion")),
          dias_pendiente: entero(v("dias_pendiente")),
        };
        if (mov.ingreso || mov.oficina) movimientos.push(mov);
      }
    }

    return {
      clave: c,
      url: urlExpediente(c, base),
      detalle: {
        oficina_origen: limpio(datos["OFICINA ORIGEN"]),
        fecha_ingreso: fechaIngreso,
        causante: limpio(datos["CAUSANTE"]),
        beneficiario,
        beneficiario_documento: documento,
        asunto: limpio(datos["ASUNTO"]),
        nomenclador: limpio(datos["NOMENCLADOR"]),
        prioridad: prioridad || null,
        formato: formato ? formato[1].toUpperCase() : null,
        asignado_a: asignado ? asignado[1] : null,
      },
      movimientos,
    };
  }

  /** ¿El expediente está hoy en la oficina? (último pase hacia la oficina y sin egreso) */
  function estaEnOficina(exp, ofi) {
    const ultimo = exp.movimientos[exp.movimientos.length - 1];
    return !!(ultimo && ofi && sinTildes(ultimo.oficina) === sinTildes(ofi) && !ultimo.egreso);
  }

  /** Descarga una pantalla del Sistema con la sesión abierta y la decodifica (usa windows-1252). */
  async function traer(url) {
    const r = await fetch(url, { credentials: "include" });
    if (!r.ok) throw new Error(`El Sistema de Expedientes respondió ${r.status} al abrir ${url}`);
    const tipo = r.headers.get("content-type") || "";
    const m = tipo.match(/charset=([\w-]+)/i);
    const buf = await r.arrayBuffer();
    let html = new TextDecoder(m ? m[1] : "windows-1252").decode(buf);
    if (!m) {
      const meta = html.slice(0, 2000).match(/charset=["']?([\w-]+)/i);
      if (meta && !/^windows-1252$/i.test(meta[1])) html = new TextDecoder(meta[1]).decode(buf);
    }
    const doc = new DOMParser().parseFromString(html, "text/html");
    if (/Login\.do|name=["']?password/i.test(html) && !doc.getElementById("tramitesEnMiOficinaPaginado") && !doc.getElementById("t01")) {
      throw new Error("La sesión del Sistema de Expedientes venció. Vuelva a ingresar y repita.");
    }
    return doc;
  }

  global.SulamParser = { limpio, sinTildes, fechaIso, hora, marca, claveDeTexto, claveDeEnlace, urlExpediente, oficina, bandeja, expediente, estaEnOficina, traer };
  if (typeof module !== "undefined" && module.exports) module.exports = global.SulamParser;
})(typeof globalThis !== "undefined" ? globalThis : this);

// Informes redactados en SULAM: plantilla con los datos de la persona ya
// completados, secciones que se agregan, quitan y reordenan, texto con formato,
// guardado automático, firma (PDF con membrete en el legajo) y versiones.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api, type UsuarioBreve } from "../api";
import { Aviso, Cargando, Enlace, Modal, Seccion, Vacio, fecha, fechaHora, navegar, useDatos, useEnvio, useSesion } from "../comun";
import membrete from "../recursos/membrete-2024.jpg";

// ---------------------------------------------------------------- tipos

export interface DatoInforme {
  clave: string | null;
  etiqueta: string;
  valor: string;
}

export interface SeccionInforme {
  titulo: string;
  html: string;
}

export interface Firmante {
  nombre: string;
  cargo: string;
}

export interface ResumenInforme {
  id: string;
  grupo_id: string;
  version: number;
  titulo: string;
  fecha: string;
  estado: "borrador" | "firmado" | "reemplazado";
  caso_id: string | null;
  documento_id: string | null;
  firmado_en: string | null;
  firmado_por: UsuarioBreve | null;
  autor: UsuarioBreve | null;
  actualizado_en: string;
}

interface GrupoInforme extends ResumenInforme {
  vigente: ResumenInforme | null;
  borrador: ResumenInforme | null;
  cantidad_versiones: number;
}

export interface Informe extends ResumenInforme {
  persona: { id: string; nombres: string; apellidos: string; numero_legajo: string };
  caso: { id: string; numero: string; numero_actuacion: number | null; anio_actuacion: number | null; area: string | null } | null;
  plantilla_id: number | null;
  tipo_documental: { id: number; nombre: string } | null;
  lugar: string | null;
  destinatario: string | null;
  datos: DatoInforme[];
  secciones: SeccionInforme[];
  firmantes: Firmante[];
  estructura: {
    destinatario: boolean;
    numerar: boolean;
    mostrar_titulo: boolean;
    guias: Record<string, string>;
    secciones_sugeridas: string[];
  };
  versiones: ResumenInforme[];
  permisos: { modificar: boolean; firmar: boolean; nueva_version: boolean; descartar: boolean };
  datos_disponibles?: DatoInforme[];
}

export interface PlantillaResumen {
  id: number;
  nombre: string;
  descripcion: string | null;
  area: { id: number; nombre: string } | null;
}

interface CatalogoInformes {
  campos: { clave: string; etiqueta: string }[];
  plantillas: PlantillaResumen[];
  lugar: string;
}

interface Fuente {
  grupo: string;
  titulo: string;
  texto: string;
}

export const ESTADOS_INFORME: Record<string, string> = {
  borrador: "Borrador",
  firmado: "Firmado",
  reemplazado: "Reemplazado por otra versión",
};

export function useCatalogoInformes() {
  return useDatos(() => api.get<CatalogoInformes>("/informes/catalogo"), []);
}

/** Ruta del editor según la versión que se está usando. */
export function rutaInforme(id: string, movil?: boolean) {
  return (movil ? "/m/informe/" : "/informes/") + id;
}

function areaCorta(nombre: string | null | undefined) {
  return (nombre ?? "").replace(/^(Departamento|División|Dirección de)\s+/i, "");
}

// ---------------------------------------------------------------- listado en caso y legajo

export function SeccionInformes({ casoId, personaId, puedeCrear }: { casoId?: string; personaId?: string; puedeCrear: boolean }) {
  const ruta = casoId ? `/casos/${casoId}/informes` : `/personas/${personaId}/informes`;
  const lista = useDatos(() => api.get<GrupoInforme[]>(ruta), [ruta]);
  const [nuevo, setNuevo] = useState(false);
  return (
    <Seccion
      titulo="Informes"
      acciones={
        puedeCrear && (
          <button className="boton boton-primario" onClick={() => setNuevo(true)}>
            Redactar informe
          </button>
        )
      }
    >
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <Vacio>
          Todavía no hay informes redactados en SULAM. Se arman con una plantilla que ya trae los datos de la persona; al firmarlos,
          el PDF con membrete queda en los documentos.
        </Vacio>
      ) : (
        <TablaInformes grupos={lista.datos} />
      )}
      {nuevo && (
        <Modal titulo="Redactar informe" alCerrar={() => setNuevo(false)} ancho>
          <ElegirPlantilla casoId={casoId} personaId={personaId} alCrear={(i) => navegar(rutaInforme(i.id))} />
        </Modal>
      )}
    </Seccion>
  );
}

function TablaInformes({ grupos }: { grupos: GrupoInforme[] }) {
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Informe</th>
          <th>Estado</th>
          <th>Fecha</th>
          <th>Redactó</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {grupos.map((g) => (
          <tr key={g.grupo_id}>
            <td>
              <strong>{g.titulo}</strong>
              {g.cantidad_versiones > 1 && <div className="tenue">{g.cantidad_versiones} versiones</div>}
            </td>
            <td>
              {g.vigente && <span className="chip-informe chip-firmado">Firmado · v{g.vigente.version}</span>}{" "}
              {g.borrador && <span className="chip-informe chip-borrador">Borrador{g.borrador.version > 1 ? ` · v${g.borrador.version}` : ""}</span>}
            </td>
            <td>{fecha(g.vigente?.firmado_en ?? g.fecha)}</td>
            <td>{(g.borrador ?? g.vigente ?? g).autor?.nombre_completo ?? "—"}</td>
            <td className="celda-acciones">
              {g.borrador && (
                <Enlace a={rutaInforme(g.borrador.id)} className="boton boton-chico boton-primario">
                  Seguir redactando
                </Enlace>
              )}
              {g.vigente && (
                <>
                  <Enlace a={rutaInforme(g.vigente.id)} className="boton boton-chico">
                    Ver
                  </Enlace>
                  {g.vigente.documento_id && (
                    <a className="boton boton-chico" href={`/api/documentos/${g.vigente.documento_id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
                      PDF
                    </a>
                  )}
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ElegirPlantilla({
  casoId,
  personaId,
  alCrear,
}: {
  casoId?: string;
  personaId?: string;
  alCrear: (i: Informe) => void;
}) {
  const cat = useCatalogoInformes();
  const { yo } = useSesion();
  const envio = useEnvio();
  const crear = (plantilla_id: number | null) =>
    envio.ejecutar(async () => {
      const i = await api.post<Informe>("/informes", { caso_id: casoId, persona_id: personaId, plantilla_id });
      alCrear(i);
    });
  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  return (
    <div className="elegir-plantilla">
      <p className="tenue">Elija una plantilla. Los datos de la persona se completan solos; después puede quitar o agregar datos y secciones.</p>
      <div className="plantillas-grilla">
        {cat.datos.plantillas.map((p) => (
          <button key={p.id} type="button" className="plantilla-tarjeta" onClick={() => crear(p.id)} disabled={envio.enviando}>
            <strong>{p.nombre}</strong>
            {p.descripcion && <span>{p.descripcion}</span>}
            {p.area && (
              <small className={p.area.id === yo.area?.id ? "de-mi-area" : ""}>
                {p.area.id === yo.area?.id ? "De su área" : areaCorta(p.area.nombre)}
              </small>
            )}
          </button>
        ))}
        <button type="button" className="plantilla-tarjeta plantilla-blanco" onClick={() => crear(null)} disabled={envio.enviando}>
          <strong>Documento en blanco</strong>
          <span>Solo membrete, nombre, documento y domicilio.</span>
        </button>
      </div>
      {envio.enviando && <p className="tenue">Preparando el informe…</p>}
      <Aviso error={envio.error} />
    </div>
  );
}

// ---------------------------------------------------------------- editor de texto con formato

let editorActivo: { uid: string; rango: Range } | null = null;

if (typeof document !== "undefined") {
  document.addEventListener("selectionchange", () => {
    const sel = document.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const nodo = sel.anchorNode;
    const el = (nodo instanceof Element ? nodo : nodo?.parentElement)?.closest<HTMLElement>("[data-editor]");
    if (el) editorActivo = { uid: el.dataset.editor!, rango: sel.getRangeAt(0).cloneRange() };
  });
}

function escaparHtml(t: string) {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Texto plano → párrafos HTML (al pegar o insertar textos del caso). */
export function textoAParrafos(texto: string) {
  return texto
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => `<p>${escaparHtml(p).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function estaVacio(el: HTMLElement) {
  return (el.textContent ?? "").trim() === "" && !el.querySelector("li");
}

export function EditorTexto({
  uid,
  inicial,
  alCambiar,
  placeholder,
  soloLectura,
  etiqueta,
}: {
  uid: string;
  inicial: string;
  alCambiar: (html: string) => void;
  placeholder?: string;
  soloLectura?: boolean;
  etiqueta?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cambiar = useRef(alCambiar);
  cambiar.current = alCambiar;
  useEffect(() => {
    const el = ref.current!;
    el.innerHTML = inicial;
    el.classList.toggle("vacio", estaVacio(el));
    // El contenido inicial se fija una sola vez: después manda lo que se escribe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);
  const alEscribir = () => {
    const el = ref.current!;
    el.classList.toggle("vacio", estaVacio(el));
    cambiar.current(el.innerHTML);
  };
  return (
    <div
      ref={ref}
      className="editor-texto"
      data-editor={uid}
      data-placeholder={placeholder}
      contentEditable={!soloLectura}
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label={etiqueta ?? "Texto"}
      onFocus={() => {
        try {
          document.execCommand("defaultParagraphSeparator", false, "p");
        } catch {
          /* navegadores sin soporte */
        }
        // Un texto vacío arranca con un párrafo, así el primer renglón también lleva sangría.
        const el = ref.current!;
        if (!soloLectura && estaVacio(el) && !el.querySelector("p")) {
          el.innerHTML = "<p><br></p>";
          const r = document.createRange();
          r.setStart(el.firstChild!, 0);
          r.collapse(true);
          const sel = document.getSelection()!;
          sel.removeAllRanges();
          sel.addRange(r);
        }
      }}
      onInput={alEscribir}
      onPaste={(e) => {
        // Se pega como texto: evita estilos y basura de Word o páginas web.
        e.preventDefault();
        const texto = e.clipboardData.getData("text/plain");
        if (!texto) return;
        const html = texto.includes("\n") ? textoAParrafos(texto) : escaparHtml(texto);
        document.execCommand("insertHTML", false, html);
      }}
    />
  );
}

/** Inserta párrafos después del párrafo donde estaba el cursor (o al final de la sección indicada). */
function insertarEn(uidPreferido: string | null, html: string): boolean {
  const activo = editorActivo && document.querySelector(`[data-editor="${editorActivo.uid}"]`) ? editorActivo : null;
  const destino = activo ? activo.uid : uidPreferido;
  if (!destino) return false;
  const el = document.querySelector<HTMLElement>(`[data-editor="${destino}"]`);
  if (!el || el.contentEditable !== "true") return false;
  // Bloque (párrafo o lista) de primer nivel donde estaba el cursor.
  let bloque: Node | null = null;
  if (activo && el.contains(activo.rango.endContainer)) {
    bloque = activo.rango.endContainer;
    while (bloque && bloque.parentNode !== el) bloque = bloque.parentNode;
  }
  const plantilla = document.createElement("template");
  plantilla.innerHTML = html;
  const nuevos = Array.from(plantilla.content.childNodes);
  const ultimo = nuevos[nuevos.length - 1];
  if (estaVacio(el)) el.innerHTML = "";
  if (bloque && bloque.nextSibling) el.insertBefore(plantilla.content, bloque.nextSibling);
  else el.appendChild(plantilla.content);
  // Cursor al final de lo insertado, para seguir escribiendo.
  el.focus();
  const r = document.createRange();
  r.selectNodeContents(ultimo);
  r.collapse(false);
  const sel = document.getSelection()!;
  sel.removeAllRanges();
  sel.addRange(r);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  (ultimo as Element).scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  return true;
}

const FORMATOS: { cmd: string; texto: ReactNode; titulo: string }[] = [
  { cmd: "bold", texto: <b>N</b>, titulo: "Negrita (Ctrl+B)" },
  { cmd: "italic", texto: <i>C</i>, titulo: "Cursiva (Ctrl+I)" },
  { cmd: "underline", texto: <u>S</u>, titulo: "Subrayado (Ctrl+U)" },
  { cmd: "insertUnorderedList", texto: "• Lista", titulo: "Lista con viñetas" },
  { cmd: "insertOrderedList", texto: "1. Lista", titulo: "Lista numerada" },
  { cmd: "removeFormat", texto: "Quitar formato", titulo: "Quitar negrita, cursiva y subrayado" },
];

export function BarraFormato() {
  return (
    <div className="barra-formato" role="toolbar" aria-label="Formato del texto">
      {FORMATOS.map((f) => (
        <button
          key={f.cmd}
          type="button"
          title={f.titulo}
          aria-label={f.titulo}
          onMouseDown={(e) => {
            e.preventDefault(); // no sacar el foco del texto
            document.execCommand(f.cmd);
          }}
        >
          {f.texto}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- editor del informe

interface Local {
  titulo: string;
  lugar: string;
  fecha: string;
  destinatario: string | null;
  datos: (DatoInforme & { uid: string })[];
  secciones: (SeccionInforme & { uid: string })[];
  firmantes: Firmante[];
}

let contadorUid = 0;
const nuevoUid = () => `u${++contadorUid}`;

function aLocal(i: Informe): Local {
  return {
    titulo: i.titulo,
    lugar: i.lugar ?? "",
    fecha: i.fecha,
    destinatario: i.destinatario,
    datos: i.datos.map((d) => ({ ...d, uid: nuevoUid() })),
    secciones: i.secciones.map((s) => ({ ...s, uid: nuevoUid() })),
    firmantes: i.firmantes.length ? i.firmantes : [],
  };
}

type EstadoGuardado = "guardado" | "pendiente" | "guardando" | "error";

export function PaginaInforme({ id, movil }: { id: string; movil?: boolean }) {
  const [inf, setInf] = useState<Informe | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    setInf(null);
    api.get<Informe>(`/informes/${id}`).then(setInf, setError);
  }, [id]);
  if (error) return <Aviso error={error} />;
  if (!inf) return <Cargando />;
  return inf.permisos.modificar ? (
    <EditorInforme inicial={inf} movil={movil} alCambiarInforme={setInf} key={inf.id} />
  ) : (
    <InformeLectura inf={inf} movil={movil} />
  );
}

function enlaceVolver(inf: Informe, movil?: boolean) {
  if (inf.caso) return { a: movil ? `/m/caso/${inf.caso.id}` : `/casos/${inf.caso.id}`, texto: actuacion(inf) };
  return { a: movil ? `/m/legajo/${inf.persona.id}` : `/legajos/${inf.persona.id}`, texto: `Legajo ${inf.persona.numero_legajo}` };
}

function actuacion(inf: Informe) {
  const c = inf.caso!;
  return c.numero_actuacion ? `Actuación ${c.numero_actuacion}/${c.anio_actuacion}` : `Caso ${c.numero}`;
}

function Versiones({ inf, movil }: { inf: Informe; movil?: boolean }) {
  if (inf.versiones.length < 2) return null;
  return (
    <label className="informe-versiones">
      <span className="tenue">Versión</span>
      <select value={inf.id} onChange={(e) => navegar(rutaInforme(e.target.value, movil))}>
        {inf.versiones.map((v) => (
          <option key={v.id} value={v.id}>
            {v.version} · {ESTADOS_INFORME[v.estado]}
            {v.firmado_en ? ` ${fecha(v.firmado_en)}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

function EditorInforme({ inicial, movil, alCambiarInforme }: { inicial: Informe; movil?: boolean; alCambiarInforme: (i: Informe) => void }) {
  const inf = inicial;
  const [local, setLocal] = useState<Local>(() => aLocal(inicial));
  const [estado, setEstado] = useState<EstadoGuardado>("guardado");
  const [errorGuardado, setErrorGuardado] = useState<unknown>(null);
  const [firmar, setFirmar] = useState(false);
  const [panel, setPanel] = useState(!movil);
  const actualizadoEn = useRef(inicial.actualizado_en);
  const ultimo = useRef(local);
  ultimo.current = local;
  const sucio = useRef(false);
  const guardando = useRef<Promise<boolean> | null>(null);

  const cambiar = useCallback((f: (l: Local) => Local) => {
    sucio.current = true;
    setEstado("pendiente");
    setLocal((l) => f(l));
  }, []);

  const guardar = useCallback(async (): Promise<boolean> => {
    if (guardando.current) await guardando.current;
    if (!sucio.current) return true;
    sucio.current = false;
    const l = ultimo.current;
    setEstado("guardando");
    const tarea = (async () => {
      try {
        const r = await api.put<{ actualizado_en: string }>(`/informes/${inf.id}`, {
          titulo: l.titulo.trim() || "Informe",
          lugar: l.lugar,
          fecha: l.fecha || new Date().toISOString().slice(0, 10),
          destinatario: l.destinatario,
          datos: l.datos.map(({ clave, etiqueta, valor }) => ({ clave, etiqueta, valor })),
          secciones: l.secciones.map(({ titulo, html }) => ({ titulo, html })),
          firmantes: l.firmantes,
          actualizado_en: actualizadoEn.current,
        });
        actualizadoEn.current = r.actualizado_en;
        setErrorGuardado(null);
        setEstado(sucio.current ? "pendiente" : "guardado");
        return true;
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 409)) sucio.current = true;
        setErrorGuardado(e);
        setEstado("error");
        return false;
      }
    })();
    guardando.current = tarea;
    const ok = await tarea;
    guardando.current = null;
    return ok;
  }, [inf.id]);

  // Guardado automático: 1,5 s después de dejar de escribir.
  useEffect(() => {
    if (estado !== "pendiente") return;
    const t = setTimeout(guardar, 1500);
    return () => clearTimeout(t);
  }, [local, estado, guardar]);

  // Al salir de la pantalla o cerrar la pestaña, se guarda lo pendiente.
  useEffect(() => {
    const antesDeSalir = (e: BeforeUnloadEvent) => {
      if (sucio.current) {
        guardar();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", antesDeSalir);
    return () => {
      window.removeEventListener("beforeunload", antesDeSalir);
      if (sucio.current) guardar();
    };
  }, [guardar]);

  const fuentes = useDatos(() => api.get<Fuente[]>(`/informes/${inf.id}/fuentes`), [inf.id]);
  const volver = enlaceVolver(inf, movil);
  const disponibles = inf.datos_disponibles ?? [];

  // -- datos
  const setDato = (uid: string, campo: "etiqueta" | "valor", v: string) =>
    cambiar((l) => ({ ...l, datos: l.datos.map((d) => (d.uid === uid ? { ...d, [campo]: v } : d)) }));
  const quitarDato = (uid: string) => cambiar((l) => ({ ...l, datos: l.datos.filter((d) => d.uid !== uid) }));
  const moverDato = (i: number, delta: number) =>
    cambiar((l) => {
      const d = [...l.datos];
      const j = i + delta;
      if (j < 0 || j >= d.length) return l;
      [d[i], d[j]] = [d[j], d[i]];
      return { ...l, datos: d };
    });
  const agregarDato = (clave: string) => {
    const uid = nuevoUid();
    if (clave === "_libre") {
      cambiar((l) => ({ ...l, datos: [...l.datos, { clave: null, etiqueta: "", valor: "", uid }] }));
    } else {
      const d = disponibles.find((x) => x.clave === clave);
      if (d) cambiar((l) => ({ ...l, datos: [...l.datos, { ...d, uid }] }));
    }
    setTimeout(() => document.querySelector<HTMLInputElement>(`[data-dato="${uid}"] input`)?.focus(), 50);
  };
  const desactualizados = local.datos.filter((d) => {
    const x = d.clave && disponibles.find((y) => y.clave === d.clave);
    return x && x.valor && x.valor !== d.valor;
  });
  const actualizarDatos = () =>
    cambiar((l) => ({
      ...l,
      datos: l.datos.map((d) => {
        const x = d.clave && disponibles.find((y) => y.clave === d.clave);
        return x && x.valor ? { ...d, valor: x.valor } : d;
      }),
    }));

  // -- secciones
  const setSeccion = (uid: string, campo: "titulo" | "html", v: string) =>
    cambiar((l) => ({ ...l, secciones: l.secciones.map((s) => (s.uid === uid ? { ...s, [campo]: v } : s)) }));
  const moverSeccion = (i: number, delta: number) =>
    cambiar((l) => {
      const s = [...l.secciones];
      const j = i + delta;
      if (j < 0 || j >= s.length) return l;
      [s[i], s[j]] = [s[j], s[i]];
      return { ...l, secciones: s };
    });
  const quitarSeccion = (s: SeccionInforme & { uid: string }) => {
    const conTexto = s.html.replace(/<[^>]+>|&nbsp;|\s/g, "") !== "";
    if (conTexto && !confirm(`¿Quitar la sección «${s.titulo || "sin título"}» y su texto?`)) return;
    cambiar((l) => ({ ...l, secciones: l.secciones.filter((x) => x.uid !== s.uid) }));
  };
  const agregarSeccion = (titulo: string) => {
    const uid = nuevoUid();
    cambiar((l) => ({ ...l, secciones: [...l.secciones, { titulo, html: "", uid }] }));
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>(titulo ? `[data-editor="${uid}"]` : `[data-seccion="${uid}"] input`);
      el?.focus();
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 60);
  };
  const sugeridasFaltantes = inf.estructura.secciones_sugeridas.filter((t) => !local.secciones.some((s) => s.titulo === t));

  // -- firmantes
  const setFirmante = (i: number, campo: keyof Firmante, v: string) =>
    cambiar((l) => ({ ...l, firmantes: l.firmantes.map((f, j) => (j === i ? { ...f, [campo]: v } : f)) }));

  const insertar = (f: Fuente) => {
    const html = textoAParrafos(f.texto);
    const ultimaSeccion = local.secciones[local.secciones.length - 1]?.uid ?? null;
    if (!insertarEn(ultimaSeccion, html)) alert("Agregue una sección para insertar el texto.");
    if (movil) setPanel(false);
  };

  const descartar = async () => {
    if (!confirm("¿Descartar este borrador? No se puede recuperar.")) return;
    try {
      await api.post(`/informes/${inf.id}/descartar`);
      navegar(volver.a);
    } catch (e) {
      setErrorGuardado(e);
    }
  };

  const vistaPrevia = async () => {
    // Se guarda antes, para que el PDF muestre lo último escrito.
    const ventana = window.open("about:blank", "_blank");
    await guardar();
    if (ventana) ventana.location.href = `/api/informes/${inf.id}/vista-previa`;
  };

  let numero = 0;
  return (
    <div className={`informe-editor ${movil ? "informe-movil" : ""}`}>
      <header className="informe-cabecera">
        <div className="informe-cabecera-texto">
          <Enlace a={volver.a} className="informe-volver">
            ‹ {volver.texto} · {inf.persona.apellidos.toUpperCase()}, {inf.persona.nombres}
          </Enlace>
          <div className="informe-estado">
            <span className="chip-informe chip-borrador">Borrador{inf.version > 1 ? ` · versión ${inf.version}` : ""}</span>
            <span className={`guardado guardado-${estado}`} role="status">
              {estado === "guardado" ? "✓ Guardado" : estado === "guardando" ? "Guardando…" : estado === "pendiente" ? "Cambios sin guardar" : "No se pudo guardar"}
            </span>
            <Versiones inf={inf} movil={movil} />
          </div>
        </div>
        <div className="fila-botones informe-acciones">
          {inf.permisos.descartar && (
            <button className="boton boton-texto" onClick={descartar}>
              Descartar
            </button>
          )}
          <button className="boton" onClick={vistaPrevia}>
            Vista previa (PDF)
          </button>
          {inf.permisos.firmar && (
            <button
              className="boton boton-primario"
              onClick={async () => {
                if (await guardar()) setFirmar(true);
              }}
            >
              Firmar…
            </button>
          )}
        </div>
      </header>
      {errorGuardado ? <Aviso error={errorGuardado} /> : null}

      <div className="informe-cuerpo">
        <div className="informe-columna">
          <div className="barra-formato-fija">
            <BarraFormato />
            {movil && (
              <button type="button" className="boton boton-chico" onClick={() => setPanel(true)}>
                Insertar del caso
              </button>
            )}
          </div>
          <article className="hoja-informe">
            <header className="hoja-membrete">
              <img src={membrete} alt="Ministerio de Desarrollo Social · Dirección de Adultos Mayores · Gobierno de Tucumán" />
              {inf.caso?.area && <span className="hoja-area">{areaCorta(inf.caso.area).toUpperCase()}</span>}
            </header>

            <div className="hoja-lugar">
              <input
                aria-label="Lugar"
                value={local.lugar}
                onChange={(e) => cambiar((l) => ({ ...l, lugar: e.target.value }))}
                size={Math.max(10, local.lugar.length)}
              />
              ,{" "}
              <input type="date" aria-label="Fecha" value={local.fecha} onChange={(e) => cambiar((l) => ({ ...l, fecha: e.target.value }))} />
            </div>

            {local.destinatario !== null ? (
              <div className="hoja-bloque">
                <textarea
                  className="hoja-destinatario"
                  aria-label="Destinatario"
                  placeholder={"Sr./Sra. …\nCargo\nInstitución\nS / D"}
                  rows={Math.max(3, local.destinatario.split("\n").length)}
                  value={local.destinatario}
                  onChange={(e) => cambiar((l) => ({ ...l, destinatario: e.target.value }))}
                />
                <button type="button" className="boton-quitar" title="Quitar destinatario" onClick={() => cambiar((l) => ({ ...l, destinatario: null }))}>
                  ×
                </button>
              </div>
            ) : (
              <button type="button" className="boton-agregar" onClick={() => cambiar((l) => ({ ...l, destinatario: "" }))}>
                + Agregar destinatario
              </button>
            )}

            <input
              className={`hoja-titulo ${inf.estructura.mostrar_titulo ? "" : "hoja-titulo-oculto"}`}
              aria-label="Título del informe"
              value={local.titulo}
              onChange={(e) => cambiar((l) => ({ ...l, titulo: e.target.value }))}
              placeholder="Título del informe"
            />
            {!inf.estructura.mostrar_titulo && <p className="hoja-ayuda">El título no se imprime en este tipo de documento; sirve para encontrarlo en el legajo.</p>}

            <div className="hoja-datos">
              {local.datos.map((d, i) => (
                <div className="hoja-dato" key={d.uid} data-dato={d.uid}>
                  <input
                    className="dato-etiqueta"
                    aria-label="Nombre del dato"
                    placeholder="Dato"
                    value={d.etiqueta}
                    size={Math.max(4, d.etiqueta.length)}
                    onChange={(e) => setDato(d.uid, "etiqueta", e.target.value)}
                  />
                  <span className="dato-dos">:</span>
                  <input className="dato-valor" aria-label={d.etiqueta || "Valor"} value={d.valor} placeholder="—" onChange={(e) => setDato(d.uid, "valor", e.target.value)} />
                  <span className="dato-botones">
                    <button type="button" title="Subir" onClick={() => moverDato(i, -1)} disabled={i === 0}>
                      ↑
                    </button>
                    <button type="button" title={`Quitar «${d.etiqueta}»`} aria-label={`Quitar ${d.etiqueta}`} onClick={() => quitarDato(d.uid)}>
                      ×
                    </button>
                  </span>
                </div>
              ))}
              <div className="hoja-datos-acciones">
                <select
                  className="boton-agregar"
                  value=""
                  aria-label="Agregar dato"
                  onChange={(e) => {
                    if (e.target.value) agregarDato(e.target.value);
                  }}
                >
                  <option value="">+ Agregar dato…</option>
                  {disponibles
                    .filter((d) => !local.datos.some((x) => x.clave === d.clave))
                    .map((d) => (
                      <option key={d.clave!} value={d.clave!}>
                        {d.etiqueta}
                        {d.valor ? ` (${d.valor.length > 40 ? d.valor.slice(0, 40) + "…" : d.valor})` : " (sin dato en el legajo)"}
                      </option>
                    ))}
                  <option value="_libre">Otro dato (escribirlo)</option>
                </select>
                {desactualizados.length > 0 && (
                  <button type="button" className="boton-agregar" onClick={actualizarDatos} title={desactualizados.map((d) => d.etiqueta).join(", ")}>
                    ↻ Actualizar {desactualizados.length} {desactualizados.length === 1 ? "dato" : "datos"} con el legajo
                  </button>
                )}
              </div>
            </div>

            {local.secciones.map((s, i) => {
              const n = s.titulo ? ++numero : 0;
              const guia = inf.estructura.guias[s.titulo];
              return (
                <section className="hoja-seccion" key={s.uid} data-seccion={s.uid}>
                  <div className="seccion-titulo">
                    {inf.estructura.numerar && s.titulo && <span className="seccion-numero">{n}.</span>}
                    <input
                      aria-label="Título de la sección"
                      placeholder="Título de la sección (opcional)"
                      value={s.titulo}
                      onChange={(e) => setSeccion(s.uid, "titulo", e.target.value)}
                    />
                    <span className="seccion-botones">
                      <button type="button" title="Subir la sección" onClick={() => moverSeccion(i, -1)} disabled={i === 0}>
                        ↑
                      </button>
                      <button type="button" title="Bajar la sección" onClick={() => moverSeccion(i, 1)} disabled={i === local.secciones.length - 1}>
                        ↓
                      </button>
                      <button type="button" title="Quitar la sección" aria-label={`Quitar la sección ${s.titulo}`} onClick={() => quitarSeccion(s)}>
                        ×
                      </button>
                    </span>
                  </div>
                  <EditorTexto
                    uid={s.uid}
                    inicial={s.html}
                    etiqueta={s.titulo || "Texto"}
                    placeholder={guia || "Escriba aquí…"}
                    alCambiar={(h) => setSeccion(s.uid, "html", h)}
                  />
                </section>
              );
            })}
            <div className="hoja-agregar-seccion">
              {sugeridasFaltantes.map((t) => (
                <button key={t} type="button" className="boton-agregar" onClick={() => agregarSeccion(t)}>
                  + {t}
                </button>
              ))}
              <button type="button" className="boton-agregar" onClick={() => agregarSeccion("")}>
                + Sección nueva
              </button>
            </div>

            <div className="hoja-firmas">
              {local.firmantes.map((f, i) => (
                <div className="hoja-firma" key={i}>
                  <div className="linea-firma" />
                  <input className="firma-nombre" aria-label="Nombre de quien firma" placeholder="Nombre y apellido" value={f.nombre} onChange={(e) => setFirmante(i, "nombre", e.target.value)} />
                  <input aria-label="Cargo o profesión" placeholder="Cargo o profesión" value={f.cargo} onChange={(e) => setFirmante(i, "cargo", e.target.value)} />
                  <button
                    type="button"
                    className="boton-quitar"
                    title="Quitar firmante"
                    onClick={() => cambiar((l) => ({ ...l, firmantes: l.firmantes.filter((_, j) => j !== i) }))}
                  >
                    ×
                  </button>
                </div>
              ))}
              {local.firmantes.length < 6 && (
                <button type="button" className="boton-agregar" onClick={() => cambiar((l) => ({ ...l, firmantes: [...l.firmantes, { nombre: "", cargo: "" }] }))}>
                  + Agregar firmante
                </button>
              )}
            </div>
          </article>
        </div>

        {panel && (
          <aside className={`informe-panel ${movil ? "informe-panel-movil" : ""}`}>
            <header>
              <h3>Insertar del caso</h3>
              {movil && (
                <button type="button" className="boton-icono" onClick={() => setPanel(false)} aria-label="Cerrar">
                  ×
                </button>
              )}
            </header>
            <p className="tenue">
              {movil ? "Toque «Insertar» y el texto se agrega" : "Ubique el cursor en el texto y toque «Insertar»: se agrega"} donde estaba escribiendo (o al
              final del informe). Después puede editarlo.
            </p>
            <Aviso error={fuentes.error} />
            {!fuentes.datos ? (
              <Cargando />
            ) : fuentes.datos.length === 0 ? (
              <p className="tenue">Todavía no hay evoluciones ni otros textos cargados en el caso.</p>
            ) : (
              <ListaFuentes fuentes={fuentes.datos} alInsertar={insertar} />
            )}
          </aside>
        )}
      </div>

      {firmar && (
        <ConfirmarFirma
          inf={inf}
          firmantes={local.firmantes}
          secciones={local.secciones}
          datos={local.datos}
          alCerrar={() => setFirmar(false)}
          alFirmar={(i) => {
            sucio.current = false;
            setFirmar(false);
            alCambiarInforme(i);
          }}
        />
      )}
    </div>
  );
}

function ListaFuentes({ fuentes, alInsertar }: { fuentes: Fuente[]; alInsertar: (f: Fuente) => void }) {
  const grupos = useMemo(() => Array.from(new Set(fuentes.map((f) => (f.grupo.startsWith("Registro de demanda") ? "Registro de demanda" : f.grupo)))), [fuentes]);
  const [grupo, setGrupo] = useState("");
  const visibles = fuentes.filter((f) => !grupo || f.grupo === grupo || (grupo === "Registro de demanda" && f.grupo.startsWith(grupo)));
  return (
    <>
      {grupos.length > 1 && (
        <div className="chips-filtro">
          <button type="button" className={grupo === "" ? "activo" : ""} onClick={() => setGrupo("")}>
            Todo
          </button>
          {grupos.map((g) => (
            <button key={g} type="button" className={grupo === g ? "activo" : ""} onClick={() => setGrupo(g)}>
              {g}
            </button>
          ))}
        </div>
      )}
      <ul className="lista-fuentes">
        {visibles.map((f, i) => (
          <li key={i}>
            <div>
              <small>{f.grupo}</small>
              <strong>{f.titulo}</strong>
              <p>{f.texto}</p>
            </div>
            <button
              type="button"
              className="boton boton-chico"
              onMouseDown={(e) => e.preventDefault() /* conserva el cursor en el texto */}
              onClick={() => alInsertar(f)}
            >
              Insertar
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function ConfirmarFirma({
  inf,
  firmantes,
  secciones,
  datos,
  alCerrar,
  alFirmar,
}: {
  inf: Informe;
  firmantes: Firmante[];
  secciones: SeccionInforme[];
  datos: DatoInforme[];
  alCerrar: () => void;
  alFirmar: (i: Informe) => void;
}) {
  const envio = useEnvio();
  const validos = firmantes.filter((f) => f.nombre.trim());
  const vacias = secciones.filter((s) => s.html.replace(/<[^>]+>|&nbsp;|\s/g, "") === "").map((s) => s.titulo || "sin título");
  const sinValor = datos.filter((d) => !d.valor.trim()).map((d) => d.etiqueta);
  return (
    <Modal titulo="Firmar el informe" alCerrar={alCerrar}>
      <p>
        Se genera el PDF con membrete y queda guardado en los documentos {inf.caso ? "del caso" : "del legajo"} como «{inf.tipo_documental?.nombre ?? "Informe"}».
      </p>
      <p>
        <strong>Después no se puede modificar.</strong> Si hay que corregirlo, se abre una nueva versión y la anterior queda registrada.
      </p>
      {validos.length === 0 ? (
        <Aviso error="Agregue al menos una persona que firme (al final del informe)." />
      ) : (
        <p>
          Firman: {validos.map((f) => f.nombre + (f.cargo ? ` (${f.cargo})` : "")).join(", ")}.
        </p>
      )}
      {(vacias.length > 0 || sinValor.length > 0) && (
        <div className="aviso aviso-advertencia">
          {vacias.length > 0 && (
            <p>
              Secciones vacías (no se imprimen): <strong>{vacias.join(", ")}</strong>.
            </p>
          )}
          {sinValor.length > 0 && (
            <p>
              Datos sin completar (salen en blanco): <strong>{sinValor.join(", ")}</strong>. Puede completarlos o quitarlos.
            </p>
          )}
        </div>
      )}
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton" onClick={alCerrar}>
          Seguir editando
        </button>
        <button
          className="boton boton-primario"
          disabled={envio.enviando || validos.length === 0}
          onClick={() =>
            envio.ejecutar(async () => {
              alFirmar(await api.post<Informe>(`/informes/${inf.id}/firmar`));
            })
          }
        >
          {envio.enviando ? "Firmando…" : "Firmar y guardar el PDF"}
        </button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- lectura (firmado o sin permiso)

function InformeLectura({ inf, movil }: { inf: Informe; movil?: boolean }) {
  const volver = enlaceVolver(inf, movil);
  const envio = useEnvio();
  let numero = 0;
  return (
    <div className={`informe-editor ${movil ? "informe-movil" : ""}`}>
      <header className="informe-cabecera">
        <div className="informe-cabecera-texto">
          <Enlace a={volver.a} className="informe-volver">
            ‹ {volver.texto} · {inf.persona.apellidos.toUpperCase()}, {inf.persona.nombres}
          </Enlace>
          <div className="informe-estado">
            <span className={`chip-informe chip-${inf.estado}`}>
              {ESTADOS_INFORME[inf.estado]}
              {inf.version > 1 ? ` · versión ${inf.version}` : ""}
            </span>
            {inf.firmado_en && (
              <span className="tenue">
                el {fechaHora(inf.firmado_en)} por {inf.firmado_por?.nombre_completo}
              </span>
            )}
            <Versiones inf={inf} movil={movil} />
          </div>
        </div>
        <div className="fila-botones informe-acciones">
          {inf.documento_id && (
            <a className="boton boton-primario" href={`/api/documentos/${inf.documento_id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
              Ver PDF firmado
            </a>
          )}
          {inf.estado === "borrador" && (
            <a className="boton" href={`/api/informes/${inf.id}/vista-previa`} target="_blank" rel="noreferrer">
              Vista previa (PDF)
            </a>
          )}
          {inf.permisos.nueva_version && (
            <button
              className="boton"
              disabled={envio.enviando}
              onClick={() =>
                envio.ejecutar(async () => {
                  const n = await api.post<Informe>(`/informes/${inf.id}/nueva-version`);
                  navegar(rutaInforme(n.id, movil));
                })
              }
            >
              Corregir (nueva versión)
            </button>
          )}
        </div>
      </header>
      <Aviso error={envio.error} />
      {inf.estado === "borrador" && <Aviso tipo="info" error="Borrador en preparación: lo puede ver, pero no modificar." />}
      {inf.estado === "reemplazado" && <Aviso tipo="info" error="Esta versión fue reemplazada por una posterior. Se conserva como registro." />}
      <article className="hoja-informe hoja-lectura">
        <header className="hoja-membrete">
          <img src={membrete} alt="Ministerio de Desarrollo Social · Dirección de Adultos Mayores · Gobierno de Tucumán" />
          {inf.caso?.area && <span className="hoja-area">{areaCorta(inf.caso.area).toUpperCase()}</span>}
        </header>
        <p className="hoja-lugar">
          {inf.lugar}, {fechaLarga(inf.fecha)}
        </p>
        {inf.estructura.destinatario && inf.destinatario && <p className="hoja-destinatario-texto">{inf.destinatario}</p>}
        {inf.estructura.mostrar_titulo && <h1 className="hoja-titulo">{inf.titulo}</h1>}
        <div className="hoja-datos">
          {inf.datos.map((d, i) => (
            <p key={i} className="hoja-dato-texto">
              <strong>{d.etiqueta}</strong>: {d.valor}
            </p>
          ))}
        </div>
        {inf.secciones.filter((s) => s.html.replace(/<[^>]+>|&nbsp;|\s/g, "") !== "").map((s, i) => (
          <section className="hoja-seccion" key={i}>
            {s.titulo && (
              <h2 className="seccion-titulo-texto">
                {inf.estructura.numerar ? `${++numero}. ` : ""}
                {s.titulo}
              </h2>
            )}
            {/* HTML limpiado en el servidor (solo párrafos, listas, negrita, cursiva y subrayado). */}
            <div className="editor-texto" dangerouslySetInnerHTML={{ __html: s.html }} />
          </section>
        ))}
        <div className="hoja-firmas">
          {inf.firmantes.map((f, i) => (
            <div className="hoja-firma" key={i}>
              <div className="linea-firma" />
              <strong>{f.nombre}</strong>
              {f.cargo && <span>{f.cargo}</span>}
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function fechaLarga(iso: string) {
  const [a, m, d] = iso.split("-").map(Number);
  return `${d} de ${MESES[m - 1]} de ${a}`;
}

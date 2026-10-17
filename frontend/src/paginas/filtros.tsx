// Filtros por cualquier campo. Se usan igual en las listas y en Estadísticas:
// «+ Filtro» → campo → comparación → valor. Cada filtro queda como una etiqueta
// que se toca para cambiarla. Viajan en la dirección (?f=…) para compartirlos.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Modal, fecha } from "../comun";

export interface Filtro {
  c: string;
  o: string;
  v?: unknown;
}

interface Opcion {
  valor: string;
  texto: string;
  nivel?: number;
}

export interface CampoFiltro {
  clave: string;
  etiqueta: string;
  grupo: string;
  tipo: "texto" | "opcion" | "multiple" | "fecha" | "numero" | "si_no";
  operadores: string[];
  opciones: Opcion[] | null;
}

export type Lista = "casos" | "legajos" | "expedientes" | "ingresos" | "recursos" | "contactos";

const TEXTO_OP: Record<string, string> = {
  contiene: "contiene",
  no_contiene: "no contiene",
  vacio: "sin dato",
  no_vacio: "con algún dato",
  es: "es",
  no_es: "no es",
  alguno: "incluye",
  todos: "incluye todos",
  ninguno: "no incluye",
  entre: "",
};

// ---------------------------------------------------------------- dirección (?f=…)

function parametrosHash(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split("?")[1] ?? "");
}

export function filtrosDeUrl(): Filtro[] {
  const t = parametrosHash().get("f");
  if (!t) return [];
  try {
    const v = JSON.parse(t);
    return Array.isArray(v) ? v.filter((x) => x && typeof x.c === "string") : [];
  } catch {
    return [];
  }
}

/** Filtros guardados en la dirección: se pueden copiar, compartir y volver atrás. */
export function useFiltrosUrl(): [Filtro[], (f: Filtro[]) => void] {
  const [filtros, setFiltros] = useState<Filtro[]>(filtrosDeUrl);
  const cambiar = (f: Filtro[]) => {
    setFiltros(f);
    const [base] = window.location.hash.split("?");
    const p = parametrosHash();
    if (f.length) p.set("f", JSON.stringify(f));
    else p.delete("f");
    const qs = p.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${base}${qs ? "?" + qs : ""}`);
  };
  return [filtros, cambiar];
}

export function rutaConFiltros(ruta: string, f: Filtro[]): string {
  return f.length ? `${ruta}?f=${encodeURIComponent(JSON.stringify(f))}` : ruta;
}

export function parametroF(f: Filtro[]): string | undefined {
  return f.length ? JSON.stringify(f) : undefined;
}

// ---------------------------------------------------------------- catálogo

const cache = new Map<Lista, Promise<CampoFiltro[]>>();

export function useCampos(lista: Lista): CampoFiltro[] | null {
  const [campos, setCampos] = useState<CampoFiltro[] | null>(null);
  useEffect(() => {
    if (!cache.has(lista)) cache.set(lista, api.get<CampoFiltro[]>(`/filtros/${lista}`).catch((e) => (cache.delete(lista), Promise.reject(e))));
    let vivo = true;
    cache
      .get(lista)!
      .then((c) => vivo && setCampos(c))
      .catch(() => vivo && setCampos([]));
    return () => {
      vivo = false;
    };
  }, [lista]);
  return campos;
}

// ---------------------------------------------------------------- texto de un filtro

function textoValor(campo: CampoFiltro, f: Filtro): string {
  if (f.o === "vacio" || f.o === "no_vacio") return "";
  const v = f.v as any;
  switch (campo.tipo) {
    case "texto":
      return `«${v}»`;
    case "si_no":
      return v ? "sí" : "no";
    case "fecha":
      return v?.desde && v?.hasta ? `del ${fecha(v.desde)} al ${fecha(v.hasta)}` : v?.desde ? `desde el ${fecha(v.desde)}` : `hasta el ${fecha(v?.hasta)}`;
    case "numero":
      return v?.desde != null && v?.desde !== "" && v?.hasta != null && v?.hasta !== ""
        ? `de ${v.desde} a ${v.hasta}`
        : v?.desde != null && v?.desde !== ""
          ? `desde ${v.desde}`
          : `hasta ${v?.hasta}`;
    default: {
      const textos = (Array.isArray(v) ? v : [v]).map((x: string) => campo.opciones?.find((o) => o.valor === x)?.texto ?? x);
      return textos.join(f.o === "todos" ? " y " : " o ");
    }
  }
}

export function textoFiltro(campo: CampoFiltro | undefined, f: Filtro): string {
  if (!campo) return f.c;
  if (campo.tipo === "si_no") return `${campo.etiqueta}: ${textoValor(campo, f)}`;
  return [campo.etiqueta, TEXTO_OP[f.o] ?? f.o, textoValor(campo, f)].filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- barra

export function BarraFiltros({
  lista,
  filtros,
  alCambiar,
  total,
  mostrados,
  sustantivo = ["resultado", "resultados"],
}: {
  lista: Lista;
  filtros: Filtro[];
  alCambiar: (f: Filtro[]) => void;
  total?: number | null;
  mostrados?: number;
  sustantivo?: [string, string];
}) {
  const campos = useCampos(lista);
  const [editando, setEditando] = useState<number | "nuevo" | null>(null);
  const porClave = useMemo(() => new Map((campos ?? []).map((c) => [c.clave, c])), [campos]);
  return (
    <div className="barra-filtros">
      <div className="barra-filtros-chips">
        {filtros.map((f, i) => (
          <span key={i} className="chip-filtro">
            <button type="button" className="chip-filtro-texto" onClick={() => setEditando(i)} title="Cambiar este filtro">
              {textoFiltro(porClave.get(f.c), f)}
            </button>
            <button type="button" className="chip-filtro-quitar" aria-label="Quitar filtro" onClick={() => alCambiar(filtros.filter((_, j) => j !== i))}>
              ×
            </button>
          </span>
        ))}
        <button type="button" className="boton boton-chico" onClick={() => setEditando("nuevo")} disabled={!campos}>
          + Filtro
        </button>
        {filtros.length > 1 && (
          <button type="button" className="boton-enlace" onClick={() => alCambiar([])}>
            Quitar todos
          </button>
        )}
        {total != null && (
          <span className="barra-filtros-total" aria-live="polite">
            {total} {total === 1 ? sustantivo[0] : sustantivo[1]}
            {mostrados != null && mostrados < total ? ` · se muestran ${mostrados}` : ""}
          </span>
        )}
      </div>
      {editando !== null && campos && (
        <Modal titulo={editando === "nuevo" ? "Agregar filtro" : "Cambiar filtro"} alCerrar={() => setEditando(null)}>
          <EditorFiltro
            campos={campos}
            inicial={editando === "nuevo" ? null : filtros[editando]}
            alGuardar={(f) => {
              alCambiar(editando === "nuevo" ? [...filtros, f] : filtros.map((x, j) => (j === editando ? f : x)));
              setEditando(null);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- editor

function hoyIso(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function atajosFecha(): { texto: string; desde: string; hasta: string }[] {
  const h = new Date();
  const y = h.getFullYear();
  const m = h.getMonth();
  const hace = (dias: number) => hoyIso(new Date(y, m, h.getDate() - dias));
  return [
    { texto: "Este mes", desde: hoyIso(new Date(y, m, 1)), hasta: hoyIso(h) },
    { texto: "Mes pasado", desde: hoyIso(new Date(y, m - 1, 1)), hasta: hoyIso(new Date(y, m, 0)) },
    { texto: "Últimos 30 días", desde: hace(30), hasta: hoyIso(h) },
    { texto: "Este año", desde: `${y}-01-01`, hasta: hoyIso(h) },
    { texto: "Año pasado", desde: `${y - 1}-01-01`, hasta: `${y - 1}-12-31` },
  ];
}

export function EditorFiltro({ campos, inicial, alGuardar }: { campos: CampoFiltro[]; inicial: Filtro | null; alGuardar: (f: Filtro) => void }) {
  const [clave, setClave] = useState(inicial?.c ?? "");
  const [buscar, setBuscar] = useState("");
  const campo = campos.find((c) => c.clave === clave);
  const [op, setOp] = useState(inicial?.o ?? "");
  const [valor, setValor] = useState<any>(inicial?.v ?? null);
  const [error, setError] = useState("");

  const elegir = (c: CampoFiltro) => {
    setClave(c.clave);
    setOp(c.operadores[0]);
    setValor(c.tipo === "si_no" ? true : c.tipo === "fecha" || c.tipo === "numero" ? { desde: "", hasta: "" } : c.tipo === "texto" ? "" : []);
    setError("");
  };

  if (!campo) {
    const q = buscar.trim().toLowerCase();
    const visibles = campos.filter((c) => !q || c.etiqueta.toLowerCase().includes(q) || c.grupo.toLowerCase().includes(q));
    const grupos = [...new Set(visibles.map((c) => c.grupo))];
    return (
      <div className="editor-filtro">
        <input type="search" autoFocus placeholder="Buscar un campo (edad, indicadores, departamento…)" value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label="Buscar campo" />
        <div className="editor-filtro-campos">
          {grupos.map((g) => (
            <div key={g}>
              <h3>{g}</h3>
              <div className="editor-filtro-lista">
                {visibles
                  .filter((c) => c.grupo === g)
                  .map((c) => (
                    <button type="button" key={c.clave} className="campo-filtro" onClick={() => elegir(c)}>
                      {c.etiqueta}
                    </button>
                  ))}
              </div>
            </div>
          ))}
          {visibles.length === 0 && <p className="tenue">Ningún campo coincide.</p>}
        </div>
      </div>
    );
  }

  const sinValor = op === "vacio" || op === "no_vacio";
  const guardar = () => {
    let v = valor;
    if (!sinValor) {
      if (campo.tipo === "texto" && !String(v ?? "").trim()) return setError("Escribí el texto a buscar.");
      if ((campo.tipo === "opcion" || campo.tipo === "multiple") && (!Array.isArray(v) || v.length === 0)) return setError("Elegí al menos una opción.");
      if ((campo.tipo === "fecha" || campo.tipo === "numero") && !v?.desde && v?.desde !== 0 && !v?.hasta && v?.hasta !== 0)
        return setError("Indicá al menos uno de los dos extremos.");
      if (campo.tipo === "numero") v = { desde: v.desde === "" ? null : Number(v.desde), hasta: v.hasta === "" ? null : Number(v.hasta) };
      if (campo.tipo === "fecha") v = { desde: v.desde || null, hasta: v.hasta || null };
    }
    alGuardar(sinValor ? { c: campo.clave, o: op } : { c: campo.clave, o: op, v });
  };

  return (
    <form
      className="editor-filtro formulario"
      onSubmit={(e) => {
        e.preventDefault();
        guardar();
      }}
    >
      <p className="editor-filtro-campo">
        <span className="tenue">{campo.grupo} ·</span> <strong>{campo.etiqueta}</strong>{" "}
        {!inicial && (
          <button type="button" className="boton-enlace" onClick={() => setClave("")}>
            cambiar campo
          </button>
        )}
      </p>
      {campo.tipo !== "si_no" && campo.operadores.length > 1 && (
        <div className="segmentado segmentado-envolver" role="radiogroup" aria-label="Comparación">
          {campo.operadores.map((o) => (
            <button type="button" key={o} role="radio" aria-checked={op === o} className={op === o ? "activo" : ""} onClick={() => setOp(o)}>
              {o === "entre" ? (campo.tipo === "fecha" ? "entre fechas" : "entre valores") : TEXTO_OP[o]}
            </button>
          ))}
        </div>
      )}
      {!sinValor && <ValorFiltro campo={campo} valor={valor} alCambiar={setValor} />}
      {error && <p className="texto-alerta">{error}</p>}
      <div className="fila-botones">
        <button className="boton boton-primario">{inicial ? "Aplicar" : "Agregar filtro"}</button>
      </div>
    </form>
  );
}

function ValorFiltro({ campo, valor, alCambiar }: { campo: CampoFiltro; valor: any; alCambiar: (v: any) => void }) {
  const [buscar, setBuscar] = useState("");
  switch (campo.tipo) {
    case "texto":
      return <input autoFocus value={valor ?? ""} onChange={(e) => alCambiar(e.target.value)} aria-label="Texto" />;
    case "si_no":
      return (
        <div className="opciones-linea">
          {[
            [true, "Sí"],
            [false, "No"],
          ].map(([v, t]) => (
            <label key={String(v)} className="casilla">
              <input type="radio" checked={valor === v} onChange={() => alCambiar(v)} /> {t as string}
            </label>
          ))}
        </div>
      );
    case "fecha":
      return (
        <>
          <div className="opciones-linea">
            {atajosFecha().map((a) => (
              <button type="button" key={a.texto} className="boton boton-chico" onClick={() => alCambiar({ desde: a.desde, hasta: a.hasta })}>
                {a.texto}
              </button>
            ))}
          </div>
          <div className="grilla">
            <label className="campo">
              <span>Desde</span>
              <input type="date" value={valor?.desde ?? ""} onChange={(e) => alCambiar({ ...valor, desde: e.target.value })} />
            </label>
            <label className="campo">
              <span>Hasta</span>
              <input type="date" value={valor?.hasta ?? ""} min={valor?.desde || undefined} onChange={(e) => alCambiar({ ...valor, hasta: e.target.value })} />
            </label>
          </div>
        </>
      );
    case "numero":
      return (
        <>
          {campo.clave.endsWith(".edad") && (
            <div className="opciones-linea">
              {[
                ["60 a 69", 60, 69],
                ["70 a 79", 70, 79],
                ["80 a 89", 80, 89],
                ["90 o más", 90, ""],
              ].map(([t, d, h]) => (
                <button type="button" key={t as string} className="boton boton-chico" onClick={() => alCambiar({ desde: d, hasta: h })}>
                  {t}
                </button>
              ))}
            </div>
          )}
          <div className="grilla">
            <label className="campo">
              <span>Desde</span>
              <input type="number" inputMode="numeric" value={valor?.desde ?? ""} onChange={(e) => alCambiar({ ...valor, desde: e.target.value })} />
            </label>
            <label className="campo">
              <span>Hasta</span>
              <input type="number" inputMode="numeric" value={valor?.hasta ?? ""} onChange={(e) => alCambiar({ ...valor, hasta: e.target.value })} />
            </label>
          </div>
        </>
      );
    default: {
      const elegidos: string[] = Array.isArray(valor) ? valor : [];
      const ops = campo.opciones ?? [];
      const q = buscar.trim().toLowerCase();
      const alternar = (v: string) => alCambiar(elegidos.includes(v) ? elegidos.filter((x) => x !== v) : [...elegidos, v]);
      return (
        <>
          {ops.length > 10 && <input type="search" placeholder="Buscar opción" value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label="Buscar opción" />}
          <div className="editor-filtro-opciones">
            {ops
              .filter((o) => !q || o.texto.toLowerCase().includes(q) || elegidos.includes(o.valor))
              .map((o) => (
                <label key={o.valor} className={`casilla ${o.nivel ? "opcion-sub" : ""}`}>
                  <input type="checkbox" checked={elegidos.includes(o.valor)} onChange={() => alternar(o.valor)} /> {o.nivel ? o.texto.split(": ").slice(1).join(": ") : o.texto}
                </label>
              ))}
            {ops.length === 0 && <p className="tenue">Todavía no hay valores cargados para este campo.</p>}
          </div>
        </>
      );
    }
  }
}

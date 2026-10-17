// Estadísticas: «Casos» y «Funcionamiento interno». Cada número que tiene un filtro
// equivalente se puede tocar para abrir la lista de esos casos.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Aviso, Cargando, Enlace, fecha, navegar, useSesion } from "../comun";
import { BarraFiltros, parametroF, rutaConFiltros, useFiltrosUrl, type Filtro } from "./filtros";

interface Fila {
  etiqueta: string;
  cantidad?: number;
  pct?: number | null;
  filtro?: Filtro[] | null;
  sin_dato?: boolean;
  area?: string;
  [k: string]: unknown;
}

interface Tabla {
  clave: string;
  titulo: string;
  filas: Fila[];
  base: number | null;
  nota: string | null;
  columnas: string[] | null;
}

interface Dato {
  clave: string;
  etiqueta: string;
  valor: number | null;
  pct?: number | null;
  nota?: string;
  unidad?: string;
  filtro?: Filtro[];
}

interface Casos {
  periodo: { desde: string; hasta: string };
  base: Filtro[];
  periodo_filtro: Filtro;
  total: number;
  resumen: Dato[];
  mensual: { etiqueta: string; ingresados: number; cerrados: number; filtro: Filtro[] }[];
  secciones: { titulo: string; tablas: Tabla[] }[];
}

interface Bloque {
  resumen: Dato[];
  tablas: Tabla[];
  periodo?: { desde: string; hasta: string };
  recortado?: boolean;
}

interface Interno {
  periodo: { desde: string; hasta: string };
  carga: Bloque | null;
  asistencia: Bloque | null;
  circuitos: Bloque | null;
  comunicacion: Bloque | null;
}

const COLUMNAS: Record<string, string> = {
  cantidad: "Cantidad",
  activos: "Activos",
  sin_actividad: "Sin movimiento",
  asignados: "Asignados",
  cerrados: "Cerrados",
  evoluciones: "Evoluciones",
  sin_responsable: "Sin técnico/a",
  personas: "Personas",
  jornadas: "Jornadas",
  con_incidencias: "Con incidencias",
  pendientes: "Pendientes",
  horas: "Horas sin justificar",
  pedidos: "Pedidos",
  dias: "Días",
  fecha: "Publicada",
  para: "Para",
  destinatarios: "Destinatarios",
  confirmaron: "Confirmaron",
  pct: "% confirmado",
  area: "Área",
};

const num = (v: unknown) =>
  v === null || v === undefined ? "—" : typeof v === "number" ? v.toLocaleString("es-AR", { maximumFractionDigits: 1 }) : String(v);
const corta = (a: string) => a.replace(/^(Departamento|División) /, "");

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function atajos() {
  const h = new Date();
  const y = h.getFullYear();
  const m = h.getMonth();
  return [
    { texto: "Este mes", desde: iso(new Date(y, m, 1)), hasta: iso(h) },
    { texto: "Mes pasado", desde: iso(new Date(y, m - 1, 1)), hasta: iso(new Date(y, m, 0)) },
    { texto: "Este año", desde: `${y}-01-01`, hasta: iso(h) },
    { texto: "Últimos 12 meses", desde: iso(new Date(y - 1, m, h.getDate() + 1)), hasta: iso(h) },
    { texto: "Año pasado", desde: `${y - 1}-01-01`, hasta: `${y - 1}-12-31` },
  ];
}

function leerPreferencia<T>(clave: string, defecto: T): T {
  try {
    const v = sessionStorage.getItem(clave);
    return v ? (JSON.parse(v) as T) : defecto;
  } catch {
    return defecto;
  }
}

function guardarPreferencia(clave: string, valor: unknown) {
  try {
    sessionStorage.setItem(clave, JSON.stringify(valor));
  } catch {
    /* sin almacenamiento */
  }
}

// ---------------------------------------------------------------- página

export function PaginaEstadisticas() {
  const { yo, catalogos } = useSesion();
  const alcance = yo.permisos["estadisticas.consultar"];
  const soloAsistencia = !alcance;
  const [pestana, setPestana] = useState<"casos" | "interno">(() => (soloAsistencia ? "interno" : leerPreferencia("sulam.est.pestana", "casos")));
  const [periodo, setPeriodo] = useState(() => leerPreferencia("sulam.est.periodo", { desde: `${new Date().getFullYear()}-01-01`, hasta: iso(new Date()) }));
  const [area, setArea] = useState<string>(() => leerPreferencia("sulam.est.area", ""));
  const [filtros, setFiltros] = useFiltrosUrl();
  useEffect(() => guardarPreferencia("sulam.est.pestana", pestana), [pestana]);
  useEffect(() => guardarPreferencia("sulam.est.periodo", periodo), [periodo]);
  useEffect(() => guardarPreferencia("sulam.est.area", area), [area]);

  const params = {
    desde: periodo.desde,
    hasta: periodo.hasta,
    area_id: alcance === "todos" && area ? area : undefined,
    ...(pestana === "casos" ? { f: parametroF(filtros) } : {}),
  };
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
  const areaFiltro: Filtro[] = alcance === "todos" && area ? [{ c: "caso.area", o: "es", v: [area] }] : [];

  return (
    <>
      <div className="titulo-pagina">
        <h1>Estadísticas</h1>
        <div className="fila-botones">
          <a className="boton" href={`/api/estadisticas/${pestana}.xlsx?${qs}`}>
            Descargar Excel
          </a>
          <a className="boton" href={`/api/estadisticas/${pestana}.pdf?${qs}`} target="_blank" rel="noreferrer">
            Informe PDF
          </a>
        </div>
      </div>
      {!soloAsistencia && (
        <div className="segmentado pestanas-est" role="tablist">
          <button role="tab" aria-selected={pestana === "casos"} className={pestana === "casos" ? "activo" : ""} onClick={() => setPestana("casos")}>
            Casos
          </button>
          <button role="tab" aria-selected={pestana === "interno"} className={pestana === "interno" ? "activo" : ""} onClick={() => setPestana("interno")}>
            Funcionamiento interno
          </button>
        </div>
      )}
      <div className="filtros filtros-est">
        <label className="campo-linea">
          Desde <input type="date" value={periodo.desde} max={periodo.hasta} onChange={(e) => e.target.value && setPeriodo({ ...periodo, desde: e.target.value })} />
        </label>
        <label className="campo-linea">
          Hasta <input type="date" value={periodo.hasta} min={periodo.desde} onChange={(e) => e.target.value && setPeriodo({ ...periodo, hasta: e.target.value })} />
        </label>
        <div className="opciones-linea">
          {atajos().map((a) => (
            <button
              type="button"
              key={a.texto}
              className={`boton boton-chico ${periodo.desde === a.desde && periodo.hasta === a.hasta ? "boton-elegido" : ""}`}
              onClick={() => setPeriodo({ desde: a.desde, hasta: a.hasta })}
            >
              {a.texto}
            </button>
          ))}
        </div>
        {alcance === "todos" ? (
          <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Área">
            <option value="">Toda la Dirección</option>
            {catalogos.areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        ) : alcance ? (
          <span className="tenue">Área: {yo.area?.nombre ?? "—"}</span>
        ) : null}
      </div>
      {pestana === "casos" ? (
        <>
          <BarraFiltros lista="casos" filtros={filtros} alCambiar={setFiltros} />
          <EstadCasos params={params} />
        </>
      ) : (
        <EstadInterno params={params} areaFiltro={areaFiltro} />
      )}
    </>
  );
}

function useEstadisticas<T>(ruta: string, params: Record<string, string | undefined>) {
  const clave = JSON.stringify(params);
  const [estado, setEstado] = useState<{ datos: T | null; error: unknown; cargando: boolean }>({ datos: null, error: null, cargando: true });
  useEffect(() => {
    let vivo = true;
    setEstado((e) => ({ ...e, cargando: true, error: null }));
    api
      .get<T>(ruta, params)
      .then((d) => vivo && setEstado({ datos: d, error: null, cargando: false }))
      .catch((e) => vivo && setEstado((x) => ({ ...x, error: e, cargando: false })));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta, clave]);
  return estado;
}

// ---------------------------------------------------------------- casos

function EstadCasos({ params }: { params: Record<string, string | undefined> }) {
  const { datos: d, error, cargando } = useEstadisticas<Casos>("/estadisticas/casos", params);
  if (error) return <Aviso error={error} />;
  if (!d) return <Cargando />;
  const aCasos = (f: Filtro[] | null | undefined) => (f ? rutaConFiltros("/casos", [...d.base, d.periodo_filtro, ...f]) : null);
  const aCasosSinPeriodo = (f: Filtro[] | null | undefined) => (f ? rutaConFiltros("/casos", [...d.base, ...f]) : null);
  return (
    <div className={`estadisticas ${cargando ? "estadisticas-cargando" : ""}`} aria-busy={cargando}>
      <p className="tenue">
        Casos con fecha de ingreso entre el {fecha(d.periodo.desde)} y el {fecha(d.periodo.hasta)}. Tocá una barra o un número para ver esos casos.
      </p>
      <Tiles
        datos={d.resumen}
        enlace={(r) => (r.clave === "activos" || r.clave === "cerrados" || r.clave === "reiteraciones" ? aCasosSinPeriodo(r.filtro) : r.filtro ? aCasos(r.filtro.slice(1)) : null)}
      />
      <section className="est-bloque">
        <h2>Ingresos y cierres por mes</h2>
        <Columnas mensual={d.mensual} enlace={(m) => rutaConFiltros("/casos", [...d.base, ...m.filtro])} />
      </section>
      {d.total === 0 ? (
        <Aviso tipo="info" error="No hay casos ingresados en el período con esos filtros." />
      ) : (
        d.secciones.map((s) => (
          <section key={s.titulo} className="est-bloque">
            <h2>{s.titulo}</h2>
            <div className="est-grilla">
              {s.tablas.map((t) => (
                <TablaGrafico key={t.clave} t={t} enlace={(f) => aCasos(f.filtro)} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}

// ---------------------------------------------------------------- interno

function EstadInterno({ params, areaFiltro }: { params: Record<string, string | undefined>; areaFiltro: Filtro[] }) {
  const { datos: d, error, cargando } = useEstadisticas<Interno>("/estadisticas/interno", params);
  if (error) return <Aviso error={error} />;
  if (!d) return <Cargando />;
  const aCasos = (f: Filtro[] | null | undefined) => (f ? rutaConFiltros("/casos", [...areaFiltro, ...f]) : null);
  const bloques: [keyof Interno, string, string][] = [
    ["carga", "Carga de trabajo y tiempos", "Casos activos, técnicos y tiempos de respuesta."],
    ["asistencia", "Asistencia del personal", "Jornadas del reloj evaluadas con las reglas fijas, licencias y comisiones."],
    ["circuitos", "Circuitos administrativos", "Mesa de Entrada, pases de carpetas, informes y digitalización."],
    ["comunicacion", "Comunicación interna", "Novedades publicadas y confirmación de lectura."],
  ];
  return (
    <div className={`estadisticas ${cargando ? "estadisticas-cargando" : ""}`} aria-busy={cargando}>
      {bloques.map(([clave, titulo, sub]) => {
        const b = d[clave] as Bloque | null;
        if (!b) return null;
        return (
          <section key={clave} className="est-bloque">
            <h2>{titulo}</h2>
            <p className="tenue">
              {sub}
              {b.recortado && b.periodo && ` Calculado desde el ${fecha(b.periodo.desde)} (máximo un año).`}
            </p>
            <Tiles datos={b.resumen} enlace={(r) => aCasos(r.filtro)} />
            <div className="est-grilla">
              {b.tablas.map((t) => (
                <TablaGrafico key={t.clave} t={t} enlace={(f) => aCasos(f.filtro)} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- piezas

function Tiles({ datos, enlace }: { datos: Dato[]; enlace: (d: Dato) => string | null }) {
  return (
    <div className="est-tiles">
      {datos.map((r) => {
        const a = enlace(r);
        const contenido = (
          <>
            <span className="est-tile-valor">
              {num(r.valor)}
              {r.unidad && r.valor != null ? ` ${r.unidad}` : ""}
            </span>
            <span className="est-tile-texto">{r.etiqueta}</span>
            {(r.nota || r.pct != null) && <span className="est-tile-nota">{r.nota ?? `${num(r.pct)} % del total`}</span>}
          </>
        );
        return a ? (
          <Enlace key={r.clave} a={a} className="est-tile est-tile-enlace">
            {contenido}
          </Enlace>
        ) : (
          <div key={r.clave} className="est-tile">
            {contenido}
          </div>
        );
      })}
    </div>
  );
}

/** Una tabla con su gráfico: barras horizontales si es una sola cantidad; tabla si tiene varias columnas. */
function TablaGrafico({ t, enlace }: { t: Tabla; enlace: (f: Fila) => string | null }) {
  const [verTabla, setVerTabla] = useState(false);
  const multi = Boolean(t.columnas && t.columnas.length);
  const columnas = useMemo(() => {
    const c = multi ? [...t.columnas!] : ["cantidad", ...(t.base != null ? ["pct"] : [])];
    return t.filas.some((f) => f.area) ? ["area", ...c] : c;
  }, [t, multi]);
  const ancho = multi || t.filas.length > 12 || t.clave.startsWith("asistencia_personas") || t.clave === "novedades";
  return (
    <figure className={`est-figura ${ancho ? "est-figura-ancha" : ""}`}>
      <figcaption>
        <span className="est-figura-titulo">{t.titulo}</span>
        {!multi && t.filas.length > 0 && (
          <button type="button" className="boton-enlace" onClick={() => setVerTabla(!verTabla)}>
            {verTabla ? "Ver gráfico" : "Ver tabla"}
          </button>
        )}
      </figcaption>
      {t.nota && <p className="est-nota">{t.nota}</p>}
      {t.filas.length === 0 ? (
        <p className="tenue">Sin datos en el período.</p>
      ) : multi || verTabla ? (
        <div className="tabla-desplazable">
          <table className="tabla tabla-compacta est-tabla">
            <thead>
              <tr>
                <th />
                {columnas.map((c) => (
                  <th key={c} className={c === "area" || c === "para" ? "" : "num"}>
                    {c === "pct" && !multi ? "%" : COLUMNAS[c] ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.filas.map((f, i) => {
                const a = enlace(f);
                return (
                  <tr key={i}>
                    <td>{a ? <Enlace a={a}>{f.etiqueta}</Enlace> : f.etiqueta}</td>
                    {columnas.map((c) => (
                      <td key={c} className={c === "area" || c === "para" ? "" : "num"}>
                        {c === "area" ? corta(String(f.area ?? "")) : c === "fecha" && f.fecha ? fecha(String(f.fecha)) : c === "pct" && f.pct != null ? `${num(f.pct)} %` : num(f[c])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <Barras filas={t.filas} enlace={enlace} />
      )}
    </figure>
  );
}

function Barras({ filas, enlace }: { filas: Fila[]; enlace: (f: Fila) => string | null }) {
  const max = Math.max(1, ...filas.map((f) => f.cantidad ?? 0));
  return (
    <ul className="est-barras">
      {filas.map((f, i) => {
        const a = enlace(f);
        const valor = `${num(f.cantidad)}${f.pct != null ? ` · ${num(f.pct)} %` : ""}`;
        const contenido = (
          <>
            <span className="est-barra-etiqueta">{corta(f.etiqueta)}</span>
            <span className="est-barra-pista" aria-hidden>
              <span className={`est-barra ${f.sin_dato ? "est-barra-sin" : ""}`} style={{ width: `${Math.max(0.6, (100 * (f.cantidad ?? 0)) / max)}%` }} />
              <span className="est-barra-valor">{valor}</span>
            </span>
          </>
        );
        return (
          <li key={i}>
            {a ? (
              <a href={"#" + a} className="est-barra-fila est-barra-enlace" title={`${f.etiqueta}: ${valor}. Ver estos casos.`} aria-label={`${f.etiqueta}: ${valor}. Ver estos casos`}>
                {contenido}
              </a>
            ) : (
              <div className="est-barra-fila" title={`${f.etiqueta}: ${valor}`}>
                {contenido}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Columnas({ mensual, enlace }: { mensual: Casos["mensual"]; enlace: (m: Casos["mensual"][number]) => string }) {
  const [verTabla, setVerTabla] = useState(false);
  const max = Math.max(1, ...mensual.flatMap((m) => [m.ingresados, m.cerrados]));
  return (
    <figure className="est-figura est-figura-ancha">
      <figcaption>
        <span className="est-leyenda">
          <span className="est-clave est-clave-1" aria-hidden /> Ingresados <span className="est-clave est-clave-2" aria-hidden /> Cerrados
        </span>
        <button type="button" className="boton-enlace" onClick={() => setVerTabla(!verTabla)}>
          {verTabla ? "Ver gráfico" : "Ver tabla"}
        </button>
      </figcaption>
      {verTabla ? (
        <table className="tabla tabla-compacta est-tabla">
          <thead>
            <tr>
              <th>Mes</th>
              <th className="num">Ingresados</th>
              <th className="num">Cerrados</th>
            </tr>
          </thead>
          <tbody>
            {mensual.map((m) => (
              <tr key={m.etiqueta}>
                <td>{m.etiqueta}</td>
                <td className="num">
                  <Enlace a={enlace(m)}>{m.ingresados}</Enlace>
                </td>
                <td className="num">{m.cerrados}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="est-columnas" role="img" aria-label={mensual.map((m) => `${m.etiqueta}: ${m.ingresados} ingresados, ${m.cerrados} cerrados`).join("; ")}>
          {mensual.map((m) => (
            <button
              type="button"
              key={m.etiqueta}
              className="est-columna-grupo"
              title={`${m.etiqueta}\n${m.ingresados} ingresados\n${m.cerrados} cerrados\nTocá para ver los ingresados`}
              onClick={() => navegar(enlace(m))}
            >
              <span className="est-columna-pares">
                <span className="est-columna est-columna-1" style={{ height: `${(100 * m.ingresados) / max}%` }}>
                  {m.ingresados > 0 && <span className="est-columna-valor">{m.ingresados}</span>}
                </span>
                <span className="est-columna est-columna-2" style={{ height: `${(100 * m.cerrados) / max}%` }}>
                  {m.cerrados > 0 && <span className="est-columna-valor">{m.cerrados}</span>}
                </span>
              </span>
              <span className="est-columna-mes">{m.etiqueta}</span>
            </button>
          ))}
        </div>
      )}
    </figure>
  );
}

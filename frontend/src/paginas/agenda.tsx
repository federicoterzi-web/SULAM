import { useMemo, useState, type FormEvent } from "react";
import { api, type Caso, type PersonaResumen } from "../api";
import { Aviso, Campo, Cargando, Modal, Vacio, useDatos, useEnvio, useSesion } from "../comun";
import { BuscarLegajo } from "./bandeja";
import { DetalleEvento } from "./participacion";
import { RecorridoSalida } from "./recorrido";

export interface Actividad {
  id: string;
  tipo: string;
  tipo_texto: string;
  titulo: string;
  descripcion: string | null;
  inicio: string;
  fin: string | null;
  todo_el_dia: boolean;
  lugar: string | null;
  area: { id: number; nombre: string } | null;
  persona: { id: string | null; nombre: string; legajo: string | null } | null;
  caso: { id: string; numero: string } | null;
  estado: "programado" | "realizado" | "no_realizado" | "cancelado";
  resultado: string | null;
  resuelto_por: string | null;
  resuelto_en: string | null;
  participantes: { id: string; nombre: string }[];
  creado_por: string | null;
  soy_participante: boolean;
  puedo_modificar: boolean;
  serie_id: string | null;
  repeticion: string | null;
  repeticion_texto: string | null;
  historial?: Cambio[];
  en_la_serie?: { total: number; siguientes: number };
}

export interface Cambio {
  en: string;
  por: string;
  motivo: string | null;
  cambios: { campo: string; texto: string; antes: string | boolean | null; despues: string | boolean | null }[];
}

interface Superpuestos {
  vencimientos: { fecha: string; documento_id: string; tipo: string; persona: { id: string; nombre: string } }[];
  ausencias: { desde: string; hasta: string; agente: string; usuario_id: string | null; tipo_texto: string; lugar: string | null; horas: string | null }[];
}

export const ESTADO: Record<string, string> = { programado: "Programada", realizado: "Realizada", no_realizado: "No realizada", cancelado: "Cancelada" };
export const ICONO: Record<string, string> = { programado: "🕒", realizado: "✔", no_realizado: "✖", cancelado: "⊘" };
const DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

export const dosDig = (n: number) => String(n).padStart(2, "0");
export const claveDia = (d: Date) => `${d.getFullYear()}-${dosDig(d.getMonth() + 1)}-${dosDig(d.getDate())}`;
export const hora = (a: Actividad) => (a.todo_el_dia ? "Todo el día" : new Date(a.inicio).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" }));
const diaLargo = (d: Date) => d.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
const lunesDe = (d: Date) => {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
};

type Ambito = "mio" | "area";

const FRECUENCIAS: [string, string][] = [
  ["", "No se repite"],
  ["diaria", "Todos los días hábiles"],
  ["semanal", "Todas las semanas"],
  ["quincenal", "Cada 15 días"],
  ["mensual", "Todos los meses"],
];

const fechaHora = (iso: string) => new Date(iso).toLocaleString("es-AR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const valorDe = (campo: string, v: string | boolean | null) =>
  v === null || v === "" ? "—" : typeof v === "boolean" ? (v ? "sí" : "no") : campo === "inicio" || campo === "fin" ? fechaHora(v) : String(v);
type Vista = "mes" | "lista";

export function PaginaAgenda({ movil = false }: { movil?: boolean }) {
  const { puede, yo } = useSesion();
  const alcance = yo.permisos["agenda.consultar"];
  const [ambito, setAmbito] = useState<Ambito>("mio");
  const [vista, setVista] = useState<Vista>(movil ? "lista" : "mes");
  const [mes, setMes] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [dia, setDia] = useState(() => claveDia(new Date()));
  const [abierta, setAbierta] = useState<Actividad | null>(null);
  const [nueva, setNueva] = useState<string | null>(null);
  const [quien, setQuien] = useState("");
  const [verVenc, setVerVenc] = useState(true);
  const [verAus, setVerAus] = useState(true);

  const rango = useMemo(() => {
    if (vista === "mes") {
      const d = lunesDe(mes);
      return { desde: d, hasta: new Date(d.getFullYear(), d.getMonth(), d.getDate() + 42) };
    }
    const h = new Date();
    return { desde: new Date(h.getFullYear(), h.getMonth(), h.getDate()), hasta: new Date(h.getFullYear(), h.getMonth(), h.getDate() + 21) };
  }, [vista, mes]);

  const { datos, error, recargar } = useDatos(
    () =>
      api.get<{ eventos: Actividad[] }>("/agenda", {
        desde: rango.desde.toISOString(),
        hasta: rango.hasta.toISOString(),
        ambito,
        ...(ambito !== "mio" && quien ? { usuario_id: quien } : {}),
      }),
    [rango.desde.getTime(), rango.hasta.getTime(), ambito, quien],
  );
  // Vencimientos de documentos y ausencias del personal: solo para mirar junto con la agenda.
  const sup = useDatos(
    () =>
      api.get<Superpuestos>("/agenda/superpuestos", {
        desde: rango.desde.toISOString(),
        hasta: rango.hasta.toISOString(),
        ambito,
        ...(ambito !== "mio" && quien ? { usuario_id: quien } : {}),
      }),
    [rango.desde.getTime(), rango.hasta.getTime(), ambito, quien],
  );
  const gente = useDatos(
    () => (puede("agenda", "crear") ? api.get<{ id: string; nombre: string; area: string | null }[]>("/agenda/participantes") : Promise.resolve([])),
    [],
  );
  // Lo que ya pasó y quedó sin registrar el resultado.
  const pendientes = useDatos(
    () => {
      const h = new Date();
      return api.get<{ eventos: Actividad[] }>("/agenda", {
        desde: new Date(h.getFullYear(), h.getMonth(), h.getDate() - 60).toISOString(),
        hasta: new Date().toISOString(),
        ambito,
        estado: "programado",
        ...(ambito !== "mio" && quien ? { usuario_id: quien } : {}),
      });
    },
    [ambito, quien],
  );
  const refrescar = () => {
    recargar();
    pendientes.recargar();
  };

  const porDia = useMemo(() => {
    const m = new Map<string, Actividad[]>();
    for (const e of datos?.eventos ?? []) {
      const k = claveDia(new Date(e.inicio));
      m.set(k, [...(m.get(k) ?? []), e]);
    }
    return m;
  }, [datos]);

  // Lo de otros módulos, por día (las ausencias ocupan todos los días de su rango).
  const extraPorDia = useMemo(() => {
    const m = new Map<string, { venc: Superpuestos["vencimientos"]; aus: Superpuestos["ausencias"] }>();
    const nodo = (k: string) => m.get(k) ?? (m.set(k, { venc: [], aus: [] }), m.get(k)!);
    if (verVenc) for (const v of sup.datos?.vencimientos ?? []) nodo(v.fecha).venc.push(v);
    if (verAus)
      for (const a of sup.datos?.ausencias ?? []) {
        const fin = new Date(a.hasta + "T12:00:00");
        for (let d = new Date(a.desde + "T12:00:00"); d <= fin; d.setDate(d.getDate() + 1)) {
          const k = claveDia(d);
          if (k >= claveDia(rango.desde) && k < claveDia(rango.hasta) && ![6, 0].includes(d.getDay())) nodo(k).aus.push(a);
        }
      }
    return m;
  }, [sup.datos, verVenc, verAus, rango]);

  if (!puede("agenda", "consultar")) return <Aviso error="No tiene acceso a la agenda." />;

  const dias = Array.from({ length: 42 }, (_, i) => {
    const d = lunesDe(mes);
    d.setDate(d.getDate() + i);
    return d;
  });
  const hoy = claveDia(new Date());

  return (
    <div className={movil ? "agenda agenda-movil" : "agenda"}>
      {!movil && <h1>Agenda</h1>}
      <div className="agenda-barra">
        {alcance !== "propios" && (
          <div className="segmentado" role="group" aria-label="De quién">
            <button
              className={ambito === "mio" ? "activo" : ""}
              onClick={() => {
                setAmbito("mio");
                setQuien("");
              }}
              aria-pressed={ambito === "mio"}
            >
              La mía
            </button>
            <button className={ambito === "area" ? "activo" : ""} onClick={() => setAmbito("area")} aria-pressed={ambito === "area"}>
              De mi área
            </button>
          </div>
        )}
        {ambito !== "mio" && (gente.datos?.length ?? 0) > 1 && (
          <select aria-label="Persona" value={quien} onChange={(e) => setQuien(e.target.value)}>
            <option value="">Todas las personas</option>
            {gente.datos!.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nombre}
              </option>
            ))}
          </select>
        )}
        {!movil && (
          <div className="segmentado" role="group" aria-label="Vista">
            <button className={vista === "mes" ? "activo" : ""} onClick={() => setVista("mes")} aria-pressed={vista === "mes"}>
              Mes
            </button>
            <button className={vista === "lista" ? "activo" : ""} onClick={() => setVista("lista")} aria-pressed={vista === "lista"}>
              Próximos días
            </button>
          </div>
        )}
        {puede("agenda", "crear") && (
          <button className="boton boton-primario" onClick={() => setNueva(vista === "mes" ? dia : hoy)}>
            ＋ Nueva actividad
          </button>
        )}
      </div>
      <Aviso error={error} />
      <div className="agenda-superpuestos">
        <span className="tenue">También mostrar:</span>
        <label className="campo campo-casilla">
          <input type="checkbox" checked={verVenc} onChange={(e) => setVerVenc(e.target.checked)} /> Vencimientos de documentos
        </label>
        <label className="campo campo-casilla">
          <input type="checkbox" checked={verAus} onChange={(e) => setVerAus(e.target.checked)} /> Ausencias del personal
        </label>
      </div>

      {(pendientes.datos?.eventos.length ?? 0) > 0 && (
        <section className="agenda-pendientes" aria-label="Sin resultado">
          <strong>Falta registrar el resultado ({pendientes.datos!.eventos.length})</strong>
          <ul>
            {pendientes.datos!.eventos.slice(0, 6).map((e) => (
              <li key={e.id}>
                <button className="boton-enlace" onClick={() => setAbierta(e)}>
                  {new Date(e.inicio).toLocaleDateString("es-AR", { day: "numeric", month: "short" })} · {e.titulo === e.tipo_texto || e.titulo.startsWith(e.tipo_texto) ? e.titulo : `${e.tipo_texto}: ${e.titulo}`}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!datos && !error && <Cargando />}

      {datos && vista === "mes" && (
        <>
          <div className="agenda-mes-cabecera">
            <button className="boton boton-chico" onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))} aria-label="Mes anterior">
              ◀
            </button>
            <h2>{mes.toLocaleDateString("es-AR", { month: "long", year: "numeric" })}</h2>
            <button className="boton boton-chico" onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))} aria-label="Mes siguiente">
              ▶
            </button>
            <button
              className="boton boton-chico"
              onClick={() => {
                const h = new Date();
                setMes(new Date(h.getFullYear(), h.getMonth(), 1));
                setDia(claveDia(h));
              }}
            >
              Hoy
            </button>
          </div>
          <div className="agenda-grilla" role="grid">
            {DIAS.map((d) => (
              <div key={d} className="agenda-dia-nombre" role="columnheader">
                {d}
              </div>
            ))}
            {dias.map((d) => {
              const k = claveDia(d);
              const es = porDia.get(k) ?? [];
              return (
                <div
                  key={k}
                  role="gridcell"
                  tabIndex={0}
                  className={`agenda-celda ${d.getMonth() !== mes.getMonth() ? "fuera" : ""} ${k === hoy ? "hoy" : ""} ${k === dia ? "elegido" : ""}`}
                  onClick={() => setDia(k)}
                  onKeyDown={(e) => e.key === "Enter" && setDia(k)}
                >
                  <span className="agenda-num">{d.getDate()}</span>
                  {es.slice(0, 3).map((e) => (
                    <button
                      key={e.id}
                      className={`agenda-chip estado-${e.estado}`}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        setAbierta(e);
                      }}
                      title={`${hora(e)} · ${e.titulo}`}
                    >
                      {ICONO[e.estado]} {e.titulo}
                    </button>
                  ))}
                  {es.length > 3 && <span className="tenue">+{es.length - 3} más</span>}
                  {(extraPorDia.get(k)?.venc.length ?? 0) > 0 && (
                    <span className="agenda-marca agenda-marca-venc" title="Documentos que vencen">
                      📄 {extraPorDia.get(k)!.venc.length}
                    </span>
                  )}
                  {(extraPorDia.get(k)?.aus.length ?? 0) > 0 && (
                    <span className="agenda-marca agenda-marca-aus" title="Personal ausente">
                      🚫 {extraPorDia.get(k)!.aus.length}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <h2 className="agenda-titulo-dia">{diaLargo(new Date(dia + "T12:00:00"))}</h2>
          <ListaDia eventos={porDia.get(dia) ?? []} alAbrir={setAbierta} vacio="Nada agendado este día." />
          <ExtrasDelDia extra={extraPorDia.get(dia)} />
        </>
      )}

      {datos && vista === "lista" && <ProximosDias eventos={datos.eventos} alAbrir={setAbierta} extra={extraPorDia} />}

      {abierta && (
        <DetalleActividad
          actividad={abierta}
          alCerrar={() => setAbierta(null)}
          alCambiar={() => {
            setAbierta(null);
            refrescar();
          }}
        />
      )}
      {nueva && (
        <Modal titulo="Nueva actividad" alCerrar={() => setNueva(null)} ancho>
          <FormActividad
            diaInicial={nueva}
            alGuardar={() => {
              setNueva(null);
              refrescar();
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function ListaDia({ eventos, alAbrir, vacio }: { eventos: Actividad[]; alAbrir: (a: Actividad) => void; vacio: string }) {
  if (eventos.length === 0) return <Vacio>{vacio}</Vacio>;
  return (
    <ul className="agenda-lista">
      {eventos.map((e) => (
        <li key={e.id} className={`estado-${e.estado}`}>
          <button className="agenda-item" onClick={() => alAbrir(e)}>
            <span className="agenda-hora">{hora(e)}</span>
            <span>
              <strong>{e.titulo}</strong> <small className="tenue">· {e.tipo_texto}</small>
              <br />
              <small className="tenue">
                {ICONO[e.estado]} {ESTADO[e.estado]}
                {e.persona && ` · ${e.persona.nombre}`}
                {e.participantes.length > 0 && ` · ${e.participantes.map((p) => p.nombre).join(", ")}`}
              </small>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

type ExtraDia = { venc: Superpuestos["vencimientos"]; aus: Superpuestos["ausencias"] };

/** Vencimientos y ausencias del día: solo lectura. */
function ExtrasDelDia({ extra }: { extra?: ExtraDia }) {
  if (!extra || (extra.venc.length === 0 && extra.aus.length === 0)) return null;
  return (
    <ul className="agenda-extras">
      {extra.aus.map((a, i) => (
        <li key={`a${i}`}>
          🚫 <strong>{a.agente}</strong> · {a.tipo_texto}
          {a.lugar && ` (${a.lugar})`}
          {a.horas && ` · ${a.horas}`}
        </li>
      ))}
      {extra.venc.map((v) => (
        <li key={v.documento_id}>
          📄 Vence <strong>{v.tipo}</strong> · <a href={`#/legajos/${v.persona.id}`}>{v.persona.nombre}</a>
        </li>
      ))}
    </ul>
  );
}

function ProximosDias({ eventos, alAbrir, extra }: { eventos: Actividad[]; alAbrir: (a: Actividad) => void; extra: Map<string, ExtraDia> }) {
  const grupos = new Map<string, Actividad[]>();
  for (const e of eventos) {
    const k = claveDia(new Date(e.inicio));
    grupos.set(k, [...(grupos.get(k) ?? []), e]);
  }
  // Los días sin actividades pero con vencimientos o ausencias, dentro de las próximas semanas, también se muestran.
  for (const k of extra.keys()) if (!grupos.has(k) && k >= claveDia(new Date())) grupos.set(k, []);
  const ordenados = [...grupos.entries()].sort(([a], [b]) => (a < b ? -1 : 1));
  if (grupos.size === 0) return <Vacio>No hay nada agendado en los próximos días.</Vacio>;
  return (
    <>
      {ordenados.map(([k, es]) => (
        <section key={k}>
          <h2 className="agenda-titulo-dia">{diaLargo(new Date(k + "T12:00:00"))}</h2>
          <ListaDia eventos={es} alAbrir={alAbrir} vacio="" />
          <ExtrasDelDia extra={extra.get(k)} />
        </section>
      ))}
    </>
  );
}

// ---------------------------------------------------------------- detalle y resultado

function DetalleActividad({ actividad: base, alCerrar, alCambiar }: { actividad: Actividad; alCerrar: () => void; alCambiar: () => void }) {
  if (base.tipo === "evento") return <DetalleEvento id={base.id} alCerrar={alCerrar} alCambiar={alCambiar} />;
  return <DetalleComun actividad={base} alCerrar={alCerrar} alCambiar={alCambiar} />;
}

function DetalleComun({ actividad: base, alCerrar, alCambiar }: { actividad: Actividad; alCerrar: () => void; alCambiar: () => void }) {
  const completa = useDatos(() => api.get<Actividad>(`/agenda/${base.id}`), [base.id]);
  const a = completa.datos ?? base;
  const siguientes = a.en_la_serie?.siguientes ?? 0;
  const [modo, setModo] = useState<"ver" | "editar" | "resultado">("ver");
  return (
    <Modal titulo={a.titulo} alCerrar={alCerrar} ancho>
      {modo === "editar" ? (
        <FormActividad actividad={a} alGuardar={alCambiar} siguientes={siguientes} />
      ) : (
        <>
          <dl className="agenda-detalle">
            <dt>Cuándo</dt>
            <dd>
              {new Date(a.inicio).toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })} · {hora(a)}
              {a.fin && !a.todo_el_dia && ` a ${new Date(a.fin).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}`}
            </dd>
            <dt>Clase</dt>
            <dd>{a.tipo_texto}</dd>
            {a.repeticion_texto && (
              <>
                <dt>Se repite</dt>
                <dd>
                  {a.repeticion_texto}
                  {a.en_la_serie && <small className="tenue"> · {a.en_la_serie.total} actividades en la serie</small>}
                </dd>
              </>
            )}
            {a.lugar && (
              <>
                <dt>Lugar</dt>
                <dd>{a.lugar}</dd>
              </>
            )}
            {a.persona && (
              <>
                <dt>Legajo</dt>
                <dd>{a.persona.id ? <a href={`#/legajos/${a.persona.id}`}>{a.persona.nombre}</a> : a.persona.nombre}</dd>
              </>
            )}
            {a.caso && (
              <>
                <dt>Caso</dt>
                <dd>{a.caso.numero}</dd>
              </>
            )}
            <dt>Participan</dt>
            <dd>{a.participantes.map((p) => p.nombre).join(", ") || "—"}</dd>
            {a.descripcion && (
              <>
                <dt>Detalle</dt>
                <dd>{a.descripcion}</dd>
              </>
            )}
            <dt>Estado</dt>
            <dd>
              {ICONO[a.estado]} {ESTADO[a.estado]}
              {a.resuelto_por && <small className="tenue"> · {a.resuelto_por}</small>}
            </dd>
            {a.resultado && (
              <>
                <dt>Resultado</dt>
                <dd>{a.resultado}</dd>
              </>
            )}
          </dl>
          {a.tipo === "salida" && modo === "ver" && <RecorridoSalida actividadId={a.id} />}
          {a.estado === "programado" && a.puedo_modificar && modo === "ver" && (
            <div className="fila-botones fila-izquierda">
              <button className="boton boton-primario" onClick={() => setModo("resultado")}>
                Registrar resultado
              </button>
              <button className="boton" onClick={() => setModo("editar")}>
                Editar o reprogramar
              </button>
            </div>
          )}
          {modo === "ver" && a.tipo !== "recordatorio" && (
            <div className="fila-botones fila-izquierda">
              <a className="boton" href={`/api/agenda/${a.id}/comision.docx`} title="Formulario de la Dirección, completado con quienes participan">
                Orden de salida en comisión (Word)
              </a>
            </div>
          )}
          {modo === "ver" && <HistorialCambios historial={a.historial} />}
          {modo === "resultado" && <FormResultado actividadId={a.id} siguientes={siguientes} alGuardar={alCambiar} alVolver={() => setModo("ver")} />}
        </>
      )}
    </Modal>
  );
}

/** Registrar cómo terminó una actividad (realizada, no realizada o cancelada). */
export function FormResultado({
  actividadId,
  siguientes,
  alGuardar,
  alVolver,
  etiqueta = "Cómo fue (queda en la evolución del caso)",
}: {
  actividadId: string;
  siguientes: number;
  alGuardar: () => void;
  alVolver: () => void;
  etiqueta?: string;
}) {
  const [estado, setEstado] = useState<"realizado" | "no_realizado" | "cancelado">("realizado");
  const [texto, setTexto] = useState("");
  const [aplicar, setAplicar] = useState<"esta" | "siguientes">("esta");
  const { enviando, error, ejecutar } = useEnvio();
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/agenda/${actividadId}/resultado`, { estado, resultado: texto || null, aplicar_a: estado === "cancelado" ? aplicar : "esta" }));
    if (r) alGuardar();
  };
  return (
    <form className="formulario" onSubmit={guardar}>
      <div className="segmentado" role="group" aria-label="Resultado">
        {(
          [
            ["realizado", "Se realizó"],
            ["no_realizado", "No se pudo realizar"],
            ["cancelado", "Se canceló"],
          ] as const
        ).map(([k, t]) => (
          <button type="button" key={k} className={estado === k ? "activo" : ""} aria-pressed={estado === k} onClick={() => setEstado(k)}>
            {t}
          </button>
        ))}
      </div>
      <Campo etiqueta={estado === "no_realizado" ? "Motivo *" : etiqueta}>
        <textarea rows={4} value={texto} maxLength={5000} required={estado === "no_realizado"} onChange={(e) => setTexto(e.target.value)} />
      </Campo>
      {estado === "cancelado" && siguientes > 0 && <AplicarA valor={aplicar} alCambiar={setAplicar} siguientes={siguientes} />}
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
        <button type="button" className="boton" onClick={alVolver}>
          Volver
        </button>
      </div>
    </form>
  );
}

export function HistorialCambios({ historial }: { historial?: Cambio[] }) {
  if (!historial || historial.length === 0) return null;
  return (
    <details className="agenda-historial">
      <summary>Historial de cambios ({historial.length})</summary>
      <ul>
        {historial.map((h, i) => (
          <li key={i}>
            <strong>{new Date(h.en).toLocaleString("es-AR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong> · {h.por}
            {h.motivo && <em> — {h.motivo}</em>}
            <ul>
              {h.cambios.map((c) => (
                <li key={c.campo}>
                  {c.texto}: {valorDe(c.campo, c.antes)} → {valorDe(c.campo, c.despues)}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function AplicarA({ valor, alCambiar, siguientes }: { valor: "esta" | "siguientes"; alCambiar: (v: "esta" | "siguientes") => void; siguientes: number }) {
  return (
    <fieldset className="agenda-quienes">
      <legend>Esta actividad se repite</legend>
      <label className="campo campo-casilla">
        <input type="radio" name="aplicar" checked={valor === "esta"} onChange={() => alCambiar("esta")} /> Solo esta
      </label>
      <label className="campo campo-casilla">
        <input type="radio" name="aplicar" checked={valor === "siguientes"} onChange={() => alCambiar("siguientes")} /> Esta y las {siguientes}{" "}
        {siguientes === 1 ? "siguiente" : "siguientes"}
      </label>
    </fieldset>
  );
}

// ---------------------------------------------------------------- alta y edición

export function FormActividad({
  actividad,
  diaInicial,
  alGuardar,
  siguientes = 0,
}: {
  actividad?: Actividad;
  diaInicial?: string;
  alGuardar: () => void;
  siguientes?: number;
}) {
  const { yo } = useSesion();
  const ini = actividad ? new Date(actividad.inicio) : null;
  const fin = actividad?.fin ? new Date(actividad.fin) : null;
  const tipos = useDatos(() => api.get<{ clave: string; texto: string }[]>("/agenda/tipos"), []);
  const gente = useDatos(() => api.get<{ id: string; nombre: string; area: string | null }[]>("/agenda/participantes"), []);
  const [tipo, setTipo] = useState(actividad?.tipo ?? "visita");
  const [titulo, setTitulo] = useState(actividad?.titulo ?? "");
  const [dia, setDia] = useState(ini ? claveDia(ini) : diaInicial ?? claveDia(new Date()));
  const [desde, setDesde] = useState(ini && !actividad?.todo_el_dia ? `${dosDig(ini.getHours())}:${dosDig(ini.getMinutes())}` : "09:00");
  const [hasta, setHasta] = useState(fin && !actividad?.todo_el_dia ? `${dosDig(fin.getHours())}:${dosDig(fin.getMinutes())}` : "");
  const [todo, setTodo] = useState(actividad?.todo_el_dia ?? false);
  const [lugar, setLugar] = useState(actividad?.lugar ?? "");
  const [descripcion, setDescripcion] = useState(actividad?.descripcion ?? "");
  const [quienes, setQuienes] = useState<string[]>(actividad ? actividad.participantes.map((p) => p.id) : [yo.id]);
  const [persona, setPersona] = useState<PersonaResumen | null>(null);
  const [vinculoActual, setVinculoActual] = useState(actividad?.persona ?? null);
  const [casoId, setCasoId] = useState(actividad?.caso?.id ?? "");
  const personaId = persona?.id ?? vinculoActual?.id ?? null;
  const casos = useDatos(() => (personaId ? api.get<Caso[]>("/casos", { persona_id: personaId, limite: 50 }) : Promise.resolve([] as Caso[])), [personaId]);
  const [frecuencia, setFrecuencia] = useState("");
  const [terminaEn, setTerminaEn] = useState<"cantidad" | "hasta">("cantidad");
  const [cantidad, setCantidad] = useState(4);
  const [hastaDia, setHastaDia] = useState("");
  const [aplicar, setAplicar] = useState<"esta" | "siguientes">("esta");
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const inicio = new Date(`${dia}T${todo ? "00:00" : desde}:00`);
    const finDate = !todo && hasta ? new Date(`${dia}T${hasta}:00`) : null;
    const cuerpo = {
      tipo,
      titulo,
      descripcion: descripcion || null,
      inicio: inicio.toISOString(),
      fin: finDate ? finDate.toISOString() : null,
      todo_el_dia: todo,
      lugar: lugar || null,
      persona_id: personaId,
      caso_id: personaId && casoId ? casoId : null,
      participantes: quienes,
      ...(actividad
        ? { aplicar_a: aplicar, motivo: motivo || null }
        : frecuencia
          ? { repetir: { frecuencia, ...(terminaEn === "cantidad" ? { cantidad } : { hasta: hastaDia }) } }
          : {}),
    };
    const r = await ejecutar(() => (actividad ? api.patch(`/agenda/${actividad.id}`, cuerpo) : api.post("/agenda", cuerpo)));
    if (r) alGuardar();
  };

  const alternar = (id: string) => setQuienes((q) => (q.includes(id) ? q.filter((x) => x !== id) : [...q, id]));

  return (
    <form className="formulario" onSubmit={guardar}>
      <div className="grilla">
        <Campo etiqueta="Clase *">
          <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
            {(tipos.datos ?? []).map((t) => (
              <option key={t.clave} value={t.clave}>
                {t.texto}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Título *">
          <input value={titulo} maxLength={200} required onChange={(e) => setTitulo(e.target.value)} placeholder="Sin nombres de personas" />
        </Campo>
        <Campo etiqueta="Día *">
          <input type="date" value={dia} required onChange={(e) => setDia(e.target.value)} />
        </Campo>
        {!todo && (
          <>
            <Campo etiqueta="Desde *">
              <input type="time" value={desde} required onChange={(e) => setDesde(e.target.value)} />
            </Campo>
            <Campo etiqueta="Hasta">
              <input type="time" value={hasta} onChange={(e) => setHasta(e.target.value)} />
            </Campo>
          </>
        )}
        <label className="campo campo-casilla">
          <input type="checkbox" checked={todo} onChange={(e) => setTodo(e.target.checked)} /> Todo el día
        </label>
        <Campo etiqueta="Lugar">
          <input value={lugar} maxLength={300} onChange={(e) => setLugar(e.target.value)} />
        </Campo>
      </div>

      {!actividad && (
        <div className="grilla">
          <Campo etiqueta="Repetir">
            <select value={frecuencia} onChange={(e) => setFrecuencia(e.target.value)}>
              {FRECUENCIAS.map(([k, t]) => (
                <option key={k} value={k}>
                  {t}
                </option>
              ))}
            </select>
          </Campo>
          {frecuencia && (
            <>
              <Campo etiqueta="Termina">
                <select value={terminaEn} onChange={(e) => setTerminaEn(e.target.value as "cantidad" | "hasta")}>
                  <option value="cantidad">Después de cierta cantidad</option>
                  <option value="hasta">En un día</option>
                </select>
              </Campo>
              {terminaEn === "cantidad" ? (
                <Campo etiqueta="Cantidad de veces (con esta)">
                  <input type="number" min={2} max={52} value={cantidad} required onChange={(e) => setCantidad(Number(e.target.value))} />
                </Campo>
              ) : (
                <Campo etiqueta="Hasta el día *">
                  <input type="date" value={hastaDia} min={dia} required onChange={(e) => setHastaDia(e.target.value)} />
                </Campo>
              )}
            </>
          )}
        </div>
      )}
      {actividad && siguientes > 0 && <AplicarA valor={aplicar} alCambiar={setAplicar} siguientes={siguientes} />}
      {actividad && (
        <Campo etiqueta="Motivo del cambio (opcional, queda en el historial)">
          <input value={motivo} maxLength={1000} onChange={(e) => setMotivo(e.target.value)} />
        </Campo>
      )}

      <fieldset className="agenda-quienes">
        <legend>Quiénes participan</legend>
        {(gente.datos ?? []).map((u) => (
          <label key={u.id} className="campo campo-casilla">
            <input type="checkbox" checked={quienes.includes(u.id)} onChange={() => alternar(u.id)} /> {u.nombre}
          </label>
        ))}
      </fieldset>

      {personaId ? (
        <p>
          <strong>Legajo:</strong> {persona ? `${persona.apellidos}, ${persona.nombres}` : vinculoActual?.nombre}{" "}
          <button
            type="button"
            className="boton boton-chico"
            onClick={() => {
              setPersona(null);
              setVinculoActual(null);
              setCasoId("");
            }}
          >
            Quitar
          </button>
        </p>
      ) : (
        <details>
          <summary>Ligar a un legajo y a un caso (opcional)</summary>
          <BuscarLegajo alElegir={setPersona} />
        </details>
      )}
      {personaId && (casos.datos?.length ?? 0) > 0 && (
        <Campo etiqueta="Caso">
          <select value={casoId} onChange={(e) => setCasoId(e.target.value)}>
            <option value="">Sin caso</option>
            {casos.datos!.map((c) => (
              <option key={c.id} value={c.id}>
                {c.numero} · {c.estado}
              </option>
            ))}
          </select>
        </Campo>
      )}
      <Campo etiqueta="Detalle">
        <textarea rows={3} value={descripcion} maxLength={5000} onChange={(e) => setDescripcion(e.target.value)} />
      </Campo>
      <Aviso error={error} />
      <button className="boton boton-primario" disabled={enviando || quienes.length === 0}>
        {actividad ? "Guardar cambios" : "Agendar"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- salida desde el mapa

/** UUID para unir las paradas de una salida (``crypto.randomUUID`` solo existe en páginas seguras: https o localhost). */
function nuevoId(): string {
  const c: Crypto = crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  const b = c.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** Agenda una salida con los casos elegidos en el mapa: una actividad por caso, para registrar el resultado de cada visita. */
export function ProgramarSalida({
  casos,
  alCerrar,
  alAgendar,
}: {
  casos: { caso_id: string; persona_id: string }[];
  alCerrar: () => void;
  alAgendar: () => void;
}) {
  const { yo } = useSesion();
  const gente = useDatos(() => api.get<{ id: string; nombre: string; area: string | null }[]>("/agenda/participantes"), []);
  const [dia, setDia] = useState(claveDia(new Date(Date.now() + 86_400_000)));
  const [desde, setDesde] = useState("09:00");
  const [quienes, setQuienes] = useState<string[]>([yo.id]);
  const { enviando, error, ejecutar } = useEnvio();
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(async () => {
      const salidaId = nuevoId(); // une las paradas: así se puede volver a ver el recorrido
      for (let i = 0; i < casos.length; i++) {
        await api.post("/agenda", {
          tipo: "salida",
          titulo: "Salida a domicilio",
          descripcion: `Parada ${i + 1} de ${casos.length} del recorrido.`,
          inicio: new Date(`${dia}T${desde}:00`).toISOString(),
          todo_el_dia: false,
          persona_id: casos[i].persona_id,
          caso_id: casos[i].caso_id,
          participantes: quienes,
          salida_id: salidaId,
          salida_orden: i + 1,
        });
      }
      return true;
    });
    if (ok) alAgendar();
  };
  return (
    <Modal titulo={`Agendar salida (${casos.length} ${casos.length === 1 ? "visita" : "visitas"})`} alCerrar={alCerrar}>
      <form className="formulario" onSubmit={guardar}>
        <p className="tenue">Se agenda una actividad por cada caso del recorrido, para registrar después cómo fue cada visita.</p>
        <div className="grilla">
          <Campo etiqueta="Día *">
            <input type="date" value={dia} required onChange={(e) => setDia(e.target.value)} />
          </Campo>
          <Campo etiqueta="Hora de salida *">
            <input type="time" value={desde} required onChange={(e) => setDesde(e.target.value)} />
          </Campo>
        </div>
        <fieldset className="agenda-quienes">
          <legend>Quiénes salen</legend>
          {(gente.datos ?? []).map((u) => (
            <label key={u.id} className="campo campo-casilla">
              <input type="checkbox" checked={quienes.includes(u.id)} onChange={() => setQuienes((q) => (q.includes(u.id) ? q.filter((x) => x !== u.id) : [...q, u.id]))} /> {u.nombre}
            </label>
          ))}
        </fieldset>
        <Aviso error={error} />
        <button className="boton boton-primario" disabled={enviando || quienes.length === 0}>
          Agendar
        </button>
      </form>
    </Modal>
  );
}

// División Participación y Sensibilización Ciudadana: planificación semanal, campañas, tipos de evento,
// asistentes, fotos y brief para Comunicación. Los eventos también se ven en la Agenda.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, subirConProgreso } from "../api";
import { Aviso, Campo, Cargando, Modal, Vacio, fecha, useDatos, useEnvio, useSesion } from "../comun";
import { AplicarA, FormResultado, HistorialCambios, ICONO, ESTADO, type Actividad } from "./agenda";

// ---------------------------------------------------------------- tipos

export interface EventoResumen {
  id: string;
  titulo: string;
  tipo: string;
  fecha: string;
  hora: string | null;
  fin: string | null;
  lugar: string | null;
  instituciones: string[];
  resumen: string | null;
  campania: string | null;
  organiza_otra: string | null;
  sugerir_directora: boolean;
  estado: "programado" | "realizado" | "no_realizado" | "cancelado";
  asistentes: number | null;
}

export interface SemanaDatos {
  lunes: string;
  domingo: string;
  dias: { fecha: string; texto: string; eventos: EventoResumen[] }[];
  total: number;
  con_presencia_sugerida: number;
  texto: string;
}

interface DatosEvento {
  tipo: { id: number; nombre: string };
  nombre_flyer: string | null;
  instituciones: string[];
  resumen: string | null;
  campania: { id: string; nombre: string } | null;
  organiza_otra: string | null;
  sugerir_directora: boolean;
  asistentes: number | null;
  fotos: { id: string; orden: number; nombre: string }[];
  puedo_cargar_cierre: boolean;
  puedo_descargar_brief: boolean;
}

type EventoCompleto = Actividad & { participacion: DatosEvento };

interface Tipo {
  id: number;
  nombre: string;
  activo: boolean;
  eventos: number;
}

export interface Campania {
  id: string;
  nombre: string;
  descripcion: string | null;
  desde: string | null;
  hasta: string | null;
  estado: "activa" | "cerrada";
  eventos: number;
  realizados: number;
  asistentes: number;
  materiales: number;
  lista_materiales?: { id: string; nombre: string; mime: string; tamano: number; subido_en: string }[];
  lista_eventos?: EventoResumen[];
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const lunesDe = (d: Date) => {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
};
const kb = (n: number) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// ---------------------------------------------------------------- página

type Pestana = "semana" | "campanias" | "tipos";

export function PaginaParticipacion() {
  const { puede } = useSesion();
  const [pestana, setPestana] = useState<Pestana>("semana");
  if (!puede("participacion", "consultar")) return <Aviso error="No tiene acceso a Participación y Sensibilización." />;
  return (
    <div className="participacion">
      <div className="titulo-pagina">
        <h1>Participación y Sensibilización</h1>
      </div>
      <div className="segmentado" role="tablist">
        {(
          [
            ["semana", "Planificación semanal"],
            ["campanias", "Campañas"],
            ["tipos", "Tipos de evento"],
          ] as [Pestana, string][]
        ).map(([k, t]) => (
          <button key={k} role="tab" aria-selected={pestana === k} className={pestana === k ? "activo" : ""} onClick={() => setPestana(k)}>
            {t}
          </button>
        ))}
      </div>
      {pestana === "semana" && <Semana />}
      {pestana === "campanias" && <Campanias />}
      {pestana === "tipos" && <Tipos />}
    </div>
  );
}

// ---------------------------------------------------------------- semana

function Insignias({ e }: { e: EventoResumen }) {
  return (
    <>
      {e.sugerir_directora && (
        <span className="part-insignia part-presencia" title="Se sugiere la presencia de la Directora">
          ★ Presencia sugerida
        </span>
      )}
      {e.organiza_otra && (
        <span className="part-insignia part-otra" title="A cargo de otra organización">
          {e.organiza_otra}
        </span>
      )}
      {e.campania && <span className="part-insignia part-insig-campania">{e.campania}</span>}
    </>
  );
}

function Semana() {
  const { puede } = useSesion();
  const [lunes, setLunes] = useState(() => iso(lunesDe(new Date())));
  const [abierto, setAbierto] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const semana = useDatos(() => api.get<SemanaDatos>("/participacion/semana", { lunes }), [lunes]);
  const pend = useDatos(() => api.get<{ sin_asistentes: EventoResumen[]; sin_fotos: number }>("/participacion/pendientes"), []);
  const mover = (dias: number) => {
    const d = new Date(lunes + "T12:00:00");
    d.setDate(d.getDate() + dias);
    setLunes(iso(d));
  };
  const refrescar = () => {
    semana.recargar();
    pend.recargar();
  };
  return (
    <>
      <div className="agenda-barra">
        <div className="fila-botones">
          <button className="boton boton-chico" onClick={() => mover(-7)} aria-label="Semana anterior">
            ◀
          </button>
          <strong>
            {semana.datos ? `Del ${fecha(semana.datos.lunes)} al ${fecha(semana.datos.domingo)}` : "…"}
          </strong>
          <button className="boton boton-chico" onClick={() => mover(7)} aria-label="Semana siguiente">
            ▶
          </button>
          <button className="boton boton-chico" onClick={() => setLunes(iso(lunesDe(new Date())))}>
            Esta semana
          </button>
        </div>
        {puede("participacion", "crear") && (
          <button className="boton boton-primario" onClick={() => setNuevo(true)}>
            ＋ Nuevo evento
          </button>
        )}
      </div>
      <Aviso error={semana.error} />
      {(pend.datos?.sin_asistentes.length ?? 0) > 0 && (
        <section className="agenda-pendientes" aria-label="Faltan asistentes">
          <strong>Falta cargar los asistentes ({pend.datos!.sin_asistentes.length})</strong>
          <ul>
            {pend.datos!.sin_asistentes.slice(0, 6).map((e) => (
              <li key={e.id}>
                <button className="boton-enlace" onClick={() => setAbierto(e.id)}>
                  {fecha(e.fecha)} · {e.titulo}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {!semana.datos && !semana.error && <Cargando />}
      {semana.datos && (
        <>
          <div className="part-semana">
            {semana.datos.dias.map((d) => (
              <section key={d.fecha} className={`part-dia ${d.fecha === iso(new Date()) ? "hoy" : ""}`}>
                <h3>{d.texto}</h3>
                {d.eventos.length === 0 && <p className="tenue">—</p>}
                {d.eventos.map((e) => (
                  <button key={e.id} className={`part-evento estado-${e.estado}`} onClick={() => setAbierto(e.id)}>
                    <span className="part-hora">
                      {ICONO[e.estado]} {e.hora ? `${e.hora}${e.fin ? `–${e.fin}` : ""}` : "Todo el día"}
                    </span>
                    <strong>{e.titulo}</strong>
                    {e.titulo !== e.tipo && <small className="tenue">{e.tipo}</small>}
                    {e.lugar && <small>📍 {e.lugar}</small>}
                    <span className="part-insignias">
                      <Insignias e={e} />
                    </span>
                  </button>
                ))}
              </section>
            ))}
          </div>
          <ResumenTexto semana={semana.datos} />
        </>
      )}
      {abierto && (
        <DetalleEvento
          id={abierto}
          alCerrar={() => setAbierto(null)}
          alCambiar={() => {
            setAbierto(null);
            refrescar();
          }}
        />
      )}
      {nuevo && (
        <Modal titulo="Nuevo evento" alCerrar={() => setNuevo(false)} ancho>
          <FormEvento
            diaInicial={semana.datos?.lunes ?? lunes}
            alGuardar={() => {
              setNuevo(false);
              refrescar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function ResumenTexto({ semana }: { semana: SemanaDatos }) {
  const [copiado, setCopiado] = useState(false);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(semana.texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* el navegador no permite copiar: el texto se puede seleccionar a mano */
    }
  };
  return (
    <section className="part-resumen">
      <h3>Resumen de la semana</h3>
      <p className="part-texto">{semana.texto}</p>
      <button className="boton boton-chico" onClick={copiar}>
        {copiado ? "Copiado" : "Copiar el resumen"}
      </button>
    </section>
  );
}

/** Resumen semanal para el tablero de la Dirección y de la División: navega de semana en semana. */
export function ResumenSemanal({ inicial }: { inicial: SemanaDatos }) {
  const [lunes, setLunes] = useState(inicial.lunes);
  const [datos, setDatos] = useState<SemanaDatos>(inicial);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (lunes === inicial.lunes) return setDatos(inicial);
    let vivo = true;
    api
      .get<SemanaDatos>("/participacion/semana", { lunes })
      .then((d) => vivo && setDatos(d))
      .catch((e) => vivo && setError(e));
    return () => {
      vivo = false;
    };
  }, [lunes, inicial]);
  const mover = (dias: number) => {
    const d = new Date(lunes + "T12:00:00");
    d.setDate(d.getDate() + dias);
    setLunes(iso(d));
  };
  return (
    <div className="part-tablero">
      <div className="fila-botones">
        <button className="boton boton-chico" onClick={() => mover(-7)} aria-label="Semana anterior">
          ◀
        </button>
        <strong>
          {fecha(datos.lunes)} al {fecha(datos.domingo)}
        </strong>
        <button className="boton boton-chico" onClick={() => mover(7)} aria-label="Semana siguiente">
          ▶
        </button>
      </div>
      <Aviso error={error} />
      <p className="part-texto">{datos.texto}</p>
    </div>
  );
}

// ---------------------------------------------------------------- detalle de un evento

export function DetalleEvento({ id, alCerrar, alCambiar }: { id: string; alCerrar: () => void; alCambiar: () => void }) {
  const { puede } = useSesion();
  const datos = useDatos(() => api.get<EventoCompleto>(`/participacion/eventos/${id}`), [id]);
  const [modo, setModo] = useState<"ver" | "editar" | "resultado">("ver");
  const e = datos.datos;
  if (datos.error) {
    return (
      <Modal titulo="Evento" alCerrar={alCerrar}>
        <Aviso error={datos.error} />
      </Modal>
    );
  }
  if (!e) {
    return (
      <Modal titulo="Evento" alCerrar={alCerrar}>
        <Cargando />
      </Modal>
    );
  }
  const x = e.participacion;
  const siguientes = e.en_la_serie?.siguientes ?? 0;
  const ini = new Date(e.inicio);
  return (
    <Modal titulo={e.titulo} alCerrar={alCerrar} ancho>
      {modo === "editar" ? (
        <FormEvento evento={e} siguientes={siguientes} alGuardar={alCambiar} />
      ) : (
        <>
          <dl className="agenda-detalle">
            <dt>Cuándo</dt>
            <dd>
              {ini.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })} ·{" "}
              {e.todo_el_dia ? "Todo el día" : ini.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}
              {e.fin && !e.todo_el_dia && ` a ${new Date(e.fin).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}`}
            </dd>
            <dt>Tipo de evento</dt>
            <dd>{x.tipo.nombre}</dd>
            {e.repeticion_texto && (
              <>
                <dt>Se repite</dt>
                <dd>
                  {e.repeticion_texto}
                  {e.en_la_serie && <small className="tenue"> · {e.en_la_serie.total} eventos en la serie</small>}
                </dd>
              </>
            )}
            {e.lugar && (
              <>
                <dt>Lugar</dt>
                <dd>{e.lugar}</dd>
              </>
            )}
            <dt>Organiza</dt>
            <dd>{x.organiza_otra ? `${x.organiza_otra} (otra organización)` : "La propia Dirección"}</dd>
            {x.campania && (
              <>
                <dt>Campaña</dt>
                <dd>{x.campania.nombre}</dd>
              </>
            )}
            {x.instituciones.length > 0 && (
              <>
                <dt>Instituciones</dt>
                <dd>{x.instituciones.join(", ")}</dd>
              </>
            )}
            {x.sugerir_directora && (
              <>
                <dt>Directora</dt>
                <dd>★ Se sugiere su presencia</dd>
              </>
            )}
            {x.resumen && (
              <>
                <dt>Resumen</dt>
                <dd className="part-texto">{x.resumen}</dd>
              </>
            )}
            <dt>Participan</dt>
            <dd>{e.participantes.map((p) => p.nombre).join(", ") || "—"}</dd>
            <dt>Estado</dt>
            <dd>
              {ICONO[e.estado]} {ESTADO[e.estado]}
              {e.resuelto_por && <small className="tenue"> · {e.resuelto_por}</small>}
            </dd>
            {e.resultado && (
              <>
                <dt>Cómo se desarrolló</dt>
                <dd className="part-texto">{e.resultado}</dd>
              </>
            )}
            {e.estado === "realizado" && (
              <>
                <dt>Asistentes</dt>
                <dd>{x.asistentes ?? "Falta cargar"}</dd>
              </>
            )}
          </dl>
          {e.estado === "programado" && e.puedo_modificar && modo === "ver" && (
            <div className="fila-botones fila-izquierda">
              <button className="boton boton-primario" onClick={() => setModo("resultado")}>
                Registrar resultado
              </button>
              {puede("participacion", "modificar") && (
                <button className="boton" onClick={() => setModo("editar")}>
                  Editar o reprogramar
                </button>
              )}
            </div>
          )}
          {modo === "resultado" && (
            <FormResultado actividadId={e.id} siguientes={siguientes} etiqueta="Cómo se desarrolló" alGuardar={() => {
                datos.recargar();
                setModo("ver");
              }} alVolver={() => setModo("ver")} />
          )}
          {e.estado === "realizado" && <Cierre evento={e} alCambiar={() => datos.recargar()} />}
          {modo === "ver" && <HistorialCambios historial={e.historial} />}
          {modo === "ver" && (
            <div className="fila-botones fila-izquierda">
              <button className="boton" onClick={alCambiar}>
                Cerrar
              </button>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

/** Después del evento: cantidad de asistentes, hasta dos fotos y el brief para Comunicación. */
function Cierre({ evento: e, alCambiar }: { evento: EventoCompleto; alCambiar: () => void }) {
  const x = e.participacion;
  const [asistentes, setAsistentes] = useState(x.asistentes?.toString() ?? "");
  const { enviando, error, ejecutar } = useEnvio();
  const [subiendo, setSubiendo] = useState(false);
  const [errorFoto, setErrorFoto] = useState<unknown>(null);
  const entrada = useRef<HTMLInputElement>(null);
  const guardar = async (ev: FormEvent) => {
    ev.preventDefault();
    const r = await ejecutar(() => api.patch(`/participacion/eventos/${e.id}/asistentes`, { asistentes: Number(asistentes) }));
    if (r) alCambiar();
  };
  const subir = async (archivo: File | undefined) => {
    if (!archivo) return;
    setSubiendo(true);
    setErrorFoto(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      await subirConProgreso(`/participacion/eventos/${e.id}/fotos`, fd, () => {});
      alCambiar();
    } catch (err) {
      setErrorFoto(err);
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  };
  const quitar = async (fid: string) => {
    try {
      await api.delete(`/participacion/eventos/${e.id}/fotos/${fid}`);
      alCambiar();
    } catch (err) {
      setErrorFoto(err);
    }
  };
  const editable = x.puedo_cargar_cierre;
  return (
    <section className="part-cierre">
      <h3>Después del evento</h3>
      {editable ? (
        <form className="formulario formulario-linea" onSubmit={guardar}>
          <Campo etiqueta="Cantidad de asistentes">
            <input type="number" min={0} max={1000000} value={asistentes} required onChange={(ev) => setAsistentes(ev.target.value)} />
          </Campo>
          <button className="boton boton-primario" disabled={enviando || asistentes === ""}>
            Guardar
          </button>
        </form>
      ) : (
        <p>Asistentes: {x.asistentes ?? "—"}</p>
      )}
      <Aviso error={error} />
      <div className="part-fotos">
        {x.fotos.map((f) => (
          <figure key={f.id}>
            <a href={`/api/participacion/eventos/${e.id}/fotos/${f.id}`} target="_blank" rel="noreferrer">
              <img src={`/api/participacion/eventos/${e.id}/fotos/${f.id}`} alt={`Foto ${f.orden} del evento`} loading="lazy" />
            </a>
            {editable && (
              <button className="boton boton-chico" onClick={() => quitar(f.id)}>
                Quitar
              </button>
            )}
          </figure>
        ))}
        {editable && x.fotos.length < 2 && (
          <label className="part-subir">
            <input ref={entrada} type="file" accept="image/jpeg,image/png,image/webp" disabled={subiendo} onChange={(ev) => subir(ev.target.files?.[0])} />
            <span>{subiendo ? "Subiendo…" : `＋ Agregar foto (${x.fotos.length} de 2)`}</span>
          </label>
        )}
      </div>
      <Aviso error={errorFoto} />
      {x.puedo_descargar_brief && (
        <a className="boton" href={`/api/participacion/eventos/${e.id}/brief.docx`}>
          Exportar brief para Comunicación (Word)
        </a>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- alta y edición de un evento

function Instituciones({ valor, alCambiar }: { valor: string[]; alCambiar: (v: string[]) => void }) {
  const [texto, setTexto] = useState("");
  const agregar = () => {
    const t = texto.trim();
    if (t && !valor.some((v) => v.toLowerCase() === t.toLowerCase())) alCambiar([...valor, t]);
    setTexto("");
  };
  return (
    <div className="part-instituciones">
      <div className="part-chips">
        {valor.map((v) => (
          <span key={v} className="part-chip">
            {v}
            <button type="button" aria-label={`Quitar ${v}`} onClick={() => alCambiar(valor.filter((x) => x !== v))}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="fila-botones">
        <input
          value={texto}
          maxLength={200}
          placeholder="Escriba una institución y toque Agregar"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              agregar();
            }
          }}
        />
        <button type="button" className="boton boton-chico" onClick={agregar} disabled={!texto.trim()}>
          Agregar
        </button>
      </div>
    </div>
  );
}

const FRECUENCIAS: [string, string][] = [
  ["", "No se repite"],
  ["diaria", "Todos los días hábiles"],
  ["semanal", "Todas las semanas"],
  ["quincenal", "Cada 15 días"],
  ["mensual", "Todos los meses"],
];

export function FormEvento({
  evento,
  diaInicial,
  campaniaId,
  siguientes = 0,
  alGuardar,
}: {
  evento?: EventoCompleto;
  diaInicial?: string;
  campaniaId?: string;
  siguientes?: number;
  alGuardar: () => void;
}) {
  const { yo, puede } = useSesion();
  const x = evento?.participacion;
  const ini = evento ? new Date(evento.inicio) : null;
  const fin = evento?.fin ? new Date(evento.fin) : null;
  const dos = (n: number) => String(n).padStart(2, "0");
  const tipos = useDatos(() => api.get<Tipo[]>("/participacion/tipos"), []);
  const campanias = useDatos(() => api.get<Campania[]>("/participacion/campanias", { estado: "activa" }), []);
  const gente = useDatos(() => api.get<{ id: string; nombre: string }[]>("/agenda/participantes"), []);
  const [tipoId, setTipoId] = useState<string>(x ? String(x.tipo.id) : "");
  const [tipoNuevo, setTipoNuevo] = useState("");
  const [flyer, setFlyer] = useState(x?.nombre_flyer ?? "");
  const [dia, setDia] = useState(ini ? iso(ini) : diaInicial ?? iso(new Date()));
  const [desde, setDesde] = useState(ini && !evento?.todo_el_dia ? `${dos(ini.getHours())}:${dos(ini.getMinutes())}` : "10:00");
  const [hasta, setHasta] = useState(fin && !evento?.todo_el_dia ? `${dos(fin.getHours())}:${dos(fin.getMinutes())}` : "");
  const [todo, setTodo] = useState(evento?.todo_el_dia ?? false);
  const [lugar, setLugar] = useState(evento?.lugar ?? "");
  const [instituciones, setInstituciones] = useState<string[]>(x?.instituciones ?? []);
  const [resumen, setResumen] = useState(x?.resumen ?? "");
  const [campania, setCampania] = useState(x?.campania?.id ?? campaniaId ?? "");
  const [otra, setOtra] = useState(Boolean(x?.organiza_otra));
  const [organiza, setOrganiza] = useState(x?.organiza_otra ?? "");
  const [sugerir, setSugerir] = useState(x?.sugerir_directora ?? false);
  const [quienes, setQuienes] = useState<string[]>(evento ? evento.participantes.map((p) => p.id) : [yo.id]);
  const [frecuencia, setFrecuencia] = useState("");
  const [terminaEn, setTerminaEn] = useState<"cantidad" | "hasta">("cantidad");
  const [cantidad, setCantidad] = useState(4);
  const [hastaDia, setHastaDia] = useState("");
  const [aplicar, setAplicar] = useState<"esta" | "siguientes">("esta");
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const activos = (tipos.datos ?? []).filter((t) => t.activo || String(t.id) === tipoId);

  const guardar = async (ev: FormEvent) => {
    ev.preventDefault();
    const r = await ejecutar(async () => {
      let tid = tipoId;
      if (!tid && tipoNuevo.trim()) {
        const t = await api.post<Tipo>("/participacion/tipos", { nombre: tipoNuevo.trim() });
        tid = String(t.id);
      }
      if (!tid) throw new Error("Elija el tipo de evento.");
      const inicio = new Date(`${dia}T${todo ? "00:00" : desde}:00`);
      const finDate = !todo && hasta ? new Date(`${dia}T${hasta}:00`) : null;
      const cuerpo = {
        tipo_id: Number(tid),
        nombre_flyer: flyer.trim() || null,
        inicio: inicio.toISOString(),
        fin: finDate ? finDate.toISOString() : null,
        todo_el_dia: todo,
        lugar: lugar.trim() || null,
        instituciones,
        resumen: resumen.trim() || null,
        campania_id: campania || null,
        organiza_otra: otra ? organiza.trim() || null : null,
        sugerir_directora: sugerir,
        participantes: quienes,
      };
      return evento
        ? api.patch(`/participacion/eventos/${evento.id}`, { ...cuerpo, aplicar_a: aplicar, motivo: motivo || null })
        : api.post("/participacion/eventos", {
            ...cuerpo,
            ...(frecuencia ? { repetir: { frecuencia, ...(terminaEn === "cantidad" ? { cantidad } : { hasta: hastaDia }) } } : {}),
          });
    });
    if (r) alGuardar();
  };
  const alternar = (id: string) => setQuienes((q) => (q.includes(id) ? q.filter((v) => v !== id) : [...q, id]));

  return (
    <form className="formulario" onSubmit={guardar}>
      <div className="grilla">
        <Campo etiqueta="Tipo de evento *" ayuda="Si no hay flyer, el evento se registra con el nombre del tipo.">
          <select value={tipoId} onChange={(e) => setTipoId(e.target.value)} required={!tipoNuevo.trim()}>
            <option value="">{activos.length ? "Elegir…" : "Todavía no hay tipos: cree uno abajo"}</option>
            {activos.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </select>
        </Campo>
        {puede("participacion", "administrar") && !tipoId && (
          <Campo etiqueta="…o crear un tipo nuevo">
            <input value={tipoNuevo} maxLength={120} onChange={(e) => setTipoNuevo(e.target.value)} placeholder="Ej.: Charla, Taller, Feria" />
          </Campo>
        )}
        <Campo etiqueta="Nombre del flyer (si corresponde)">
          <input value={flyer} maxLength={200} onChange={(e) => setFlyer(e.target.value)} />
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

      <Campo etiqueta="Instituciones con las que se coordina o a las que se dirige">
        <Instituciones valor={instituciones} alCambiar={setInstituciones} />
      </Campo>
      <Campo etiqueta="Breve resumen" ayuda="Es lo que se lee en el resumen semanal de la Dirección.">
        <textarea rows={3} value={resumen} maxLength={3000} onChange={(e) => setResumen(e.target.value)} />
      </Campo>

      <div className="grilla">
        <Campo etiqueta="Campaña">
          <select value={campania} onChange={(e) => setCampania(e.target.value)}>
            <option value="">Ninguna</option>
            {(campanias.datos ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
            {x?.campania && !(campanias.datos ?? []).some((c) => c.id === x.campania!.id) && <option value={x.campania.id}>{x.campania.nombre}</option>}
          </select>
        </Campo>
        <fieldset className="agenda-quienes">
          <legend>Quién organiza</legend>
          <label className="campo campo-casilla">
            <input type="radio" name="organiza" checked={!otra} onChange={() => setOtra(false)} /> La propia Dirección
          </label>
          <label className="campo campo-casilla">
            <input type="radio" name="organiza" checked={otra} onChange={() => setOtra(true)} /> Otra organización
          </label>
          {otra && <input value={organiza} maxLength={200} required placeholder="Nombre de la organización a cargo" onChange={(e) => setOrganiza(e.target.value)} />}
        </fieldset>
      </div>
      <label className="campo campo-casilla">
        <input type="checkbox" checked={sugerir} onChange={(e) => setSugerir(e.target.checked)} /> Se sugiere la presencia de la Directora
      </label>

      <fieldset className="agenda-quienes">
        <legend>Quiénes participan</legend>
        {(gente.datos ?? []).map((u) => (
          <label key={u.id} className="campo campo-casilla">
            <input type="checkbox" checked={quienes.includes(u.id)} onChange={() => alternar(u.id)} /> {u.nombre}
          </label>
        ))}
      </fieldset>

      {!evento && (
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
      {evento && siguientes > 0 && <AplicarA valor={aplicar} alCambiar={setAplicar} siguientes={siguientes} />}
      {evento && (
        <Campo etiqueta="Motivo del cambio (opcional, queda en el historial)">
          <input value={motivo} maxLength={1000} onChange={(e) => setMotivo(e.target.value)} />
        </Campo>
      )}
      <Aviso error={error} />
      <button className="boton boton-primario" disabled={enviando || quienes.length === 0}>
        {evento ? "Guardar cambios" : "Agendar evento"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- campañas

function Campanias() {
  const { puede } = useSesion();
  const [estado, setEstado] = useState<"activa" | "cerrada">("activa");
  const [abierta, setAbierta] = useState<string | null>(null);
  const [nueva, setNueva] = useState(false);
  const lista = useDatos(() => api.get<Campania[]>("/participacion/campanias", { estado }), [estado]);
  return (
    <>
      <div className="agenda-barra">
        <div className="segmentado" role="group" aria-label="Estado">
          <button className={estado === "activa" ? "activo" : ""} aria-pressed={estado === "activa"} onClick={() => setEstado("activa")}>
            Activas
          </button>
          <button className={estado === "cerrada" ? "activo" : ""} aria-pressed={estado === "cerrada"} onClick={() => setEstado("cerrada")}>
            Cerradas
          </button>
        </div>
        {puede("participacion", "crear") && (
          <button className="boton boton-primario" onClick={() => setNueva(true)}>
            ＋ Nueva campaña
          </button>
        )}
      </div>
      <Aviso error={lista.error} />
      {!lista.datos && !lista.error && <Cargando />}
      {lista.datos?.length === 0 && <Vacio>No hay campañas {estado === "activa" ? "activas" : "cerradas"}.</Vacio>}
      <div className="part-campanias">
        {lista.datos?.map((c) => (
          <button key={c.id} className="part-campania" onClick={() => setAbierta(c.id)}>
            <strong>{c.nombre}</strong>
            {(c.desde || c.hasta) && (
              <small className="tenue">
                {c.desde ? fecha(c.desde) : "…"} al {c.hasta ? fecha(c.hasta) : "…"}
              </small>
            )}
            <span>
              {c.eventos} {c.eventos === 1 ? "evento" : "eventos"} · {c.realizados} {c.realizados === 1 ? "realizado" : "realizados"} · {c.asistentes} asistentes
            </span>
            <small className="tenue">{c.materiales} {c.materiales === 1 ? "archivo de material" : "archivos de material"}</small>
          </button>
        ))}
      </div>
      {nueva && (
        <Modal titulo="Nueva campaña" alCerrar={() => setNueva(false)}>
          <FormCampania
            alGuardar={(c) => {
              setNueva(false);
              lista.recargar();
              setAbierta(c.id);
            }}
          />
        </Modal>
      )}
      {abierta && (
        <DetalleCampania
          id={abierta}
          alCerrar={() => {
            setAbierta(null);
            lista.recargar();
          }}
        />
      )}
    </>
  );
}

function FormCampania({ campania, alGuardar }: { campania?: Campania; alGuardar: (c: Campania) => void }) {
  const [nombre, setNombre] = useState(campania?.nombre ?? "");
  const [descripcion, setDescripcion] = useState(campania?.descripcion ?? "");
  const [desde, setDesde] = useState(campania?.desde ?? "");
  const [hasta, setHasta] = useState(campania?.hasta ?? "");
  const { enviando, error, ejecutar } = useEnvio();
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = { nombre, descripcion: descripcion || null, desde: desde || null, hasta: hasta || null };
    const r = await ejecutar(() => (campania ? api.patch<Campania>(`/participacion/campanias/${campania.id}`, cuerpo) : api.post<Campania>("/participacion/campanias", cuerpo)));
    if (r) alGuardar(r);
  };
  return (
    <form className="formulario" onSubmit={guardar}>
      <Campo etiqueta="Nombre de la campaña *">
        <input value={nombre} maxLength={200} required onChange={(e) => setNombre(e.target.value)} />
      </Campo>
      <Campo etiqueta="Descripción">
        <textarea rows={3} value={descripcion} maxLength={5000} onChange={(e) => setDescripcion(e.target.value)} />
      </Campo>
      <div className="grilla">
        <Campo etiqueta="Desde">
          <input type="date" value={desde} max={hasta || undefined} onChange={(e) => setDesde(e.target.value)} />
        </Campo>
        <Campo etiqueta="Hasta">
          <input type="date" value={hasta} min={desde || undefined} onChange={(e) => setHasta(e.target.value)} />
        </Campo>
      </div>
      <Aviso error={error} />
      <button className="boton boton-primario" disabled={enviando}>
        {campania ? "Guardar cambios" : "Crear campaña"}
      </button>
    </form>
  );
}

function DetalleCampania({ id, alCerrar }: { id: string; alCerrar: () => void }) {
  const { puede } = useSesion();
  const datos = useDatos(() => api.get<Campania>(`/participacion/campanias/${id}`), [id]);
  const [modo, setModo] = useState<"ver" | "editar">("ver");
  const [evento, setEvento] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const entrada = useRef<HTMLInputElement>(null);
  const c = datos.datos;
  const subir = async (archivo: File | undefined) => {
    if (!archivo) return;
    setSubiendo(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      await subirConProgreso(`/participacion/campanias/${id}/materiales`, fd, () => {});
      datos.recargar();
    } catch (e) {
      setError(e);
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  };
  const quitar = async (mid: string) => {
    try {
      await api.delete(`/participacion/campanias/${id}/materiales/${mid}`);
      datos.recargar();
    } catch (e) {
      setError(e);
    }
  };
  const cambiarEstado = async () => {
    try {
      await api.patch(`/participacion/campanias/${id}`, { estado: c?.estado === "activa" ? "cerrada" : "activa" });
      datos.recargar();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <Modal titulo={c ? `Campaña: ${c.nombre}` : "Campaña"} alCerrar={alCerrar} ancho>
      <Aviso error={datos.error ?? error} />
      {!c && !datos.error && <Cargando />}
      {c && modo === "editar" && (
        <FormCampania
          campania={c}
          alGuardar={() => {
            setModo("ver");
            datos.recargar();
          }}
        />
      )}
      {c && modo === "ver" && (
        <>
          <dl className="agenda-detalle">
            <dt>Estado</dt>
            <dd>{c.estado === "activa" ? "Activa" : "Cerrada"}</dd>
            {(c.desde || c.hasta) && (
              <>
                <dt>Período</dt>
                <dd>
                  {c.desde ? fecha(c.desde) : "…"} al {c.hasta ? fecha(c.hasta) : "…"}
                </dd>
              </>
            )}
            {c.descripcion && (
              <>
                <dt>Descripción</dt>
                <dd className="part-texto">{c.descripcion}</dd>
              </>
            )}
            <dt>Eventos</dt>
            <dd>
              {c.eventos} · realizados {c.realizados} · asistentes {c.asistentes}
            </dd>
          </dl>
          <div className="fila-botones fila-izquierda">
            {puede("participacion", "modificar") && (
              <>
                <button className="boton" onClick={() => setModo("editar")}>
                  Editar
                </button>
                <button className="boton" onClick={cambiarEstado}>
                  {c.estado === "activa" ? "Cerrar la campaña" : "Reabrir"}
                </button>
              </>
            )}
            {puede("participacion", "descargar") && (
              <a className="boton" href={`/api/participacion/campanias/${c.id}/brief.docx`}>
                Exportar brief de la campaña (Word)
              </a>
            )}
          </div>

          <h3>Material de la campaña</h3>
          {(c.lista_materiales?.length ?? 0) === 0 && <p className="tenue">Todavía no se subió material.</p>}
          <ul className="part-materiales">
            {c.lista_materiales?.map((m) => (
              <li key={m.id}>
                <a href={`/api/participacion/campanias/${c.id}/materiales/${m.id}`} target="_blank" rel="noreferrer">
                  {m.nombre}
                </a>{" "}
                <small className="tenue">· {kb(m.tamano)}</small>
                {puede("participacion", "modificar") && (
                  <button className="boton boton-chico" onClick={() => quitar(m.id)}>
                    Quitar
                  </button>
                )}
              </li>
            ))}
          </ul>
          {puede("participacion", "modificar") && (
            <label className="part-subir">
              <input ref={entrada} type="file" disabled={subiendo} onChange={(e) => subir(e.target.files?.[0])} />
              <span>{subiendo ? "Subiendo…" : "＋ Subir material (PDF, imagen, Word, PowerPoint, Excel o video MP4; hasta 25 MB)"}</span>
            </label>
          )}

          <h3>Eventos de la campaña</h3>
          {puede("participacion", "crear") && (
            <div className="fila-botones fila-izquierda">
              <button className="boton boton-primario" onClick={() => setNuevo(true)}>
                ＋ Nuevo evento de esta campaña
              </button>
            </div>
          )}
          {(c.lista_eventos?.length ?? 0) === 0 && <p className="tenue">Todavía no hay eventos en esta campaña.</p>}
          <ul className="agenda-lista">
            {c.lista_eventos?.map((e) => (
              <li key={e.id} className={`estado-${e.estado}`}>
                <button className="agenda-item" onClick={() => setEvento(e.id)}>
                  <span className="agenda-hora">{fecha(e.fecha)}</span>
                  <span>
                    <strong>{e.titulo}</strong> <small className="tenue">· {e.tipo}</small>
                    <br />
                    <small className="tenue">
                      {ICONO[e.estado]} {ESTADO[e.estado]}
                      {e.organiza_otra && ` · a cargo de ${e.organiza_otra}`}
                      {e.sugerir_directora && " · ★ presencia sugerida"}
                      {e.asistentes != null && ` · ${e.asistentes} asistentes`}
                    </small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {evento && (
        <DetalleEvento
          id={evento}
          alCerrar={() => setEvento(null)}
          alCambiar={() => {
            setEvento(null);
            datos.recargar();
          }}
        />
      )}
      {nuevo && c && (
        <Modal titulo="Nuevo evento" alCerrar={() => setNuevo(false)} ancho>
          <FormEvento
            campaniaId={c.id}
            alGuardar={() => {
              setNuevo(false);
              datos.recargar();
            }}
          />
        </Modal>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- tipos de evento

function Tipos() {
  const { puede } = useSesion();
  const lista = useDatos(() => api.get<Tipo[]>("/participacion/tipos"), []);
  const [nombre, setNombre] = useState("");
  const [editando, setEditando] = useState<{ id: number; nombre: string } | null>(null);
  const { enviando, error, ejecutar } = useEnvio();
  const administra = puede("participacion", "administrar");
  const crear = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post("/participacion/tipos", { nombre }));
    if (r) {
      setNombre("");
      lista.recargar();
    }
  };
  const cambiar = async (id: number, cuerpo: object) => {
    const r = await ejecutar(() => api.patch(`/participacion/tipos/${id}`, cuerpo));
    if (r) {
      setEditando(null);
      lista.recargar();
    }
  };
  return (
    <>
      <p className="tenue">Los tipos de evento los define el área (charla, taller, feria…). Si un evento no tiene flyer, se registra con el nombre de su tipo.</p>
      {administra && (
        <form className="formulario formulario-linea" onSubmit={crear}>
          <Campo etiqueta="Nuevo tipo de evento">
            <input value={nombre} maxLength={120} required minLength={2} onChange={(e) => setNombre(e.target.value)} />
          </Campo>
          <button className="boton boton-primario" disabled={enviando}>
            Agregar
          </button>
        </form>
      )}
      <Aviso error={error ?? lista.error} />
      {!lista.datos && !lista.error && <Cargando />}
      {lista.datos?.length === 0 && <Vacio>Todavía no hay tipos de evento.</Vacio>}
      <table className="tabla">
        <thead>
          <tr>
            <th>Tipo</th>
            <th>Eventos</th>
            <th>Estado</th>
            {administra && <th />}
          </tr>
        </thead>
        <tbody>
          {lista.datos?.map((t) => (
            <tr key={t.id} className={t.activo ? "" : "fila-baja"}>
              <td>
                {editando?.id === t.id ? (
                  <input value={editando.nombre} maxLength={120} onChange={(e) => setEditando({ id: t.id, nombre: e.target.value })} />
                ) : (
                  t.nombre
                )}
              </td>
              <td>{t.eventos}</td>
              <td>{t.activo ? "En uso" : "Dado de baja"}</td>
              {administra && (
                <td className="fila-botones">
                  {editando?.id === t.id ? (
                    <>
                      <button className="boton boton-chico boton-primario" onClick={() => cambiar(t.id, { nombre: editando.nombre })}>
                        Guardar
                      </button>
                      <button className="boton boton-chico" onClick={() => setEditando(null)}>
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="boton boton-chico" onClick={() => setEditando({ id: t.id, nombre: t.nombre })}>
                        Renombrar
                      </button>
                      <button className="boton boton-chico" onClick={() => cambiar(t.id, { activo: !t.activo })}>
                        {t.activo ? "Dar de baja" : "Reactivar"}
                      </button>
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

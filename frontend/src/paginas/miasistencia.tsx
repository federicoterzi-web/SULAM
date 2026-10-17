// «Mi asistencia»: cada persona pide licencias, comisiones y cambios de horario;
// su jefatura los aprueba acá mismo; Personal los registra. Sirve igual en celular.
import { useEffect, useState, type FormEvent } from "react";
import { api, subirConProgreso } from "../api";
import { Aviso, Campo, Cargando, Seccion, Vacio, fecha, useDatos, useEnvio } from "../comun";
import {
  ESTADOS_JORNADA,
  TarjetaSolicitud,
  useCatalogoPersonal,
  type Agente,
  type CatalogoPersonal,
  type Jornada,
  type Solicitud,
} from "./personal";

export function usePendientesPersonal() {
  const r = useDatos(() => api.get<{ para_aprobar: number; para_registrar: number; cantidad: number }>("/personal/pendientes"), []);
  useEffect(() => {
    const f = () => r.recargar();
    window.addEventListener("sulam:personal", f);
    return () => window.removeEventListener("sulam:personal", f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return r;
}

/** Estado de hoy por usuario («De licencia», «En comisión»…), sin motivos. */
export type EstadoHoy = Record<string, { estado: string; texto: string; hasta: string }>;
export function useHoy() {
  return useDatos(() => api.get<EstadoHoy>("/personal/hoy"), []);
}

export function EtiquetaHoy({ hoy, usuarioId }: { hoy: EstadoHoy | null | undefined; usuarioId: string | null | undefined }) {
  const e = usuarioId ? hoy?.[usuarioId] : undefined;
  if (!e) return null;
  return (
    <span className={`chip-hoy chip-hoy-${e.estado}`} title={`Hasta el ${fecha(e.hasta)}`}>
      {e.texto}
    </span>
  );
}

function hoyIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function PaginaMiAsistencia({ movil }: { movil?: boolean }) {
  const cat = useCatalogoPersonal();
  const mio = useDatos(() => api.get<{ agente: Agente | null; solicitudes: Solicitud[] }>("/personal/mio"), []);
  const [nuevo, setNuevo] = useState(false);
  if (cat.error || mio.error) return <Aviso error={cat.error ?? mio.error} />;
  if (!cat.datos || !mio.datos) return <Cargando />;
  const c = cat.datos;
  const yo = mio.datos.agente;
  return (
    <>
      <h1>Mi asistencia</h1>
      {c.puedo.aprobar && <ParaAprobar cat={c} movil={movil} />}
      {!yo ? (
        <Aviso tipo="info" error="Tu usuario todavía no está vinculado a una ficha de personal. Pedíselo a Personal para poder hacer pedidos." />
      ) : (
        <>
          <Seccion titulo="Mis pedidos">
            {nuevo ? (
              <FormSolicitud
                cat={c}
                alCancelar={() => setNuevo(false)}
                alGuardar={() => {
                  setNuevo(false);
                  mio.recargar();
                  window.dispatchEvent(new Event("sulam:personal"));
                }}
              />
            ) : (
              <div className="fila-botones fila-izquierda">
                <button className="boton boton-primario" onClick={() => setNuevo(true)}>
                  Nuevo pedido
                </button>
              </div>
            )}
            <p className="tenue">Pedís vos, aprueba tu jefatura y Personal lo registra. Vas a ver acá en qué paso está.</p>
            {mio.datos.solicitudes.length === 0 ? (
              <Vacio>No hiciste pedidos todavía.</Vacio>
            ) : (
              <ul className="lista-solicitudes">
                {mio.datos.solicitudes.map((s) => (
                  <TarjetaSolicitud key={s.id} s={s} cat={c} alCambiar={mio.recargar} movil={movil} />
                ))}
              </ul>
            )}
          </Seccion>
          <MisJornadas cat={c} agente={yo} />
        </>
      )}
    </>
  );
}

function ParaAprobar({ cat, movil }: { cat: CatalogoPersonal; movil?: boolean }) {
  const lista = useDatos(() => api.get<Solicitud[]>("/personal/solicitudes", { vista: "para_aprobar" }), []);
  if (!lista.datos || lista.datos.length === 0) return null;
  return (
    <Seccion titulo={`Para aprobar (${lista.datos.length})`}>
      <ul className="lista-solicitudes">
        {lista.datos.map((s) => (
          <TarjetaSolicitud key={s.id} s={s} cat={cat} alCambiar={lista.recargar} mostrarPersona movil={movil} />
        ))}
      </ul>
    </Seccion>
  );
}

function FormSolicitud({ cat, alGuardar, alCancelar }: { cat: CatalogoPersonal; alGuardar: () => void; alCancelar: () => void }) {
  const [d, setD] = useState({
    tipo: "licencia",
    clase: "",
    desde: hoyIso(),
    hasta: "",
    parcial: false,
    hora_desde: "",
    hora_hasta: "",
    nueva_entrada: "",
    nueva_salida: "",
    lugar: "",
    motivo: "",
  });
  const [archivo, setArchivo] = useState<File | null>(null);
  const envio = useEnvio();
  const set = (k: keyof typeof d, v: string | boolean) => setD((x) => ({ ...x, [k]: v }));
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    envio.ejecutar(async () => {
      const fd = new FormData();
      fd.append("tipo", d.tipo);
      fd.append("desde", d.desde);
      if (d.hasta) fd.append("hasta", d.hasta);
      if (d.tipo === "licencia") fd.append("clase", d.clase);
      if (d.tipo === "comision") fd.append("lugar", d.lugar);
      if (d.tipo === "cambio_horario") {
        fd.append("nueva_entrada", d.nueva_entrada);
        fd.append("nueva_salida", d.nueva_salida);
      } else if (d.parcial) {
        fd.append("hora_desde", d.hora_desde);
        fd.append("hora_hasta", d.hora_hasta);
      }
      if (d.motivo.trim()) fd.append("motivo", d.motivo);
      if (archivo) fd.append("archivo", archivo);
      await subirConProgreso("/personal/solicitudes", fd, () => {});
      alGuardar();
    });
  };
  return (
    <form className="formulario formulario-solicitud" onSubmit={enviar}>
      <div className="segmentado" role="radiogroup" aria-label="Tipo de pedido">
        {cat.tipos.map((t) => (
          <button type="button" key={t.codigo} role="radio" aria-checked={d.tipo === t.codigo} className={d.tipo === t.codigo ? "activo" : ""} onClick={() => set("tipo", t.codigo)}>
            {t.texto}
          </button>
        ))}
      </div>
      <div className="grilla">
        {d.tipo === "licencia" && (
          <Campo etiqueta="Tipo de licencia *">
            <select required value={d.clase} onChange={(e) => set("clase", e.target.value)}>
              <option value="">Elegir…</option>
              {cat.clases_licencia.map((x) => (
                <option key={x.codigo} value={x.codigo}>
                  {x.texto}
                </option>
              ))}
            </select>
          </Campo>
        )}
        {d.tipo === "comision" && (
          <Campo etiqueta="Adónde *">
            <input required value={d.lugar} onChange={(e) => set("lugar", e.target.value)} placeholder="Ej.: CIC Barrio Norte, capacitación" />
          </Campo>
        )}
        <Campo etiqueta={d.tipo === "cambio_horario" ? "Desde el día *" : "Día *"}>
          <input type="date" required value={d.desde} onChange={(e) => set("desde", e.target.value)} />
        </Campo>
        <Campo etiqueta="Hasta (si es más de un día)">
          <input type="date" min={d.desde} value={d.hasta} onChange={(e) => set("hasta", e.target.value)} />
        </Campo>
        {d.tipo === "cambio_horario" ? (
          <>
            <Campo etiqueta="Nueva entrada *">
              <input type="time" required value={d.nueva_entrada} onChange={(e) => set("nueva_entrada", e.target.value)} />
            </Campo>
            <Campo etiqueta="Nueva salida *">
              <input type="time" required value={d.nueva_salida} onChange={(e) => set("nueva_salida", e.target.value)} />
            </Campo>
          </>
        ) : (
          <>
            <label className="casilla campo-completo">
              <input type="checkbox" checked={d.parcial} onChange={(e) => set("parcial", e.target.checked)} /> Solo una parte de la jornada
            </label>
            {d.parcial && (
              <>
                <Campo etiqueta="De">
                  <input type="time" required value={d.hora_desde} onChange={(e) => set("hora_desde", e.target.value)} />
                </Campo>
                <Campo etiqueta="A">
                  <input type="time" required value={d.hora_hasta} onChange={(e) => set("hora_hasta", e.target.value)} />
                </Campo>
              </>
            )}
          </>
        )}
        <Campo etiqueta="Motivo o detalle (opcional)" ancho="completo" ayuda={d.clase === "enfermedad" ? "En licencias por enfermedad, el motivo y el certificado los ven solo Personal y la Dirección." : undefined}>
          <textarea rows={2} value={d.motivo} onChange={(e) => set("motivo", e.target.value)} />
        </Campo>
        <Campo etiqueta="Certificado o nota (opcional)" ancho="completo">
          <input type="file" accept="application/pdf,image/jpeg,image/png" capture={undefined} onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </Campo>
      </div>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button type="button" className="boton" onClick={alCancelar}>
          Cancelar
        </button>
        <button className="boton boton-primario" disabled={envio.enviando}>
          Enviar pedido
        </button>
      </div>
    </form>
  );
}

function MisJornadas({ cat, agente }: { cat: CatalogoPersonal; agente: Agente }) {
  const hoy = hoyIso();
  const [desde, setDesde] = useState(hoy.slice(0, 8) + "01");
  const lista = useDatos(() => api.get<Jornada[]>("/personal/informe", { desde, hasta: hoy, agente_id: agente.id }), [desde]);
  const filas = (lista.datos ?? []).filter((f) => f.estado !== "sin_datos");
  return (
    <Seccion titulo="Mis jornadas">
      <div className="filtros">
        <label className="campo-linea">
          Desde <input type="date" value={desde} max={hoy} onChange={(e) => setDesde(e.target.value)} />
        </label>
      </div>
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : filas.length === 0 ? (
        <Vacio>Todavía no hay marcas importadas para estas fechas.</Vacio>
      ) : (
        <ul className="lista-jornadas">
          {filas.map((f) => (
            <li key={f.dia}>
              <span className="jornada-dia">{fecha(f.dia)}</span>
              <span>
                {f.entrada?.slice(0, 5) ?? "—"} → {f.salida?.slice(0, 5) ?? "—"}
              </span>
              <span>
                {f.incidencias.map((x) => (
                  <span key={x} className="marca marca-alerta">
                    {cat.incidencias[x] ?? x}
                  </span>
                ))}
                {f.incidencias_justificadas.length > 0 && <span className="marca marca-info">Justificada</span>}
              </span>
              <span className={`estado-jornada ej-${f.estado}`}>{ESTADOS_JORNADA[f.estado]}</span>
            </li>
          ))}
        </ul>
      )}
    </Seccion>
  );
}

/** Aviso del inicio para jefaturas: pedidos de su gente esperando aprobación. */
export function PedidosParaAprobar({ movil }: { movil?: boolean }) {
  const { datos } = usePendientesPersonal();
  if (!datos || datos.para_aprobar === 0) return null;
  const n = datos.para_aprobar;
  return (
    <a className={`pases-inicio ${movil ? "pases-inicio-movil" : ""}`} href={movil ? "#/m/mi-asistencia" : "#/mi-asistencia"}>
      📝 <strong>Personal:</strong> {n} {n === 1 ? "pedido para aprobar" : "pedidos para aprobar"} →
    </a>
  );
}

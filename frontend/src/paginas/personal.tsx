// Personal: la app «Asistencia DAM» dentro de SULAM. Resumen de jornadas con las
// reglas fijas, personal y horarios, importación del reloj, justificativos y pedidos.
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { api, subirConProgreso, type UsuarioBreve } from "../api";
import { Aviso, Campo, Cargando, Modal, Seccion, Vacio, fecha, fechaHora, useDatos, useEnvio, useSesion } from "../comun";

// ---------------------------------------------------------------- tipos

export interface CatalogoPersonal {
  codigos: string[];
  incidencias: Record<string, string>;
  criterios: Record<string, unknown>;
  clases_licencia: { codigo: string; texto: string }[];
  tipos: { codigo: string; texto: string }[];
  puedo: { consultar: boolean; administrar: boolean; aprobar: boolean };
  mi_agente: { id: number; nombre: string } | null;
}

interface HorarioV {
  id: number;
  vigente_desde: string;
  vigente_hasta: string | null;
  semana: Record<string, [string, string]>;
  confirmado: boolean;
  fuente: string;
}

export interface Agente {
  id: number;
  nombre: string;
  area: { id: number; nombre: string } | null;
  cargo: string | null;
  id_reloj: string | null;
  boleta: string | null;
  usuario: (UsuarioBreve & { activo: boolean }) | null;
  periodos: { desde: string | null; hasta: string | null }[];
  activo: boolean;
  revision: number;
  horarios: HorarioV[];
}

export interface Jornada {
  agente_id: number;
  nombre: string;
  dia: string;
  turno_desde: string | null;
  turno_hasta: string | null;
  entrada: string | null;
  salida: string | null;
  minutos_tarde: number;
  minutos_salida_anticipada: number;
  minutos_recuperados: number;
  minutos_diferencia: number;
  incidencias: string[];
  avisos: string[];
  incidencias_justificadas: string[];
  justificativos: { id: number; codigo: string; estado: string }[];
  evaluada: boolean;
  huella: string;
  revision: { decision: string; minutos: number; fundamento: string; usuario: string | null; automatica?: boolean } | null;
  revision_id: number | null;
  estado: "pendiente" | "revisado" | "justificado" | "auto_aprobado" | "sin_datos";
}

interface Justificativo {
  id: number;
  agente: { id: number; nombre: string };
  codigo: string;
  desde: string;
  hasta: string;
  hora_desde: string | null;
  hora_hasta: string | null;
  excepcion_desde: string | null;
  excepcion_hasta: string | null;
  referencia: string | null;
  notas: string | null;
  estado: "pendiente" | "aprobado" | "rechazado";
  requiere_horario: boolean;
  revision: number;
  fundamento: string | null;
  adjuntos: { id: string; nombre: string; mime: string }[];
  solicitud_id: number | null;
  usuario: UsuarioBreve | null;
  en: string;
}

interface Importacion {
  id: number;
  nombre_archivo: string;
  desde: string;
  hasta: string;
  filas: number;
  errores: string[];
  avisos: string[];
  sin_identificar: { id_reloj: string; nombre: string; sugerencias: { id: number; nombre: string }[] }[];
  incorporada: boolean;
  en: string;
}

export interface Solicitud {
  id: number;
  agente: { id: number; nombre: string; area: string | null };
  tipo: "licencia" | "comision" | "cambio_horario";
  tipo_texto: string;
  clase: string | null;
  clase_texto: string | null;
  desde: string;
  hasta: string;
  hora_desde: string | null;
  hora_hasta: string | null;
  nueva_entrada: string | null;
  nueva_salida: string | null;
  lugar: string | null;
  motivo: string | null;
  adjuntos: { id: string; nombre: string; mime: string }[];
  detalle_reservado: boolean;
  estado: "pendiente" | "aprobada" | "rechazada" | "cancelada" | "registrada";
  pedido_por: UsuarioBreve | null;
  pedido_en: string;
  decidido_por: UsuarioBreve | null;
  decidido_en: string | null;
  respuesta: string | null;
  registrado_por: UsuarioBreve | null;
  registrado_en: string | null;
  puedo_aprobar: boolean;
  puedo_cancelar: boolean;
  puedo_registrar: boolean;
}

export const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
export const ESTADOS_JORNADA: Record<string, string> = {
  pendiente: "Pendiente",
  revisado: "Revisado",
  justificado: "Justificado",
  auto_aprobado: "Aprobado automáticamente",
  sin_datos: "Sin datos",
};
export const ESTADOS_SOLICITUD: Record<string, string> = {
  pendiente: "Espera aprobación",
  aprobada: "Aprobada",
  rechazada: "Rechazada",
  cancelada: "Cancelada",
  registrada: "Registrada por Personal",
};

export function useCatalogoPersonal() {
  return useDatos(() => api.get<CatalogoPersonal>("/personal/catalogo"), []);
}

function hoyIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function inicioMes() {
  return hoyIso().slice(0, 8) + "01";
}

export function rangoTexto(desde: string, hasta: string) {
  return desde === hasta ? fecha(desde) : `${fecha(desde)} al ${fecha(hasta)}`;
}

export function textoSolicitud(s: Solicitud) {
  const partes = [s.tipo === "licencia" && s.clase_texto ? `${s.tipo_texto} · ${s.clase_texto}` : s.tipo_texto, rangoTexto(s.desde, s.hasta)];
  if (s.hora_desde) partes.push(`de ${s.hora_desde} a ${s.hora_hasta}`);
  if (s.tipo === "cambio_horario") partes.push(`nuevo horario ${s.nueva_entrada} a ${s.nueva_salida}`);
  if (s.lugar) partes.push(s.lugar);
  return partes.join(" · ");
}

// ---------------------------------------------------------------- página

const PESTANAS = ["Resumen", "Personal y horarios", "Importar reloj", "Justificativos", "Pedidos"] as const;
type Pestana = (typeof PESTANAS)[number];

export function PaginaPersonal() {
  const cat = useCatalogoPersonal();
  const [pestana, setPestana] = useState<Pestana>(() => {
    try {
      return (sessionStorage.getItem("sulam.personal.pestana") as Pestana) || "Resumen";
    } catch {
      return "Resumen";
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem("sulam.personal.pestana", pestana);
    } catch {
      /* sin almacenamiento */
    }
  }, [pestana]);
  const agentes = useDatos(() => api.get<Agente[]>("/personal/agentes", { incluir_bajas: true }), []);
  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  if (!cat.datos.puedo.consultar) return <Aviso error="Esta sección es de Personal y la Dirección." />;
  const c = cat.datos;
  return (
    <>
      <h1>Personal</h1>
      <div className="segmentado pestanas-personal" role="tablist">
        {PESTANAS.map((p) => (
          <button key={p} role="tab" aria-selected={pestana === p} className={pestana === p ? "activo" : ""} onClick={() => setPestana(p)}>
            {p}
          </button>
        ))}
      </div>
      <Aviso error={agentes.error} />
      {!agentes.datos ? (
        <Cargando />
      ) : pestana === "Resumen" ? (
        <Resumen cat={c} agentes={agentes.datos} />
      ) : pestana === "Personal y horarios" ? (
        <PersonalHorarios cat={c} agentes={agentes.datos} alCambiar={agentes.recargar} />
      ) : pestana === "Importar reloj" ? (
        <ImportarReloj cat={c} agentes={agentes.datos} alCambiar={agentes.recargar} />
      ) : pestana === "Justificativos" ? (
        <Justificativos cat={c} agentes={agentes.datos} />
      ) : (
        <PedidosPersonal cat={c} />
      )}
    </>
  );
}

// ---------------------------------------------------------------- resumen

function Resumen({ cat, agentes }: { cat: CatalogoPersonal; agentes: Agente[] }) {
  const [desde, setDesde] = useState(inicioMes());
  const [hasta, setHasta] = useState(hoyIso());
  const [agente, setAgente] = useState("");
  const [estado, setEstado] = useState("pendiente");
  const [buscar, setBuscar] = useState("");
  const [revisar, setRevisar] = useState<Jornada | null>(null);
  const [justificar, setJustificar] = useState<Jornada | null>(null);
  const { datos, error, recargar } = useDatos(
    () => api.get<Jornada[]>("/personal/informe", { desde, hasta, agente_id: agente || undefined }),
    [desde, hasta, agente],
  );
  const filas = useMemo(
    () => (datos ?? []).filter((f) => (!estado || f.estado === estado) && (!buscar || f.nombre.toLowerCase().includes(buscar.toLowerCase()))),
    [datos, estado, buscar],
  );
  const conteo = (e: string) => (datos ?? []).filter((f) => f.estado === e).length;
  return (
    <>
      <div className="filtros">
        <label className="campo-linea">
          Desde <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label className="campo-linea">
          Hasta <input type="date" value={hasta} min={desde} onChange={(e) => setHasta(e.target.value)} />
        </label>
        <select value={agente} onChange={(e) => setAgente(e.target.value)} aria-label="Persona">
          <option value="">Todo el personal</option>
          {agentes.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nombre}
              {a.activo ? "" : " (baja)"}
            </option>
          ))}
        </select>
        <input type="search" placeholder="Buscar nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label="Buscar nombre" />
      </div>
      <div className="indicadores indicadores-chicos">
        {Object.entries(ESTADOS_JORNADA).map(([k, t]) => (
          <button key={k} type="button" className={`indicador indicador-chico ${estado === k ? "indicador-activo" : ""} ${k === "pendiente" && conteo(k) ? "indicador-alerta" : ""}`} onClick={() => setEstado(estado === k ? "" : k)}>
            <span className="indicador-valor">{conteo(k)}</span>
            <span className="indicador-texto">{t}</span>
          </button>
        ))}
      </div>
      <p className="tenue">
        Criterios fijos: se ignoran los segundos; tolerancia de 10 min si se recupera a la salida el mismo día; ventana de 30 min antes y después. Los días sin
        semana importada no son ausencias.{estado ? ` Mostrando: ${ESTADOS_JORNADA[estado].toLowerCase()} (tocá el número para quitar el filtro).` : ""}
      </p>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : filas.length === 0 ? (
        <Vacio>No hay jornadas con ese filtro.</Vacio>
      ) : (
        <table className="tabla tabla-compacta">
          <thead>
            <tr>
              <th>Persona</th>
              <th>Día</th>
              <th>Turno</th>
              <th>Marcas</th>
              <th>Incidencias</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.agente_id + f.dia}>
                <td>{f.nombre}</td>
                <td>
                  {DIAS[(new Date(f.dia + "T12:00:00").getDay() + 6) % 7].slice(0, 3)} {fecha(f.dia)}
                </td>
                <td>{f.turno_desde ? `${f.turno_desde}–${f.turno_hasta}` : "—"}</td>
                <td>
                  {f.entrada?.slice(0, 5) ?? "—"} → {f.salida?.slice(0, 5) ?? "—"}
                </td>
                <td>
                  {f.incidencias.map((x) => (
                    <span key={x} className="marca marca-alerta">
                      {cat.incidencias[x] ?? x}
                    </span>
                  ))}
                  {f.incidencias_justificadas.map((x) => (
                    <span key={x} className="marca marca-info" title="Justificada">
                      ✓ {cat.incidencias[x] ?? x}
                    </span>
                  ))}
                  {f.avisos.includes("HORARIO_POR_CONFIRMAR") && <span className="marca">Horario por confirmar</span>}
                  {f.minutos_diferencia > 0 && <span className="tenue"> · dif. {f.minutos_diferencia} min</span>}
                </td>
                <td>
                  <span className={`estado-jornada ej-${f.estado}`}>{ESTADOS_JORNADA[f.estado]}</span>
                  {f.revision && !f.revision.automatica && <div className="tenue">{f.revision.usuario}</div>}
                </td>
                <td className="celda-acciones">
                  {cat.puedo.administrar && (f.estado === "pendiente" || f.estado === "revisado") && (
                    <button className="boton boton-chico" onClick={() => setRevisar(f)}>
                      Revisar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {revisar && (
        <Modal titulo={`Revisar · ${revisar.nombre} · ${fecha(revisar.dia)}`} alCerrar={() => setRevisar(null)}>
          <RevisarJornada
            cat={cat}
            f={revisar}
            alJustificar={() => {
              setJustificar(revisar);
              setRevisar(null);
            }}
            alGuardar={() => {
              setRevisar(null);
              recargar();
            }}
          />
        </Modal>
      )}
      {justificar && (
        <Modal titulo={`Justificativo · ${justificar.nombre}`} alCerrar={() => setJustificar(null)} ancho>
          <FormJustificativo
            cat={cat}
            agentes={agentes}
            inicial={{ agente_id: String(justificar.agente_id), desde: justificar.dia, hasta: justificar.dia }}
            alGuardar={() => {
              setJustificar(null);
              recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function RevisarJornada({ cat, f, alGuardar, alJustificar }: { cat: CatalogoPersonal; f: Jornada; alGuardar: () => void; alJustificar: () => void }) {
  const [decision, setDecision] = useState("sin_descuento");
  const [minutos, setMinutos] = useState(0);
  const [fundamento, setFundamento] = useState("");
  const envio = useEnvio();
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    envio.ejecutar(async () => {
      await api.post("/personal/revisiones", {
        agente_id: f.agente_id, dia: f.dia, decision, minutos: decision === "proponer_descuento" ? Number(minutos) : 0, fundamento,
        huella: f.huella, revision_vista: f.revision_id,
      });
      alGuardar();
    });
  };
  return (
    <form className="formulario" onSubmit={enviar}>
      <p>
        Turno {f.turno_desde ?? "—"}–{f.turno_hasta ?? "—"} · marcas {f.entrada ?? "sin entrada"} → {f.salida ?? "sin salida"}
      </p>
      <div>
        {f.incidencias.map((x) => (
          <span key={x} className="marca marca-alerta">
            {cat.incidencias[x] ?? x}
          </span>
        ))}
      </div>
      <p className="tenue">
        Diferencia técnica: {f.evaluada ? `${f.minutos_diferencia} min (tarde ${f.minutos_tarde}, salida anticipada ${f.minutos_salida_anticipada}, recuperados ${f.minutos_recuperados})` : "sin datos suficientes"}.
      </p>
      {f.justificativos.length > 0 && (
        <p className="tenue">Justificativos en el día: {f.justificativos.map((j) => `#${j.id} ${j.codigo} (${j.estado})`).join(", ")}</p>
      )}
      <div className="fila-botones fila-izquierda">
        <button type="button" className="boton" onClick={alJustificar}>
          Cargar justificativo para esta jornada
        </button>
      </div>
      <Campo etiqueta="Decisión">
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="sin_descuento">Revisado · sin descuento</option>
          <option value="pendiente">Mantener pendiente</option>
          <option value="proponer_descuento">Proponer minutos para evaluación</option>
        </select>
      </Campo>
      {decision === "proponer_descuento" && (
        <Campo etiqueta="Minutos propuestos" ayuda={`Hasta ${Math.ceil(f.minutos_diferencia)} (la diferencia técnica).`}>
          <input type="number" min={1} max={Math.ceil(f.minutos_diferencia)} value={minutos} onChange={(e) => setMinutos(Number(e.target.value))} required />
        </Campo>
      )}
      <Campo etiqueta="Fundamento *">
        <textarea rows={3} minLength={5} required value={fundamento} onChange={(e) => setFundamento(e.target.value)} />
      </Campo>
      <p className="tenue">Una propuesta requiere marcas completas y horario confirmado. No ejecuta descuentos ni liquidación.</p>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar revisión
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- personal y horarios

function PersonalHorarios({ cat, agentes, alCambiar }: { cat: CatalogoPersonal; agentes: Agente[]; alCambiar: () => void }) {
  const [verBajas, setVerBajas] = useState(false);
  const [alta, setAlta] = useState(false);
  const [editar, setEditar] = useState<Agente | null>(null);
  const [horario, setHorario] = useState<Agente | null>(null);
  const [bajaDe, setBajaDe] = useState<Agente | null>(null);
  const [buscar, setBuscar] = useState("");
  const lista = agentes.filter((a) => (verBajas || a.activo) && (!buscar || a.nombre.toLowerCase().includes(buscar.toLowerCase())));
  const turnoTexto = (h?: HorarioV) => {
    if (!h) return "Sin horario";
    const grupos: Record<string, string[]> = {};
    Object.entries(h.semana).forEach(([d, t]) => (grupos[t.join("–")] ??= []).push(DIAS[Number(d)].slice(0, 2)));
    return Object.entries(grupos)
      .map(([t, ds]) => `${ds.join(" ")} ${t}`)
      .join(" · ");
  };
  return (
    <>
      <div className="filtros">
        <input type="search" placeholder="Buscar nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label="Buscar" />
        <label className="casilla">
          <input type="checkbox" checked={verBajas} onChange={(e) => setVerBajas(e.target.checked)} /> Mostrar también bajas
        </label>
        {cat.puedo.administrar && (
          <button className="boton boton-primario" onClick={() => setAlta(true)}>
            Agregar persona
          </button>
        )}
      </div>
      <table className="tabla tabla-compacta">
        <thead>
          <tr>
            <th>Persona</th>
            <th>Área y cargo</th>
            <th>ID reloj · boleta</th>
            <th>Horario vigente</th>
            <th>Usuario SULAM</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {lista.map((a) => {
            const h = a.horarios.find((x) => !x.vigente_hasta) ?? a.horarios[0];
            return (
              <tr key={a.id} className={a.activo ? "" : "fila-inactiva"}>
                <td>
                  <strong>{a.nombre}</strong>
                  {!a.activo && <div className="tenue">Baja</div>}
                </td>
                <td>
                  {a.area?.nombre.replace(/^(Departamento|División) /, "") ?? "—"}
                  {a.cargo && <div className="tenue">{a.cargo}</div>}
                </td>
                <td>
                  {a.id_reloj ?? <span className="texto-alerta">sin ID</span>} · {a.boleta ?? "s/c"}
                </td>
                <td>
                  {turnoTexto(h)}
                  {h && !h.confirmado && <div className="texto-alerta">Por confirmar</div>}
                </td>
                <td>{a.usuario ? `${a.usuario.usuario}${a.usuario.activo ? "" : " (inactivo)"}` : <span className="tenue">—</span>}</td>
                <td className="celda-acciones">
                  {cat.puedo.administrar && (
                    <>
                      <button className="boton boton-chico" onClick={() => setHorario(a)}>
                        Horario
                      </button>
                      <button className="boton boton-chico" onClick={() => setEditar(a)}>
                        Editar
                      </button>
                      <button className="boton boton-chico boton-texto" onClick={() => setBajaDe(a)}>
                        {a.activo ? "Baja" : "Reingreso"}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {alta && (
        <Modal titulo="Agregar persona" alCerrar={() => setAlta(false)} ancho>
          <FormAgente
            alGuardar={() => {
              setAlta(false);
              alCambiar();
            }}
          />
        </Modal>
      )}
      {editar && (
        <Modal titulo={`Editar · ${editar.nombre}`} alCerrar={() => setEditar(null)} ancho>
          <FormAgente
            agente={editar}
            alGuardar={() => {
              setEditar(null);
              alCambiar();
            }}
          />
        </Modal>
      )}
      {horario && (
        <Modal titulo={`Horario · ${horario.nombre}`} alCerrar={() => setHorario(null)} ancho>
          <EditorHorario
            agente={horario}
            alGuardar={() => {
              setHorario(null);
              alCambiar();
            }}
          />
        </Modal>
      )}
      {bajaDe && (
        <Modal titulo={`${bajaDe.activo ? "Baja" : "Reingreso"} · ${bajaDe.nombre}`} alCerrar={() => setBajaDe(null)}>
          <FormBaja
            agente={bajaDe}
            alGuardar={() => {
              setBajaDe(null);
              alCambiar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function FormAgente({ agente, alGuardar }: { agente?: Agente; alGuardar: () => void }) {
  const { catalogos } = useSesion();
  const usuarios = useDatos(() => api.get<{ id: string; usuario: string; nombre_completo: string }[]>("/personal/usuarios-libres"), []);
  const [d, setD] = useState({
    nombre: agente?.nombre ?? "",
    fecha_ingreso: hoyIso(),
    area_id: agente?.area ? String(agente.area.id) : "",
    cargo: agente?.cargo ?? "",
    id_reloj: agente?.id_reloj ?? "",
    boleta: agente?.boleta ?? "",
    usuario_id: agente?.usuario?.id ?? "",
    modo_usuario: "ninguno" as "ninguno" | "vincular" | "crear",
    crear_usuario: "",
    password_inicial: "",
  });
  const envio = useEnvio();
  const set = (k: keyof typeof d, v: string) => setD((x) => ({ ...x, [k]: v }));
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    envio.ejecutar(async () => {
      const comun = { nombre: d.nombre, area_id: d.area_id ? Number(d.area_id) : null, cargo: d.cargo || null, id_reloj: d.id_reloj || null, boleta: d.boleta || null };
      if (agente) {
        await api.patch(`/personal/agentes/${agente.id}`, { ...comun, ...(d.usuario_id && d.usuario_id !== agente.usuario?.id ? { usuario_id: d.usuario_id } : {}) });
      } else {
        await api.post("/personal/agentes", {
          ...comun,
          fecha_ingreso: d.fecha_ingreso,
          usuario_id: d.modo_usuario === "vincular" ? d.usuario_id || null : null,
          crear_usuario: d.modo_usuario === "crear" ? d.crear_usuario : null,
          password_inicial: d.modo_usuario === "crear" ? d.password_inicial : null,
        });
      }
      alGuardar();
    });
  };
  return (
    <form className="formulario" onSubmit={enviar}>
      <div className="grilla">
        <Campo etiqueta="Apellido y nombre *">
          <input required minLength={3} value={d.nombre} onChange={(e) => set("nombre", e.target.value)} />
        </Campo>
        {!agente && (
          <Campo etiqueta="Fecha de ingreso *">
            <input type="date" required value={d.fecha_ingreso} onChange={(e) => set("fecha_ingreso", e.target.value)} />
          </Campo>
        )}
        <Campo etiqueta="Área">
          <select value={d.area_id} onChange={(e) => set("area_id", e.target.value)}>
            <option value="">—</option>
            {catalogos.areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Cargo o función">
          <input value={d.cargo} onChange={(e) => set("cargo", e.target.value)} />
        </Campo>
        <Campo etiqueta="ID del reloj" ayuda="El número que figura en el reloj. Si no se conoce, se completa al importar.">
          <input value={d.id_reloj} onChange={(e) => set("id_reloj", e.target.value)} />
        </Campo>
        <Campo etiqueta="Boleta">
          <input value={d.boleta} onChange={(e) => set("boleta", e.target.value)} />
        </Campo>
      </div>
      <h3>Usuario de SULAM</h3>
      {agente?.usuario ? (
        <p>
          Vinculada a <strong>{agente.usuario.usuario}</strong>. Al darla de baja, el usuario se desactiva; el área de Personal se refleja en su usuario.
        </p>
      ) : (
        <>
          <div className="opciones-linea">
            {(
              [
                ["ninguno", "Sin usuario (no usa SULAM)"],
                ["vincular", "Vincular a un usuario existente"],
                ...(agente ? [] : [["crear", "Crear el usuario ahora"]]),
              ] as [string, string][]
            ).map(([k, t]) => (
              <label key={k} className="casilla">
                <input type="radio" name="modo" checked={d.modo_usuario === k} onChange={() => set("modo_usuario", k)} /> {t}
              </label>
            ))}
          </div>
          {d.modo_usuario === "vincular" && (
            <Campo etiqueta="Usuario">
              <select value={d.usuario_id} onChange={(e) => set("usuario_id", e.target.value)} required>
                <option value="">Elegir…</option>
                {(usuarios.datos ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nombre_completo} ({u.usuario})
                  </option>
                ))}
              </select>
            </Campo>
          )}
          {d.modo_usuario === "crear" && (
            <div className="grilla">
              <Campo etiqueta="Nombre de usuario *">
                <input required value={d.crear_usuario} onChange={(e) => set("crear_usuario", e.target.value)} autoComplete="off" />
              </Campo>
              <Campo etiqueta="Contraseña inicial *" ayuda="La persona la cambia al entrar por primera vez. El rol lo asigna Administración.">
                <input required type="text" value={d.password_inicial} onChange={(e) => set("password_inicial", e.target.value)} autoComplete="off" />
              </Campo>
            </div>
          )}
        </>
      )}
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          {agente ? "Guardar" : "Agregar"}
        </button>
      </div>
    </form>
  );
}

function FormBaja({ agente, alGuardar }: { agente: Agente; alGuardar: () => void }) {
  const [f, setF] = useState(hoyIso());
  const envio = useEnvio();
  return (
    <div className="formulario">
      <p>
        {agente.activo
          ? "La baja no borra la persona, sus marcas ni sus justificativos. Los informes anteriores se conservan."
          : "El reingreso abre un nuevo período de alta."}
        {agente.usuario && agente.activo && " Su usuario de SULAM se desactiva y se cierran sus sesiones."}
      </p>
      <Campo etiqueta={agente.activo ? "Fecha de baja (primer día sin trabajar)" : "Fecha de reingreso"}>
        <input type="date" value={f} onChange={(e) => setF(e.target.value)} />
      </Campo>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button
          className={agente.activo ? "boton boton-peligro" : "boton boton-primario"}
          disabled={envio.enviando}
          onClick={() =>
            envio
              .ejecutar(() => api.post<{ efecto_usuario: string | null }>(`/personal/agentes/${agente.id}/alta-baja`, { activo: !agente.activo, fecha: f, revision_vista: agente.revision }))
              .then((r) => r && alGuardar())
          }
        >
          {agente.activo ? "Confirmar baja" : "Confirmar reingreso"}
        </button>
      </div>
    </div>
  );
}

function EditorHorario({ agente, alGuardar }: { agente: Agente; alGuardar: () => void }) {
  const actual = agente.horarios[0];
  const [desde, setDesde] = useState(actual?.vigente_desde ?? hoyIso());
  const [semana, setSemana] = useState<Record<string, [string, string]>>(actual?.semana ?? { "0": ["08:00", "13:00"], "1": ["08:00", "13:00"], "2": ["08:00", "13:00"], "3": ["08:00", "13:00"], "4": ["08:00", "13:00"] });
  const [fuente, setFuente] = useState(actual?.fuente ?? "");
  const [confirmado, setConfirmado] = useState(false);
  const envio = useEnvio();
  const cambiar = (d: number, i: number, v: string) => setSemana((s) => ({ ...s, [d]: s[d].map((x, j) => (j === i ? v : x)) as [string, string] }));
  return (
    <form
      className="formulario"
      onSubmit={(e) => {
        e.preventDefault();
        envio.ejecutar(() => api.post(`/personal/agentes/${agente.id}/horarios`, { vigente_desde: desde, semana, confirmado, fuente })).then((r) => r && alGuardar());
      }}
    >
      <p className="tenue">Confirmá el horario o registrá una nueva vigencia. Las jornadas desde esa fecha se recalculan con los criterios fijos.</p>
      <div className="grilla">
        <Campo etiqueta="Vigente desde">
          <input type="date" required value={desde} onChange={(e) => setDesde(e.target.value)} />
        </Campo>
        <Campo etiqueta="Referencia (de dónde sale el horario) *">
          <input required minLength={5} value={fuente} onChange={(e) => setFuente(e.target.value)} placeholder="Ej.: Nota 123/2026, planilla firmada" />
        </Campo>
      </div>
      <div className="semana-horario">
        {DIAS.map((dia, i) => (
          <div key={dia} className="dia-horario">
            <label className="casilla">
              <input
                type="checkbox"
                checked={Boolean(semana[i])}
                onChange={(e) =>
                  setSemana((s) => {
                    const n = { ...s };
                    if (e.target.checked) n[i] = ["08:00", "13:00"];
                    else delete n[i];
                    return n;
                  })
                }
              />
              {dia}
            </label>
            {semana[i] ? (
              <span>
                <input type="time" aria-label={`Entrada ${dia}`} value={semana[i][0]} onChange={(e) => cambiar(i, 0, e.target.value)} required /> a{" "}
                <input type="time" aria-label={`Salida ${dia}`} value={semana[i][1]} onChange={(e) => cambiar(i, 1, e.target.value)} required />
              </span>
            ) : (
              <span className="tenue">Sin turno</span>
            )}
          </div>
        ))}
      </div>
      <label className="casilla">
        <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} /> Confirmo el horario y su referencia
      </label>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar versión
        </button>
      </div>
      {agente.horarios.length > 0 && (
        <details>
          <summary>Versiones anteriores ({agente.horarios.length})</summary>
          <ul className="lista-simple">
            {agente.horarios.map((h) => (
              <li key={h.id}>
                {fecha(h.vigente_desde)} → {h.vigente_hasta ? fecha(h.vigente_hasta) : "vigente"} · {h.confirmado ? "confirmado" : "por confirmar"} · {h.fuente}
              </li>
            ))}
          </ul>
        </details>
      )}
    </form>
  );
}

// ---------------------------------------------------------------- reloj

function ImportarReloj({ agentes, alCambiar }: { cat: CatalogoPersonal; agentes: Agente[]; alCambiar: () => void }) {
  const lista = useDatos(() => api.get<Importacion[]>("/personal/reloj"), []);
  const [previa, setPrevia] = useState<Importacion | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const envio = useEnvio();
  const subir = () =>
    envio.ejecutar(async () => {
      const fd = new FormData();
      fd.append("archivo", archivo!);
      setPrevia(await subirConProgreso<Importacion>("/personal/reloj/previa", fd, () => {}));
      lista.recargar();
    });
  const sinId = agentes.filter((a) => a.activo && !a.id_reloj);
  return (
    <>
      <Seccion titulo="Importar la semana del reloj">
        <p className="tenue">Subí el «.xls» que exporta el reloj. Primero se muestra una vista previa; las marcas se incorporan recién cuando lo confirmás. Un archivo ya subido se reconoce y no se duplica.</p>
        <div className="filtros">
          <input type="file" accept=".xls,.html,.htm" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
          <button className="boton boton-primario" disabled={!archivo || envio.enviando} onClick={subir}>
            Ver vista previa
          </button>
        </div>
        <Aviso error={envio.error} />
        {previa && <VistaPrevia i={previa} agentes={sinId} alCambiar={(x) => { setPrevia(x); lista.recargar(); alCambiar(); }} />}
      </Seccion>
      <Seccion titulo="Semanas importadas">
        {!lista.datos ? (
          <Cargando />
        ) : lista.datos.length === 0 ? (
          <Vacio>Todavía no se importó ninguna semana.</Vacio>
        ) : (
          <table className="tabla tabla-compacta">
            <thead>
              <tr>
                <th>Período</th>
                <th>Archivo</th>
                <th>Filas</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lista.datos.map((i) => (
                <tr key={i.id}>
                  <td>{rangoTexto(i.desde, i.hasta)}</td>
                  <td>{i.nombre_archivo}</td>
                  <td>{i.filas}</td>
                  <td>{i.incorporada ? "Incorporada" : <span className="texto-alerta">Sin incorporar</span>}</td>
                  <td className="celda-acciones">
                    {!i.incorporada && (
                      <button className="boton boton-chico" onClick={() => setPrevia(i)}>
                        Continuar
                      </button>
                    )}
                    <a className="boton boton-chico" href={`/api/personal/reloj/${i.id}/original`}>
                      Original
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>
    </>
  );
}

function VistaPrevia({ i, agentes, alCambiar }: { i: Importacion; agentes: Agente[]; alCambiar: (x: Importacion | null) => void }) {
  const envio = useEnvio();
  const [eleccion, setEleccion] = useState<Record<string, string>>({});
  const [listo, setListo] = useState<string | null>(null);
  return (
    <div className="vista-previa-reloj">
      <p>
        <strong>{i.nombre_archivo}</strong> · {rangoTexto(i.desde, i.hasta)} · {i.filas} filas
      </p>
      {i.avisos.map((a) => (
        <p key={a} className="tenue">
          {a}
        </p>
      ))}
      {i.errores.length > 0 && <Aviso error={`Errores en el archivo: ${i.errores.join(" · ")}`} />}
      {i.incorporada ? (
        <Aviso tipo="exito" error="Esta semana ya está incorporada." />
      ) : (
        <>
          {i.sin_identificar.length > 0 && (
            <>
              <h3>Personas del reloj sin identificar ({i.sin_identificar.length})</h3>
              <p className="tenue">Elegí a quién corresponde cada ID. Se guarda en su ficha.</p>
              <ul className="lista-pases">
                {i.sin_identificar.map((x) => (
                  <li key={x.id_reloj} className="fila-pase">
                    <div>
                      ID <strong>{x.id_reloj}</strong> · {x.nombre}
                    </div>
                    <div className="fila-pase-acciones">
                      <select
                        value={eleccion[x.id_reloj] ?? (x.sugerencias[0] ? String(x.sugerencias[0].id) : "")}
                        onChange={(e) => setEleccion({ ...eleccion, [x.id_reloj]: e.target.value })}
                        aria-label={`Persona para ${x.id_reloj}`}
                      >
                        <option value="">Elegir…</option>
                        {agentes.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.nombre}
                            {x.sugerencias.some((s) => s.id === a.id) ? " (coincide)" : ""}
                          </option>
                        ))}
                      </select>
                      <button
                        className="boton boton-chico"
                        disabled={envio.enviando || !(eleccion[x.id_reloj] ?? x.sugerencias[0]?.id)}
                        onClick={() =>
                          envio
                            .ejecutar(() =>
                              api.post<Importacion>(`/personal/reloj/${i.id}/identificar`, {
                                id_reloj: x.id_reloj,
                                agente_id: Number(eleccion[x.id_reloj] ?? x.sugerencias[0]?.id),
                              }),
                            )
                            .then((r) => r && alCambiar(r))
                        }
                      >
                        Asignar
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="fila-botones fila-izquierda">
            <button
              className="boton boton-primario"
              disabled={envio.enviando || i.errores.length > 0 || i.sin_identificar.length > 0}
              onClick={() =>
                envio.ejecutar(() => api.post<{ incorporadas: number }>(`/personal/reloj/${i.id}/incorporar`)).then((r) => {
                  if (r) {
                    setListo(`Se incorporaron ${r.incorporadas} marcas.`);
                    alCambiar({ ...i, incorporada: true });
                  }
                })
              }
            >
              Incorporar semana
            </button>
          </div>
        </>
      )}
      {listo && <Aviso tipo="exito" error={listo} />}
      <Aviso error={envio.error} />
    </div>
  );
}

// ---------------------------------------------------------------- justificativos

function FormJustificativo({
  cat,
  agentes,
  inicial,
  alGuardar,
}: {
  cat: CatalogoPersonal;
  agentes: Agente[];
  inicial?: { agente_id?: string; desde?: string; hasta?: string };
  alGuardar: () => void;
}) {
  const [d, setD] = useState({
    agente_id: inicial?.agente_id ?? "",
    codigo: "CT",
    desde: inicial?.desde ?? hoyIso(),
    hasta: inicial?.hasta ?? "",
    hora_desde: "",
    hora_hasta: "",
    excepcion_desde: "",
    excepcion_hasta: "",
    referencia: "",
    notas: "",
  });
  const [archivo, setArchivo] = useState<File | null>(null);
  const envio = useEnvio();
  const set = (k: keyof typeof d, v: string) => setD((x) => ({ ...x, [k]: v }));
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    envio.ejecutar(async () => {
      const j = await api.post<Justificativo>("/personal/justificativos", {
        agente_id: Number(d.agente_id), codigo: d.codigo, desde: d.desde, hasta: d.hasta || null,
        hora_desde: d.hora_desde || null, hora_hasta: d.hora_hasta || null,
        excepcion_desde: d.codigo === "CAMBIO" ? d.excepcion_desde || null : null, excepcion_hasta: d.codigo === "CAMBIO" ? d.excepcion_hasta || null : null,
        referencia: d.referencia || null, notas: d.notas || null,
      });
      if (archivo) {
        const fd = new FormData();
        fd.append("archivo", archivo);
        await subirConProgreso(`/personal/justificativos/${j.id}/adjuntos`, fd, () => {});
      }
      alGuardar();
    });
  };
  return (
    <form className="formulario" onSubmit={enviar}>
      <div className="grilla">
        <Campo etiqueta="Persona *">
          <select required value={d.agente_id} onChange={(e) => set("agente_id", e.target.value)}>
            <option value="">Elegir…</option>
            {agentes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Código *">
          <select value={d.codigo} onChange={(e) => set("codigo", e.target.value)}>
            {cat.codigos.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Desde (inclusive) *">
          <input type="date" required value={d.desde} onChange={(e) => set("desde", e.target.value)} />
        </Campo>
        <Campo etiqueta="Hasta (opcional)">
          <input type="date" min={d.desde} value={d.hasta} onChange={(e) => set("hasta", e.target.value)} />
        </Campo>
        <Campo etiqueta="Tramo desde (opcional)">
          <input type="time" value={d.hora_desde} onChange={(e) => set("hora_desde", e.target.value)} />
        </Campo>
        <Campo etiqueta="Tramo hasta (opcional)">
          <input type="time" value={d.hora_hasta} onChange={(e) => set("hora_hasta", e.target.value)} />
        </Campo>
        {d.codigo === "CAMBIO" && (
          <>
            <Campo etiqueta="Nueva entrada">
              <input type="time" value={d.excepcion_desde} onChange={(e) => set("excepcion_desde", e.target.value)} />
            </Campo>
            <Campo etiqueta="Nueva salida">
              <input type="time" value={d.excepcion_hasta} onChange={(e) => set("excepcion_hasta", e.target.value)} />
            </Campo>
          </>
        )}
        <Campo etiqueta="Referencia (opcional)" ancho="completo">
          <input value={d.referencia} onChange={(e) => set("referencia", e.target.value)} />
        </Campo>
        <Campo etiqueta="Observaciones" ancho="completo">
          <textarea rows={2} value={d.notas} onChange={(e) => set("notas", e.target.value)} />
        </Campo>
        <Campo etiqueta="Adjunto (PDF, JPG o PNG)" ancho="completo">
          <input type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </Campo>
      </div>
      <p className="tenue">
        Sólo hacen falta persona, código y fecha. Se aplica al cargarlo, salvo CAMBIO sin nuevo horario (queda pendiente). Sin tramo cubre el día completo; con tramo,
        sólo las incidencias contenidas en él. Una marca faltante requiere cubrir todo el turno.
      </p>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Cargar justificativo
        </button>
      </div>
    </form>
  );
}

function Justificativos({ cat, agentes }: { cat: CatalogoPersonal; agentes: Agente[] }) {
  const [agente, setAgente] = useState("");
  const lista = useDatos(() => api.get<Justificativo[]>("/personal/justificativos", { agente_id: agente || undefined }), [agente]);
  const [nuevo, setNuevo] = useState(false);
  const [decidir, setDecidir] = useState<Justificativo | null>(null);
  const [completar, setCompletar] = useState<Justificativo | null>(null);
  return (
    <>
      <div className="filtros">
        <select value={agente} onChange={(e) => setAgente(e.target.value)} aria-label="Persona">
          <option value="">Todo el personal</option>
          {agentes.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nombre}
            </option>
          ))}
        </select>
        {cat.puedo.administrar && (
          <button className="boton boton-primario" onClick={() => setNuevo(true)}>
            Cargar justificativo
          </button>
        )}
      </div>
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <Vacio>No hay justificativos.</Vacio>
      ) : (
        <table className="tabla tabla-compacta">
          <thead>
            <tr>
              <th>#</th>
              <th>Persona</th>
              <th>Código</th>
              <th>Fechas</th>
              <th>Estado</th>
              <th>Documentación</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lista.datos.map((j) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>{j.agente.nombre}</td>
                <td>
                  <strong>{j.codigo}</strong>
                  {j.codigo === "CAMBIO" && j.excepcion_desde && <div className="tenue">{j.excepcion_desde}–{j.excepcion_hasta}</div>}
                </td>
                <td>
                  {rangoTexto(j.desde, j.hasta)}
                  {j.hora_desde && <div className="tenue">{j.hora_desde}–{j.hora_hasta}</div>}
                </td>
                <td>
                  <span className={`estado-jornada ej-${j.estado === "aprobado" ? "justificado" : j.estado === "pendiente" ? "pendiente" : "sin_datos"}`}>{j.estado}</span>
                  {j.solicitud_id && <div className="tenue">Pedido N° {j.solicitud_id}</div>}
                </td>
                <td>
                  {j.referencia && <div>{j.referencia}</div>}
                  {j.adjuntos.map((x) => (
                    <a key={x.id} href={`/api/personal/justificativos/${j.id}/adjuntos/${x.id}`} target="_blank" rel="noreferrer">
                      📎 {x.nombre}
                    </a>
                  ))}
                </td>
                <td className="celda-acciones">
                  {cat.puedo.administrar && j.requiere_horario && (
                    <button className="boton boton-chico boton-primario" onClick={() => setCompletar(j)}>
                      Completar horario
                    </button>
                  )}
                  {cat.puedo.administrar && (
                    <button className="boton boton-chico" onClick={() => setDecidir(j)}>
                      Decisión
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {nuevo && (
        <Modal titulo="Cargar justificativo" alCerrar={() => setNuevo(false)} ancho>
          <FormJustificativo
            cat={cat}
            agentes={agentes.filter((a) => a.activo)}
            alGuardar={() => {
              setNuevo(false);
              lista.recargar();
            }}
          />
        </Modal>
      )}
      {decidir && (
        <Modal titulo={`Justificativo #${decidir.id} · ${decidir.codigo}`} alCerrar={() => setDecidir(null)}>
          <FormDecisionJust
            j={decidir}
            alGuardar={() => {
              setDecidir(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
      {completar && (
        <Modal titulo={`Completar cambio de horario · ${completar.agente.nombre}`} alCerrar={() => setCompletar(null)}>
          <FormCompletar
            j={completar}
            alGuardar={() => {
              setCompletar(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function FormDecisionJust({ j, alGuardar }: { j: Justificativo; alGuardar: () => void }) {
  const [estado, setEstado] = useState(j.estado === "aprobado" ? "rechazado" : "aprobado");
  const [fundamento, setFundamento] = useState("");
  const envio = useEnvio();
  return (
    <form
      className="formulario"
      onSubmit={(e) => {
        e.preventDefault();
        envio.ejecutar(() => api.post(`/personal/justificativos/${j.id}/decision`, { estado, fundamento, revision_vista: j.revision })).then((r) => r && alGuardar());
      }}
    >
      <p>
        {j.agente.nombre} · {rangoTexto(j.desde, j.hasta)} · estado actual: {j.estado}
      </p>
      {j.fundamento && <p className="tenue">{j.fundamento}</p>}
      <Campo etiqueta="Decisión">
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="aprobado">Aprobar documentación</option>
          <option value="rechazado">Rechazar (reabre las incidencias que cubría)</option>
        </select>
      </Campo>
      <Campo etiqueta="Fundamento *">
        <textarea rows={3} minLength={5} required value={fundamento} onChange={(e) => setFundamento(e.target.value)} />
      </Campo>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar decisión
        </button>
      </div>
    </form>
  );
}

function FormCompletar({ j, alGuardar }: { j: Justificativo; alGuardar: () => void }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const envio = useEnvio();
  return (
    <form
      className="formulario"
      onSubmit={(e) => {
        e.preventDefault();
        envio.ejecutar(() => api.post(`/personal/justificativos/${j.id}/completar-horario`, { excepcion_desde: a, excepcion_hasta: b, revision_vista: j.revision })).then((r) => r && alGuardar());
      }}
    >
      <p>{rangoTexto(j.desde, j.hasta)}</p>
      <div className="grilla">
        <Campo etiqueta="Nueva entrada *">
          <input type="time" required value={a} onChange={(e) => setA(e.target.value)} />
        </Campo>
        <Campo etiqueta="Nueva salida *">
          <input type="time" required value={b} onChange={(e) => setB(e.target.value)} />
        </Campo>
      </div>
      <Aviso error={envio.error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Aplicar el cambio
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- pedidos (vista de Personal)

function PedidosPersonal({ cat }: { cat: CatalogoPersonal }) {
  const [vista, setVista] = useState<"para_registrar" | "todas">("para_registrar");
  const lista = useDatos(() => api.get<Solicitud[]>("/personal/solicitudes", { vista }), [vista]);
  return (
    <>
      <div className="segmentado" role="group">
        <button className={vista === "para_registrar" ? "activo" : ""} onClick={() => setVista("para_registrar")}>
          Aprobados para registrar
        </button>
        <button className={vista === "todas" ? "activo" : ""} onClick={() => setVista("todas")}>
          Todos
        </button>
      </div>
      <p className="tenue">Los pedidos los hace cada persona desde «Mi asistencia» y los aprueba su jefatura. Al registrarlos se cargan como justificativos.</p>
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <Vacio>{vista === "para_registrar" ? "No hay pedidos aprobados esperando." : "No hay pedidos."}</Vacio>
      ) : (
        <ul className="lista-solicitudes">
          {lista.datos.map((s) => (
            <TarjetaSolicitud key={s.id} s={s} cat={cat} alCambiar={lista.recargar} mostrarPersona />
          ))}
        </ul>
      )}
    </>
  );
}

export function TarjetaSolicitud({
  s,
  cat,
  alCambiar,
  mostrarPersona,
  movil,
}: {
  s: Solicitud;
  cat: CatalogoPersonal;
  alCambiar: () => void;
  mostrarPersona?: boolean;
  movil?: boolean;
}) {
  const envio = useEnvio();
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [codigo, setCodigo] = useState(s.tipo === "cambio_horario" ? "CAMBIO" : "");
  const hacer = (f: () => Promise<unknown>) => envio.ejecutar(f).then((r) => r !== undefined && (alCambiar(), window.dispatchEvent(new Event("sulam:personal"))));
  return (
    <li className={`solicitud solicitud-${s.estado} ${movil ? "solicitud-movil" : ""}`}>
      <div className="solicitud-cuerpo">
        {mostrarPersona && (
          <strong className="solicitud-persona">
            {s.agente.nombre}
            {s.agente.area && <span className="tenue"> · {s.agente.area.replace(/^(Departamento|División) /, "")}</span>}
          </strong>
        )}
        <div>{textoSolicitud(s)}</div>
        {s.motivo && <div className="tenue">«{s.motivo}»</div>}
        {s.detalle_reservado && <div className="tenue">Motivo y certificado reservados (los ven la persona, Personal y la Dirección).</div>}
        {s.adjuntos.map((x) => (
          <a key={x.id} href={`/api/personal/solicitudes/${s.id}/adjuntos/${x.id}`} target="_blank" rel="noreferrer">
            📎 {x.nombre}
          </a>
        ))}
        <div className="tenue solicitud-estado">
          <span className={`chip-solicitud cs-${s.estado}`}>{ESTADOS_SOLICITUD[s.estado]}</span> pedido el {fechaHora(s.pedido_en)}
          {s.decidido_por && ` · ${s.estado === "rechazada" ? "rechazó" : "aprobó"} ${s.decidido_por.nombre_completo}`}
          {s.respuesta && ` («${s.respuesta}»)`}
          {s.registrado_por && ` · registró ${s.registrado_por.nombre_completo}`}
        </div>
      </div>
      <div className="solicitud-acciones">
        {s.puedo_aprobar && rechazo === null && (
          <>
            <button className="boton boton-primario" disabled={envio.enviando} onClick={() => hacer(() => api.post(`/personal/solicitudes/${s.id}/decidir`, { aprobar: true }))}>
              Aprobar
            </button>
            <button className="boton boton-texto" onClick={() => setRechazo("")}>
              No aprobar
            </button>
          </>
        )}
        {rechazo !== null && (
          <>
            <input autoFocus placeholder="Motivo" value={rechazo} onChange={(e) => setRechazo(e.target.value)} />
            <button className="boton" disabled={!rechazo.trim() || envio.enviando} onClick={() => hacer(() => api.post(`/personal/solicitudes/${s.id}/decidir`, { aprobar: false, respuesta: rechazo }))}>
              Avisar
            </button>
          </>
        )}
        {s.puedo_registrar && (
          <>
            {s.tipo !== "cambio_horario" && (
              <select value={codigo} onChange={(e) => setCodigo(e.target.value)} aria-label="Código">
                <option value="">Código…</option>
                {cat.codigos
                  .filter((c) => c !== "CAMBIO")
                  .map((c) => (
                    <option key={c}>{c}</option>
                  ))}
              </select>
            )}
            <button className="boton boton-primario" disabled={!codigo || envio.enviando} onClick={() => hacer(() => api.post(`/personal/solicitudes/${s.id}/registrar`, { codigo }))}>
              Registrar
            </button>
          </>
        )}
        {s.puedo_cancelar && (
          <button className="boton boton-texto" disabled={envio.enviando} onClick={() => hacer(() => api.post(`/personal/solicitudes/${s.id}/cancelar`))}>
            Cancelar pedido
          </button>
        )}
      </div>
      <Aviso error={envio.error} />
    </li>
  );
}

export function Etiqueta({ children }: { children: ReactNode }) {
  return <span className="marca">{children}</span>;
}

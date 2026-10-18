// Subsidios: residencia de larga estadía, cuidador domiciliario, alimentarios, materiales y otros.
// Trámite con lista de papeles, resolución y vigencia; pagos mensuales con su propia documentación.

import { useState } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Enlace, Modal, Seccion, Vacio, fecha, useDatos, useEnvio, useSesion, valor } from "../comun";

interface Opcion {
  codigo: string;
  texto: string;
}
interface CatalogoSubsidios {
  tipos: Opcion[];
  estados: Opcion[];
  estados_pago: Opcion[];
  estados_requisito: Opcion[];
  grupos: Record<string, string>;
  mensuales: string[];
  puede: { crear: boolean; modificar: string | null; administrar: boolean };
}
interface Papeles {
  total: number;
  presentados: number;
  faltan: number;
}
interface Requisito {
  id: string;
  grupo: string;
  grupo_texto: string;
  codigo: string | null;
  texto: string;
  estado: string;
  fecha_presentado: string | null;
  observaciones: string | null;
  propio: boolean;
}
interface Pago {
  id: string;
  subsidio_id: string;
  periodo: string;
  periodo_texto: string;
  monto: number | null;
  estado: string;
  fecha_pago: string | null;
  comprobante: string | null;
  observaciones: string | null;
  papeles?: Papeles;
  requisitos?: Requisito[];
  subsidio?: { id: string; tipo: string; prestador: string | null; recurso_id: string | null };
  persona?: { id: string; numero_legajo: string; nombre: string };
}
interface Subsidio {
  id: string;
  persona_id: string;
  tipo: string;
  tipo_texto: string;
  estado: string;
  recurso_id: string | null;
  prestador: string | null;
  prestador_texto: string | null;
  solicitante_nombre: string | null;
  solicitante_dni: string | null;
  solicitante_vinculo: string | null;
  solicitante_telefono: string | null;
  horas_semanales: number | null;
  detalle: string | null;
  monto_mensual: number | null;
  fecha_solicitud: string | null;
  fecha_elevacion: string | null;
  resolucion_numero: string | null;
  resolucion_fecha: string | null;
  desde: string | null;
  hasta: string | null;
  observaciones: string | null;
  mensual: boolean;
  papeles?: Papeles;
  persona?: { id: string; numero_legajo: string; nombre: string };
}
interface Detalle extends Subsidio {
  requisitos: Requisito[];
  pagos: Pago[];
  total_pagado: number;
}

const CLASE_ESTADO: Record<string, string> = {
  en_tramite: "marca-alerta",
  elevado: "marca-info",
  aprobado: "marca-info",
  rechazado: "marca-grave",
  suspendido: "marca-alerta",
  finalizado: "marca-info",
  pendiente: "marca-alerta",
  documentacion_completa: "marca-info",
  en_liquidacion: "marca-info",
  pagado: "marca-info",
  observado: "marca-grave",
};

function useCatalogo() {
  return useDatos(() => api.get<CatalogoSubsidios>("/subsidios/catalogo"), []);
}

function textoDe(lista: Opcion[], codigo: string): string {
  return lista.find((x) => x.codigo === codigo)?.texto ?? codigo;
}

function Marca({ lista, codigo }: { lista: Opcion[]; codigo: string }) {
  return <span className={`marca ${CLASE_ESTADO[codigo] ?? "marca-info"}`}>{textoDe(lista, codigo).replace(/ \(.*\)$/, "")}</span>;
}

function pesos(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 2 });
}

function hoyIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function mesActual() {
  return hoyIso().slice(0, 7);
}

function Avance({ p }: { p?: Papeles }) {
  if (!p) return null;
  return (
    <span className={p.faltan === 0 ? "" : "tenue"}>
      {p.presentados}/{p.total} papeles
    </span>
  );
}

// ---------------------------------------------------------------- sección del legajo

export function SeccionSubsidios({ personaId }: { personaId: string }) {
  const { puede } = useSesion();
  const cat = useCatalogo();
  const lista = useDatos(() => api.get<Subsidio[]>(`/personas/${personaId}/subsidios`), [personaId]);
  const [nuevo, setNuevo] = useState(false);
  if (!puede("subsidios", "consultar")) return null;
  if (cat.error || lista.error) return <Aviso error={cat.error ?? lista.error} />;
  if (!cat.datos || !lista.datos) return <Cargando />;
  const c = cat.datos;
  return (
    <Seccion
      id="s-subsidios"
      titulo="Subsidios"
      acciones={
        c.puede.crear && (
          <button className="boton" onClick={() => setNuevo(true)}>
            Nuevo subsidio
          </button>
        )
      }
    >
      {lista.datos.length === 0 ? (
        <Vacio>No tiene subsidios registrados.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Subsidio</th>
              <th>Estado</th>
              <th>Vigencia</th>
              <th>Papeles</th>
            </tr>
          </thead>
          <tbody>
            {lista.datos.map((s) => (
              <tr key={s.id}>
                <td>
                  <Enlace a={`/subsidios/${s.id}`}>{s.tipo_texto}</Enlace>
                  {s.prestador && <div className="tenue">{s.prestador}</div>}
                </td>
                <td>
                  <Marca lista={c.estados} codigo={s.estado} />
                </td>
                <td>{s.desde ? `${fecha(s.desde)} → ${s.hasta ? fecha(s.hasta) : "vigente"}` : "—"}</td>
                <td>{s.estado === "en_tramite" || s.estado === "elevado" ? <Avance p={s.papeles} /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {nuevo && (
        <Modal titulo="Nuevo subsidio" alCerrar={() => setNuevo(false)} ancho>
          <FormSubsidio personaId={personaId} cat={c} alGuardar={(s) => (location.hash = `#/subsidios/${s.id}`)} />
        </Modal>
      )}
    </Seccion>
  );
}

function SelectorPrestador({ tipo, recurso, setRecurso }: { tipo: string; recurso: { id: string; nombre: string } | null; setRecurso: (r: { id: string; nombre: string } | null) => void }) {
  const [q, setQ] = useState("");
  const tipoRecurso = tipo === "residencia" ? "residencia" : "cuidador";
  const resultados = useDatos(
    () => (q.trim().length >= 2 && !recurso ? api.get<{ id: string; nombre: string; localidad: string | null }[]>("/recursos", { tipo: tipoRecurso, q }) : Promise.resolve([])),
    [q, recurso, tipoRecurso],
  );
  return (
    <div className="campo">
      <span className="campo-etiqueta">{tipo === "residencia" ? "Residencia (del mapa de recursos)" : "Cuidador/a (del mapa de recursos)"}</span>
      {recurso ? (
        <div className="fila-botones">
          <strong>{recurso.nombre}</strong>
          <button type="button" className="boton boton-chico" onClick={() => setRecurso(null)}>
            Cambiar
          </button>
        </div>
      ) : (
        <>
          <input type="search" value={q} onChange={(e) => setQ(valor(e))} placeholder="Buscar por nombre" aria-label="Buscar en el mapa de recursos" />
          {(resultados.datos ?? []).map((r) => (
            <button type="button" key={r.id} className="boton boton-chico" onClick={() => setRecurso({ id: r.id, nombre: r.nombre })}>
              {r.nombre}
              {r.localidad ? ` · ${r.localidad}` : ""}
            </button>
          ))}
        </>
      )}
    </div>
  );
}

function FormSubsidio({ personaId, cat, alGuardar }: { personaId: string; cat: CatalogoSubsidios; alGuardar: (s: Subsidio) => void }) {
  const [tipo, setTipo] = useState("residencia");
  const [recurso, setRecurso] = useState<{ id: string; nombre: string } | null>(null);
  const [prestador, setPrestador] = useState("");
  const [sol, setSol] = useState({ nombre: "", dni: "", vinculo: "", telefono: "" });
  const [horas, setHoras] = useState("");
  const [detalle, setDetalle] = useState("");
  const [monto, setMonto] = useState("");
  const [fechaSol, setFechaSol] = useState(hoyIso());
  const [obs, setObs] = useState("");
  const envio = useEnvio();
  const conPrestador = tipo === "residencia" || tipo === "cuidados";
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = await envio.ejecutar(() =>
      api.post<Subsidio>(`/personas/${personaId}/subsidios`, {
        tipo,
        recurso_id: conPrestador ? recurso?.id ?? null : null,
        prestador_texto: conPrestador && !recurso ? prestador || null : null,
        solicitante_nombre: sol.nombre || null,
        solicitante_dni: sol.dni || null,
        solicitante_vinculo: sol.vinculo || null,
        solicitante_telefono: sol.telefono || null,
        horas_semanales: tipo === "cuidados" && horas ? Number(horas.replace(",", ".")) : null,
        detalle: detalle || null,
        monto_mensual: monto ? monto.replace(",", ".") : null,
        fecha_solicitud: fechaSol || null,
        observaciones: obs || null,
      }),
    );
    if (s) alGuardar(s);
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <Campo etiqueta="Tipo de subsidio">
        <select value={tipo} onChange={(e) => { setTipo(valor(e)); setRecurso(null); }}>
          {cat.tipos.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.texto}
            </option>
          ))}
        </select>
      </Campo>
      {conPrestador && (
        <>
          <SelectorPrestador tipo={tipo} recurso={recurso} setRecurso={setRecurso} />
          {!recurso && (
            <Campo etiqueta="O escriba el nombre" ayuda="Si todavía no está cargado en el mapa de recursos.">
              <input value={prestador} onChange={(e) => setPrestador(valor(e))} maxLength={300} />
            </Campo>
          )}
        </>
      )}
      {tipo === "cuidados" && (
        <Campo etiqueta="Horas de cuidado por semana">
          <input inputMode="decimal" value={horas} onChange={(e) => setHoras(valor(e))} placeholder="Por ejemplo 20" />
        </Campo>
      )}
      {!conPrestador && (
        <Campo etiqueta="Qué se solicita">
          <textarea value={detalle} onChange={(e) => setDetalle(valor(e))} rows={2} maxLength={3000} />
        </Campo>
      )}
      <fieldset className="campo">
        <legend className="campo-etiqueta">Solicitante (si no es la misma persona)</legend>
        <div className="formulario">
          <Campo etiqueta="Nombre y apellido">
            <input value={sol.nombre} onChange={(e) => setSol({ ...sol, nombre: valor(e) })} maxLength={200} />
          </Campo>
          <Campo etiqueta="DNI">
            <input value={sol.dni} onChange={(e) => setSol({ ...sol, dni: valor(e) })} maxLength={20} />
          </Campo>
          <Campo etiqueta="Vínculo">
            <input value={sol.vinculo} onChange={(e) => setSol({ ...sol, vinculo: valor(e) })} maxLength={100} placeholder="Hija, hijo, cónyuge…" />
          </Campo>
          <Campo etiqueta="Teléfono">
            <input value={sol.telefono} onChange={(e) => setSol({ ...sol, telefono: valor(e) })} maxLength={100} />
          </Campo>
        </div>
      </fieldset>
      <Campo etiqueta="Monto mensual previsto (opcional)">
        <input inputMode="decimal" value={monto} onChange={(e) => setMonto(valor(e))} placeholder="Por ejemplo 450000" />
      </Campo>
      <Campo etiqueta="Fecha de la solicitud">
        <input type="date" value={fechaSol} max={hoyIso()} onChange={(e) => setFechaSol(valor(e))} />
      </Campo>
      <Campo etiqueta="Observaciones">
        <textarea value={obs} onChange={(e) => setObs(valor(e))} rows={2} maxLength={3000} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Crear y ver los papeles
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- lista de papeles

function ListaPapeles({ items, puedeMarcar, alCambiar, pagoId, subsidioId }: { items: Requisito[]; puedeMarcar: boolean; alCambiar: () => void; pagoId?: string; subsidioId: string }) {
  const cat = useCatalogo();
  const envio = useEnvio();
  const [nuevo, setNuevo] = useState("");
  const grupos: { grupo: string; texto: string; items: Requisito[] }[] = [];
  for (const r of items) {
    let g = grupos.find((x) => x.grupo === r.grupo);
    if (!g) grupos.push((g = { grupo: r.grupo, texto: r.grupo_texto, items: [] }));
    g.items.push(r);
  }
  const marcar = async (r: Requisito, cambios: Record<string, unknown>) => {
    await envio.ejecutar(() => api.patch(`/subsidios/requisitos/${r.id}`, cambios));
    alCambiar();
  };
  const agregar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (nuevo.trim().length < 3) return;
    const ok = await envio.ejecutar(() => api.post(`/subsidios/${subsidioId}/requisitos`, { texto: nuevo, grupo: "otros", pago_id: pagoId ?? null }));
    if (ok) {
      setNuevo("");
      alCambiar();
    }
  };
  const quitar = async (r: Requisito) => {
    await envio.ejecutar(() => api.delete(`/subsidios/requisitos/${r.id}`));
    alCambiar();
  };
  return (
    <div className="papeles">
      {envio.error ? <Aviso error={envio.error} /> : null}
      {grupos.length === 0 && <Vacio>Este subsidio no tiene una lista de papeles definida. Agregue los que se pidan.</Vacio>}
      {grupos.map((g) => (
        <div key={g.grupo}>
          <h3>{g.texto}</h3>
          <table className="tabla">
            <tbody>
              {g.items.map((r) => (
                <tr key={r.id} className={r.estado === "no_corresponde" ? "fila-inactiva" : ""}>
                  <td style={{ width: "55%" }}>
                    {r.texto}
                    {r.observaciones && <div className="tenue">{r.observaciones}</div>}
                  </td>
                  <td>
                    {puedeMarcar && cat.datos ? (
                      <select value={r.estado} onChange={(e) => marcar(r, { estado: valor(e) })} aria-label={`Estado de: ${r.texto}`}>
                        {cat.datos.estados_requisito.map((x) => (
                          <option key={x.codigo} value={x.codigo}>
                            {x.texto}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className={`marca ${r.estado === "presentado" ? "marca-info" : "marca-alerta"}`}>{r.estado === "presentado" ? "Presentado" : r.estado === "no_corresponde" ? "No corresponde" : "Falta"}</span>
                    )}
                  </td>
                  <td>{r.fecha_presentado ? fecha(r.fecha_presentado) : ""}</td>
                  <td>
                    {puedeMarcar && r.propio && (
                      <button className="boton boton-chico" onClick={() => quitar(r)}>
                        Quitar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {puedeMarcar && (
        <form onSubmit={agregar} className="fila-botones">
          <input value={nuevo} onChange={(e) => setNuevo(valor(e))} placeholder="Agregar otro papel que se pida" aria-label="Agregar otro papel" maxLength={500} style={{ flex: 1 }} />
          <button className="boton boton-chico" disabled={envio.enviando || nuevo.trim().length < 3}>
            Agregar
          </button>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- detalle de un subsidio

export function PaginaSubsidio({ id }: { id: string }) {
  const cat = useCatalogo();
  const det = useDatos(() => api.get<Detalle>(`/subsidios/${id}`), [id]);
  const [dialogo, setDialogo] = useState<"datos" | "resolver" | "mes" | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  if (cat.error || det.error) return <Aviso error={cat.error ?? det.error} />;
  if (!cat.datos || !det.datos) return <Cargando />;
  const c = cat.datos;
  const s = det.datos;
  const puedeModificar = !!c.puede.modificar;
  const cerrar = () => setDialogo(null);
  const listo = () => {
    cerrar();
    det.recargar();
  };
  const fila = (t: string, v: string | number | null | undefined) =>
    v !== null && v !== undefined && v !== "" ? (
      <>
        <dt>{t}</dt>
        <dd>{v}</dd>
      </>
    ) : null;
  return (
    <>
      <div className="inicio-cabecera">
        <h1>
          Subsidio: {s.tipo_texto} <Marca lista={c.estados} codigo={s.estado} />
        </h1>
        <div className="fila-botones">
          <Enlace a={`/legajos/${s.persona_id}`} className="boton">
            Ir al legajo
          </Enlace>
          <Enlace a="/subsidios" className="boton">
            Todos los subsidios
          </Enlace>
        </div>
      </div>
      <p className="tenue">
        {s.persona?.nombre} · Legajo {s.persona?.numero_legajo}
      </p>

      <Seccion
        titulo="Datos"
        acciones={
          <>
            {puedeModificar && (
              <button className="boton boton-chico" onClick={() => setDialogo("datos")}>
                Editar datos
              </button>
            )}
            {c.puede.administrar && (
              <button className="boton boton-chico boton-primario" onClick={() => setDialogo("resolver")}>
                Resolver trámite
              </button>
            )}
          </>
        }
      >
        <dl className="datos">
          {fila(s.tipo === "cuidados" ? "Cuidador/a" : s.tipo === "residencia" ? "Residencia" : "Prestador", s.prestador)}
          {fila("Solicitante", [s.solicitante_nombre, s.solicitante_vinculo && `(${s.solicitante_vinculo})`, s.solicitante_dni && `DNI ${s.solicitante_dni}`].filter(Boolean).join(" "))}
          {fila("Teléfono del solicitante", s.solicitante_telefono)}
          {s.tipo === "cuidados" && fila("Horas por semana", s.horas_semanales)}
          {fila("Qué se solicita", s.detalle)}
          {fila("Monto mensual", s.monto_mensual !== null ? pesos(s.monto_mensual) : null)}
          {fila("Fecha de la solicitud", s.fecha_solicitud ? fecha(s.fecha_solicitud) : null)}
          {fila("Elevado al Ministerio", s.fecha_elevacion ? fecha(s.fecha_elevacion) : null)}
          {fila("Resolución", s.resolucion_numero ? `${s.resolucion_numero}${s.resolucion_fecha ? ` del ${fecha(s.resolucion_fecha)}` : ""}` : null)}
          {fila("Vigencia", s.desde ? `${fecha(s.desde)} → ${s.hasta ? fecha(s.hasta) : "sin fecha de fin"}` : null)}
          {fila("Observaciones", s.observaciones)}
        </dl>
      </Seccion>

      <Seccion titulo={`Papeles del trámite (${s.papeles?.presentados ?? 0} de ${s.papeles?.total ?? 0})`}>
        <ListaPapeles items={s.requisitos} puedeMarcar={puedeModificar} alCambiar={det.recargar} subsidioId={s.id} />
      </Seccion>

      {s.mensual && (
        <Seccion
          titulo={`Pagos mensuales${s.total_pagado ? ` · pagado ${pesos(s.total_pagado)}` : ""}`}
          acciones={
            puedeModificar &&
            s.estado === "aprobado" && (
              <button className="boton boton-chico" onClick={() => setDialogo("mes")}>
                Agregar mes
              </button>
            )
          }
        >
          {s.estado !== "aprobado" ? (
            <Vacio>Los pagos se cargan cuando el subsidio está aprobado.</Vacio>
          ) : s.pagos.length === 0 ? (
            <Vacio>Todavía no hay meses cargados.</Vacio>
          ) : (
            s.pagos.map((p) => (
              <div key={p.id} className="seccion-interna">
                <div className="fila-botones" style={{ justifyContent: "space-between" }}>
                  <strong>{p.periodo_texto}</strong>
                  <span>{pesos(p.monto)}</span>
                  <Avance p={p.papeles} />
                  <Marca lista={c.estados_pago} codigo={p.estado} />
                  <button className="boton boton-chico" onClick={() => setAbierto(abierto === p.id ? null : p.id)}>
                    {abierto === p.id ? "Cerrar" : "Abrir"}
                  </button>
                </div>
                {abierto === p.id && <DetallePago pago={p} cat={c} subsidioId={s.id} puedeModificar={puedeModificar} alCambiar={det.recargar} />}
              </div>
            ))
          )}
        </Seccion>
      )}

      {dialogo === "datos" && (
        <Modal titulo="Editar datos" alCerrar={cerrar} ancho>
          <FormDatos s={s} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "resolver" && (
        <Modal titulo="Resolver trámite" alCerrar={cerrar}>
          <FormResolver s={s} cat={c} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "mes" && (
        <Modal titulo="Agregar mes" alCerrar={cerrar}>
          <FormMes s={s} alGuardar={listo} />
        </Modal>
      )}
    </>
  );
}

function FormDatos({ s, alGuardar }: { s: Subsidio; alGuardar: () => void }) {
  const [d, setD] = useState({
    prestador_texto: s.prestador_texto ?? "",
    solicitante_nombre: s.solicitante_nombre ?? "",
    solicitante_dni: s.solicitante_dni ?? "",
    solicitante_vinculo: s.solicitante_vinculo ?? "",
    solicitante_telefono: s.solicitante_telefono ?? "",
    horas_semanales: s.horas_semanales?.toString() ?? "",
    detalle: s.detalle ?? "",
    monto_mensual: s.monto_mensual?.toString() ?? "",
    observaciones: s.observaciones ?? "",
  });
  const envio = useEnvio();
  const set = (c: Partial<typeof d>) => setD({ ...d, ...c });
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const cuerpo: Record<string, unknown> = {
      solicitante_nombre: d.solicitante_nombre || null,
      solicitante_dni: d.solicitante_dni || null,
      solicitante_vinculo: d.solicitante_vinculo || null,
      solicitante_telefono: d.solicitante_telefono || null,
      detalle: d.detalle || null,
      observaciones: d.observaciones || null,
    };
    if (!s.recurso_id) cuerpo.prestador_texto = d.prestador_texto || null;
    if (s.tipo === "cuidados") cuerpo.horas_semanales = d.horas_semanales ? Number(d.horas_semanales.replace(",", ".")) : null;
    if (d.monto_mensual !== (s.monto_mensual?.toString() ?? "")) cuerpo.monto_mensual = d.monto_mensual ? d.monto_mensual.replace(",", ".") : null;
    if (await envio.ejecutar(() => api.patch(`/subsidios/${s.id}`, cuerpo))) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      {!s.recurso_id && (s.tipo === "residencia" || s.tipo === "cuidados") && (
        <Campo etiqueta="Prestador">
          <input value={d.prestador_texto} onChange={(e) => set({ prestador_texto: valor(e) })} />
        </Campo>
      )}
      <Campo etiqueta="Solicitante">
        <input value={d.solicitante_nombre} onChange={(e) => set({ solicitante_nombre: valor(e) })} />
      </Campo>
      <Campo etiqueta="DNI del solicitante">
        <input value={d.solicitante_dni} onChange={(e) => set({ solicitante_dni: valor(e) })} />
      </Campo>
      <Campo etiqueta="Vínculo">
        <input value={d.solicitante_vinculo} onChange={(e) => set({ solicitante_vinculo: valor(e) })} />
      </Campo>
      <Campo etiqueta="Teléfono">
        <input value={d.solicitante_telefono} onChange={(e) => set({ solicitante_telefono: valor(e) })} />
      </Campo>
      {s.tipo === "cuidados" && (
        <Campo etiqueta="Horas por semana">
          <input inputMode="decimal" value={d.horas_semanales} onChange={(e) => set({ horas_semanales: valor(e) })} />
        </Campo>
      )}
      <Campo etiqueta="Qué se solicita">
        <textarea value={d.detalle} onChange={(e) => set({ detalle: valor(e) })} rows={2} />
      </Campo>
      <Campo etiqueta="Monto mensual">
        <input inputMode="decimal" value={d.monto_mensual} onChange={(e) => set({ monto_mensual: valor(e) })} />
      </Campo>
      <Campo etiqueta="Observaciones">
        <textarea value={d.observaciones} onChange={(e) => set({ observaciones: valor(e) })} rows={3} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

function FormResolver({ s, cat, alGuardar }: { s: Subsidio; cat: CatalogoSubsidios; alGuardar: () => void }) {
  const [estado, setEstado] = useState(s.estado);
  const [resNum, setResNum] = useState(s.resolucion_numero ?? "");
  const [resFecha, setResFecha] = useState(s.resolucion_fecha ?? "");
  const [desde, setDesde] = useState(s.desde ?? "");
  const [hasta, setHasta] = useState(s.hasta ?? "");
  const envio = useEnvio();
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await envio.ejecutar(() =>
      api.patch(`/subsidios/${s.id}`, { estado, resolucion_numero: resNum || null, resolucion_fecha: resFecha || null, desde: desde || null, hasta: hasta || null }),
    );
    if (ok) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <Campo etiqueta="Estado del trámite">
        <select value={estado} onChange={(e) => setEstado(valor(e))}>
          {cat.estados.map((x) => (
            <option key={x.codigo} value={x.codigo}>
              {x.texto}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta="Número de resolución" ayuda="Obligatorio para aprobar.">
        <input value={resNum} onChange={(e) => setResNum(valor(e))} maxLength={100} />
      </Campo>
      <Campo etiqueta="Fecha de la resolución">
        <input type="date" value={resFecha} onChange={(e) => setResFecha(valor(e))} />
      </Campo>
      <Campo etiqueta="Rige desde" ayuda="Obligatorio para aprobar.">
        <input type="date" value={desde} onChange={(e) => setDesde(valor(e))} />
      </Campo>
      <Campo etiqueta="Rige hasta" ayuda="Se completa solo al finalizar.">
        <input type="date" value={hasta} min={desde || undefined} onChange={(e) => setHasta(valor(e))} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

function FormMes({ s, alGuardar }: { s: Subsidio; alGuardar: () => void }) {
  const [mes, setMes] = useState(mesActual());
  const [monto, setMonto] = useState(s.monto_mensual?.toString() ?? "");
  const envio = useEnvio();
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await envio.ejecutar(() => api.post(`/subsidios/${s.id}/pagos`, { periodo: `${mes}-01`, monto: monto ? monto.replace(",", ".") : null }));
    if (ok) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <Campo etiqueta="Mes">
        <input type="month" value={mes} onChange={(e) => setMes(valor(e))} required />
      </Campo>
      <Campo etiqueta="Monto del mes">
        <input inputMode="decimal" value={monto} onChange={(e) => setMonto(valor(e))} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Agregar
        </button>
      </div>
    </form>
  );
}

function DetallePago({ pago, cat, subsidioId, puedeModificar, alCambiar }: { pago: Pago; cat: CatalogoSubsidios; subsidioId: string; puedeModificar: boolean; alCambiar: () => void }) {
  const [estado, setEstado] = useState(pago.estado);
  const [monto, setMonto] = useState(pago.monto?.toString() ?? "");
  const [fechaPago, setFechaPago] = useState(pago.fecha_pago ?? "");
  const [comprobante, setComprobante] = useState(pago.comprobante ?? "");
  const [obs, setObs] = useState(pago.observaciones ?? "");
  const [pideForzar, setPideForzar] = useState<string | null>(null);
  const envio = useEnvio();
  const reservados = ["en_liquidacion", "pagado"];
  const guardar = async (forzar = false) => {
    setPideForzar(null);
    try {
      await api.patch(`/subsidios/pagos/${pago.id}`, {
        estado,
        monto: monto ? monto.replace(",", ".") : null,
        fecha_pago: fechaPago || null,
        comprobante: comprobante || null,
        observaciones: obs || null,
        forzar,
      });
      alCambiar();
    } catch (e: any) {
      if (e?.status === 409 && e.detalle?.faltan) setPideForzar(e.detalle.mensaje);
      else envio.setError(e);
    }
  };
  const quitar = async () => {
    if (!window.confirm(`¿Eliminar el mes ${pago.periodo_texto}?`)) return;
    await envio.ejecutar(() => api.delete(`/subsidios/pagos/${pago.id}`));
    alCambiar();
  };
  return (
    <div style={{ marginTop: "0.75rem" }}>
      <h3>Papeles del mes</h3>
      <ListaPapeles items={pago.requisitos ?? []} puedeMarcar={puedeModificar} alCambiar={alCambiar} pagoId={pago.id} subsidioId={subsidioId} />
      <h3>Liquidación y pago</h3>
      {envio.error ? <Aviso error={envio.error} /> : null}
      {pideForzar && (
        <div className="aviso aviso-info">
          {pideForzar}{" "}
          <button className="boton boton-chico" onClick={() => guardar(true)}>
            Liquidar igual
          </button>
        </div>
      )}
      {puedeModificar ? (
        <form
          className="formulario"
          onSubmit={(e) => {
            e.preventDefault();
            guardar();
          }}
        >
          <Campo etiqueta="Estado">
            <select value={estado} onChange={(e) => setEstado(valor(e))}>
              {cat.estados_pago
                .filter((x) => cat.puede.administrar || !reservados.includes(x.codigo) || x.codigo === pago.estado)
                .map((x) => (
                  <option key={x.codigo} value={x.codigo}>
                    {x.texto}
                  </option>
                ))}
            </select>
          </Campo>
          <Campo etiqueta="Monto">
            <input inputMode="decimal" value={monto} onChange={(e) => setMonto(valor(e))} />
          </Campo>
          <Campo etiqueta="Fecha de pago">
            <input type="date" value={fechaPago} onChange={(e) => setFechaPago(valor(e))} />
          </Campo>
          <Campo etiqueta="Comprobante u orden de pago">
            <input value={comprobante} onChange={(e) => setComprobante(valor(e))} maxLength={100} />
          </Campo>
          <Campo etiqueta="Observaciones">
            <textarea value={obs} onChange={(e) => setObs(valor(e))} rows={2} />
          </Campo>
          <div className="fila-botones">
            <button className="boton boton-primario" disabled={envio.enviando}>
              Guardar mes
            </button>
            {!reservados.includes(pago.estado) && (
              <button type="button" className="boton" onClick={quitar}>
                Eliminar mes
              </button>
            )}
          </div>
        </form>
      ) : (
        <p>
          {pesos(pago.monto)} · {pago.fecha_pago ? `pagado el ${fecha(pago.fecha_pago)}` : "sin pagar"} {pago.comprobante && `· ${pago.comprobante}`}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- panel de subsidios y pagos del mes

export function PaginaSubsidios() {
  const [vista, setVista] = useState<"tramites" | "mes">("tramites");
  return (
    <>
      <h1>Subsidios</h1>
      <div className="segmentado" role="tablist" aria-label="Vista">
        <button role="tab" aria-selected={vista === "tramites"} className={vista === "tramites" ? "activo" : ""} onClick={() => setVista("tramites")}>
          Trámites
        </button>
        <button role="tab" aria-selected={vista === "mes"} className={vista === "mes" ? "activo" : ""} onClick={() => setVista("mes")}>
          Pagos del mes
        </button>
      </div>
      {vista === "tramites" ? <Tramites /> : <PagosDelMes />}
    </>
  );
}

function Tramites() {
  const cat = useCatalogo();
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("");
  const [q, setQ] = useState("");
  const lista = useDatos(() => api.get<{ items: Subsidio[]; por_estado: Record<string, { cantidad: number; monto_mensual: number }> }>("/subsidios", { tipo, estado, q }), [tipo, estado, q]);
  if (cat.error || lista.error) return <Aviso error={cat.error ?? lista.error} />;
  if (!cat.datos || !lista.datos) return <Cargando />;
  const c = cat.datos;
  const pe = lista.datos.por_estado;
  const n = (e: string) => pe[e]?.cantidad ?? 0;
  return (
    <>
      <div className="indicadores">
        <Cifra valor={n("en_tramite") + n("elevado")} texto="en trámite" />
        <Cifra valor={n("aprobado")} texto="aprobados" />
        <Cifra valor={pesos(pe.aprobado?.monto_mensual ?? 0)} texto="por mes en subsidios aprobados" />
        <Cifra valor={n("rechazado") + n("suspendido")} texto="rechazados o suspendidos" />
      </div>
      <div className="fila-botones" style={{ margin: "0.75rem 0" }}>
        <input type="search" value={q} onChange={(e) => setQ(valor(e))} placeholder="Apellido, legajo o N° de resolución" aria-label="Buscar subsidio" />
        <select value={tipo} onChange={(e) => setTipo(valor(e))} aria-label="Tipo">
          <option value="">Todos los tipos</option>
          {c.tipos.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.texto}
            </option>
          ))}
        </select>
        <select value={estado} onChange={(e) => setEstado(valor(e))} aria-label="Estado">
          <option value="">Todos los estados</option>
          {c.estados.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.texto}
            </option>
          ))}
        </select>
      </div>
      {lista.datos.items.length === 0 ? (
        <Vacio>No hay subsidios con esos filtros. Se crean desde el legajo de la persona.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Persona</th>
              <th>Subsidio</th>
              <th>Estado</th>
              <th>Resolución</th>
              <th>Monto mensual</th>
              <th>Papeles</th>
            </tr>
          </thead>
          <tbody>
            {lista.datos.items.map((s) => (
              <tr key={s.id}>
                <td>
                  <Enlace a={`/subsidios/${s.id}`}>{s.persona?.nombre}</Enlace>
                  <div className="tenue">Legajo {s.persona?.numero_legajo}</div>
                </td>
                <td>
                  {s.tipo_texto}
                  {s.prestador && <div className="tenue">{s.prestador}</div>}
                </td>
                <td>
                  <Marca lista={c.estados} codigo={s.estado} />
                </td>
                <td>{s.resolucion_numero ?? "—"}</td>
                <td>{pesos(s.monto_mensual)}</td>
                <td>{s.estado === "en_tramite" || s.estado === "elevado" ? <Avance p={s.papeles} /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Cifra({ valor, texto }: { valor: number | string; texto: string }) {
  return (
    <div className="indicador">
      <span className="indicador-valor">{valor}</span>
      <span className="indicador-texto">{texto}</span>
    </div>
  );
}

function PagosDelMes() {
  const cat = useCatalogo();
  const [periodo, setPeriodo] = useState(mesActual());
  const [estado, setEstado] = useState("");
  const datos = useDatos(
    () => api.get<{ periodo: string; items: Pago[]; por_estado: Record<string, { cantidad: number; monto: number }>; total: number }>("/subsidios-pagos", { periodo, estado }),
    [periodo, estado],
  );
  const envio = useEnvio();
  const [aviso, setAviso] = useState<string | null>(null);
  if (cat.error || datos.error) return <Aviso error={cat.error ?? datos.error} />;
  if (!cat.datos || !datos.datos) return <Cargando />;
  const c = cat.datos;
  const generar = async () => {
    const r = await envio.ejecutar(() => api.post<{ creados: number }>("/subsidios/pagos/generar", { periodo: `${periodo}-01` }));
    if (r) {
      setAviso(r.creados ? `Se crearon ${r.creados} mes${r.creados === 1 ? "" : "es"} de subsidios aprobados.` : "No había subsidios aprobados sin su mes cargado.");
      datos.recargar();
    }
  };
  const d = datos.datos;
  return (
    <>
      <div className="fila-botones" style={{ margin: "0.75rem 0" }}>
        <label>
          Mes <input type="month" value={periodo} onChange={(e) => setPeriodo(valor(e))} />
        </label>
        <select value={estado} onChange={(e) => setEstado(valor(e))} aria-label="Estado del pago">
          <option value="">Todos los estados</option>
          {c.estados_pago.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.texto}
            </option>
          ))}
        </select>
        {c.puede.administrar && (
          <button className="boton" onClick={generar} disabled={envio.enviando}>
            Generar los pagos de este mes
          </button>
        )}
      </div>
      {envio.error ? <Aviso error={envio.error} /> : null}
      {aviso && <Aviso error={aviso} tipo="info" />}
      <div className="indicadores">
        <Cifra valor={d.items.length} texto="subsidios en el mes" />
        <Cifra valor={pesos(d.total)} texto="total del mes" />
        {c.estados_pago.map((e) => (
          <Cifra key={e.codigo} valor={d.por_estado[e.codigo]?.cantidad ?? 0} texto={e.texto.toLowerCase()} />
        ))}
      </div>
      {d.items.length === 0 ? (
        <Vacio>No hay pagos cargados en {periodo}.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Persona</th>
              <th>Subsidio</th>
              <th>Monto</th>
              <th>Papeles</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {d.items.map((p) => (
              <tr key={p.id}>
                <td>
                  <Enlace a={`/subsidios/${p.subsidio_id}`}>{p.persona?.nombre}</Enlace>
                </td>
                <td>
                  {textoDe(c.tipos, p.subsidio?.tipo ?? "")}
                  {p.subsidio?.prestador && <div className="tenue">{p.subsidio.prestador}</div>}
                </td>
                <td>{pesos(p.monto)}</td>
                <td>
                  <Avance p={p.papeles} />
                </td>
                <td>
                  <Marca lista={c.estados_pago} codigo={p.estado} />
                  {p.fecha_pago && <div className="tenue">{fecha(p.fecha_pago)}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

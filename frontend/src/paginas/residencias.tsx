// Residencias de larga estadía: documentación de cada una (habilitación, fiscalización…) y personas internadas.

import { useState } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Enlace, Modal, Seccion, Vacio, fecha, useDatos, useEnvio, useSesion, valor } from "../comun";

interface TipoDoc {
  codigo: string;
  texto: string;
  obligatorio: boolean;
}
interface CatalogoResidencias {
  tipos_documento: TipoDoc[];
  modalidades: { codigo: string; texto: string }[];
  motivos_egreso: { codigo: string; texto: string }[];
  dias_por_vencer: number;
  puede: { crear: boolean; modificar: string | null };
}
interface DocumentoRecurso {
  id: string;
  tipo: string;
  numero: string | null;
  fecha_emision: string | null;
  vence: string | null;
  estado: string;
  observaciones: string | null;
  tiene_archivo: boolean;
  nombre_archivo: string | null;
}
interface ResumenDoc {
  tipo: string;
  texto: string;
  estado: string;
  vence: string | null;
}
interface Internacion {
  id: string;
  persona_id: string;
  recurso_id: string | null;
  lugar: string | null;
  lugar_texto: string | null;
  modalidad: string;
  desde: string;
  hasta: string | null;
  vigente: boolean;
  dias: number;
  motivo_egreso: string | null;
  observaciones: string | null;
  persona?: { id: string; numero_legajo: string; nombre: string };
}

const TEXTO_ESTADO: Record<string, string> = {
  vigente: "Vigente",
  por_vencer: "Por vencer",
  vencido: "Vencido",
  sin_fecha: "Sin fecha",
  falta: "Falta",
};
const CLASE_ESTADO: Record<string, string> = {
  vigente: "marca-info",
  por_vencer: "marca-alerta",
  vencido: "marca-grave",
  sin_fecha: "marca-alerta",
  falta: "marca-grave",
};

export function MarcaEstado({ estado, vence }: { estado: string; vence?: string | null }) {
  return (
    <span className={`marca ${CLASE_ESTADO[estado] ?? "marca-info"}`}>
      {TEXTO_ESTADO[estado] ?? estado}
      {vence && estado !== "falta" ? ` · ${fecha(vence)}` : ""}
    </span>
  );
}

function useCatalogoResidencias() {
  return useDatos(() => api.get<CatalogoResidencias>("/residencias/catalogo"), []);
}

function duracion(dias: number): string {
  if (dias < 31) return `${dias} día${dias === 1 ? "" : "s"}`;
  const m = Math.floor(dias / 30.4);
  if (m < 24) return `${m} mes${m === 1 ? "" : "es"}`;
  return `${(dias / 365.25).toFixed(1).replace(".", ",")} años`;
}

function hoyIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- documentación de una residencia (ficha del recurso)

export function DocumentacionDelRecurso({ recursoId, nombre }: { recursoId: string; nombre: string }) {
  const { puede } = useSesion();
  const cat = useCatalogoResidencias();
  const lista = useDatos(() => api.get<{ documentos: DocumentoRecurso[]; resumen: ResumenDoc[] }>(`/recursos/${recursoId}/documentacion`), [recursoId]);
  const [editar, setEditar] = useState<DocumentoRecurso | "nuevo" | null>(null);
  const envio = useEnvio();
  if (!puede("residencias", "consultar")) return null;
  if (cat.error || lista.error) return <Aviso error={cat.error ?? lista.error} />;
  if (!cat.datos || !lista.datos) return <Cargando />;
  const c = cat.datos;
  const texto = (t: string) => c.tipos_documento.find((x) => x.codigo === t)?.texto ?? t;
  const puedeCrear = c.puede.crear;
  const puedeModificar = !!c.puede.modificar;

  const adjuntar = async (d: DocumentoRecurso, f: File | null) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("archivo", f);
    await envio.ejecutar(() => api.post(`/recursos/documentacion/${d.id}/archivo`, fd));
    lista.recargar();
  };
  const quitar = async (d: DocumentoRecurso) => {
    if (!window.confirm(`¿Quitar «${texto(d.tipo)}»? Queda registrado en la auditoría.`)) return;
    await envio.ejecutar(() => api.delete(`/recursos/documentacion/${d.id}`));
    lista.recargar();
  };

  return (
    <Seccion
      titulo="Documentación"
      acciones={
        puedeCrear && (
          <button className="boton boton-chico" onClick={() => setEditar("nuevo")}>
            Agregar documento
          </button>
        )
      }
    >
      {lista.datos.resumen.length > 0 && (
        <div className="fila-botones" style={{ marginBottom: "0.75rem" }}>
          {lista.datos.resumen.map((r) => (
            <span key={r.tipo}>
              <strong>{r.texto}:</strong> <MarcaEstado estado={r.estado} vence={r.vence} />
            </span>
          ))}
        </div>
      )}
      {envio.error ? <Aviso error={envio.error} /> : null}
      {lista.datos.documentos.length === 0 ? (
        <Vacio>No hay documentación registrada de {nombre}.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Número</th>
              <th>Emisión</th>
              <th>Vencimiento</th>
              <th>Archivo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lista.datos.documentos.map((d) => (
              <tr key={d.id}>
                <td>
                  {texto(d.tipo)}
                  {d.observaciones && <div className="tenue">{d.observaciones}</div>}
                </td>
                <td>{d.numero ?? "—"}</td>
                <td>{fecha(d.fecha_emision) || "—"}</td>
                <td>{d.vence ? <MarcaEstado estado={d.estado} vence={d.vence} /> : "—"}</td>
                <td>
                  {d.tiene_archivo ? (
                    <a href={`/api/recursos/documentacion/${d.id}/archivo`} target="_blank" rel="noreferrer">
                      Ver
                    </a>
                  ) : puedeModificar ? (
                    <label className="boton boton-chico">
                      Adjuntar
                      <input type="file" accept="application/pdf,image/jpeg,image/png" hidden onChange={(e) => adjuntar(d, e.target.files?.[0] ?? null)} />
                    </label>
                  ) : (
                    <span className="tenue">Sin archivo</span>
                  )}
                </td>
                <td>
                  {puedeModificar && (
                    <>
                      <button className="boton boton-chico" onClick={() => setEditar(d)}>
                        Editar
                      </button>{" "}
                      <button className="boton boton-chico" onClick={() => quitar(d)}>
                        Quitar
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editar && (
        <Modal titulo={editar === "nuevo" ? `Documento de ${nombre}` : texto(editar.tipo)} alCerrar={() => setEditar(null)}>
          <FormDocumento
            recursoId={recursoId}
            tipos={c.tipos_documento}
            doc={editar === "nuevo" ? undefined : editar}
            alGuardar={() => {
              setEditar(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </Seccion>
  );
}

function FormDocumento({ recursoId, tipos, doc, alGuardar }: { recursoId: string; tipos: TipoDoc[]; doc?: DocumentoRecurso; alGuardar: () => void }) {
  const [tipo, setTipo] = useState(doc?.tipo ?? tipos[0]?.codigo ?? "");
  const [numero, setNumero] = useState(doc?.numero ?? "");
  const [emision, setEmision] = useState(doc?.fecha_emision ?? "");
  const [vence, setVence] = useState(doc?.vence ?? "");
  const [obs, setObs] = useState(doc?.observaciones ?? "");
  const [archivo, setArchivo] = useState<File | null>(null);
  const envio = useEnvio();

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await envio.ejecutar(async () => {
      if (doc) {
        return api.patch(`/recursos/documentacion/${doc.id}`, { tipo, numero: numero || null, fecha_emision: emision || null, vence: vence || null, observaciones: obs || null });
      }
      const fd = new FormData();
      fd.append("tipo", tipo);
      if (numero) fd.append("numero", numero);
      if (emision) fd.append("fecha_emision", emision);
      if (vence) fd.append("vence", vence);
      if (obs) fd.append("observaciones", obs);
      if (archivo) fd.append("archivo", archivo);
      return api.post(`/recursos/${recursoId}/documentacion`, fd);
    });
    if (ok) alGuardar();
  };

  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <Campo etiqueta="Documento">
        <select value={tipo} onChange={(e) => setTipo(valor(e))}>
          {tipos.map((t) => (
            <option key={t.codigo} value={t.codigo}>
              {t.texto}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta="Número o expediente">
        <input value={numero} onChange={(e) => setNumero(valor(e))} maxLength={100} />
      </Campo>
      <Campo etiqueta="Fecha de emisión">
        <input type="date" value={emision} onChange={(e) => setEmision(valor(e))} />
      </Campo>
      <Campo etiqueta="Vence" ayuda="Con la fecha de vencimiento el sistema avisa cuando está por vencer.">
        <input type="date" value={vence} onChange={(e) => setVence(valor(e))} />
      </Campo>
      <Campo etiqueta="Observaciones">
        <textarea value={obs} onChange={(e) => setObs(valor(e))} rows={2} maxLength={2000} />
      </Campo>
      {!doc && (
        <Campo etiqueta="Copia escaneada (opcional)" ayuda="PDF, JPG o PNG. Se puede adjuntar después.">
          <input type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
        </Campo>
      )}
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- personas internadas (ficha de la residencia)

export function PersonasInternadas({ recursoId }: { recursoId: string }) {
  const { puede } = useSesion();
  const lista = useDatos(() => api.get<{ items: Internacion[]; total: number; fuera_de_alcance: number }>("/internaciones", { recurso_id: recursoId }), [recursoId]);
  if (!puede("residencias", "consultar")) return null;
  if (lista.error) return <Aviso error={lista.error} />;
  if (!lista.datos) return <Cargando />;
  const { items, total, fuera_de_alcance } = lista.datos;
  return (
    <Seccion titulo={`Personas internadas (${total})`}>
      {items.length === 0 && fuera_de_alcance === 0 ? (
        <Vacio>No hay personas internadas registradas en esta residencia.</Vacio>
      ) : (
        <>
          {items.length > 0 && (
            <table className="tabla">
              <thead>
                <tr>
                  <th>Persona</th>
                  <th>Desde</th>
                  <th>Tiempo</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <Enlace a={`/legajos/${i.persona_id}`}>{i.persona?.nombre}</Enlace> <small className="tenue">Legajo {i.persona?.numero_legajo}</small>
                    </td>
                    <td>{fecha(i.desde)}</td>
                    <td>{duracion(i.dias)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {fuera_de_alcance > 0 && <p className="tenue">Hay {fuera_de_alcance} persona{fuera_de_alcance === 1 ? "" : "s"} más cuyos legajos no están dentro de su alcance.</p>}
        </>
      )}
    </Seccion>
  );
}

// ---------------------------------------------------------------- internación en el legajo

export function SeccionInternacion({ personaId }: { personaId: string }) {
  const { puede } = useSesion();
  const cat = useCatalogoResidencias();
  const lista = useDatos(() => api.get<Internacion[]>(`/personas/${personaId}/internaciones`), [personaId]);
  const [dialogo, setDialogo] = useState<"nueva" | Internacion | null>(null);
  if (!puede("residencias", "consultar")) return null;
  if (cat.error || lista.error) return <Aviso error={cat.error ?? lista.error} />;
  if (!cat.datos || !lista.datos) return <Cargando />;
  const c = cat.datos;
  const vigente = lista.datos.find((i) => i.vigente);
  const texto = (lista_: { codigo: string; texto: string }[], cod: string | null) => lista_.find((x) => x.codigo === cod)?.texto ?? cod ?? "";
  return (
    <Seccion
      id="s-internacion"
      titulo="Internación en residencia u hogar"
      acciones={
        c.puede.crear && !vigente && (
          <button className="boton" onClick={() => setDialogo("nueva")}>
            Registrar internación
          </button>
        )
      }
    >
      {lista.datos.length === 0 ? (
        <Vacio>No tiene internaciones registradas.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Lugar</th>
              <th>Desde</th>
              <th>Hasta</th>
              <th>Tiempo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lista.datos.map((i) => (
              <tr key={i.id}>
                <td>
                  {i.recurso_id ? <Enlace a={`/recursos/${i.recurso_id}`}>{i.lugar}</Enlace> : i.lugar}{" "}
                  <small className="tenue">{texto(c.modalidades, i.modalidad)}</small>
                  {i.observaciones && <div className="tenue">{i.observaciones}</div>}
                </td>
                <td>{fecha(i.desde)}</td>
                <td>{i.vigente ? <span className="marca marca-alerta">Internada</span> : `${fecha(i.hasta)} · ${texto(c.motivos_egreso, i.motivo_egreso)}`}</td>
                <td>{duracion(i.dias)}</td>
                <td>
                  {c.puede.modificar && (
                    <button className="boton boton-chico" onClick={() => setDialogo(i)}>
                      {i.vigente ? "Registrar egreso" : "Editar"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {dialogo && (
        <Modal titulo={dialogo === "nueva" ? "Registrar internación" : dialogo.vigente ? "Egreso" : "Editar internación"} alCerrar={() => setDialogo(null)}>
          {dialogo === "nueva" ? (
            <FormInternacion
              personaId={personaId}
              cat={c}
              alGuardar={() => {
                setDialogo(null);
                lista.recargar();
              }}
            />
          ) : (
            <FormEgreso
              i={dialogo}
              cat={c}
              alGuardar={() => {
                setDialogo(null);
                lista.recargar();
              }}
            />
          )}
        </Modal>
      )}
    </Seccion>
  );
}

function FormInternacion({ personaId, cat, alGuardar }: { personaId: string; cat: CatalogoResidencias; alGuardar: () => void }) {
  const [q, setQ] = useState("");
  const [recurso, setRecurso] = useState<{ id: string; nombre: string } | null>(null);
  const [lugar, setLugar] = useState("");
  const [modalidad, setModalidad] = useState("residencia");
  const [desde, setDesde] = useState(hoyIso());
  const [obs, setObs] = useState("");
  const envio = useEnvio();
  const resultados = useDatos(
    () => (q.trim().length >= 2 && !recurso ? api.get<{ id: string; nombre: string; localidad: string | null }[]>("/recursos", { tipo: "residencia", q }) : Promise.resolve([])),
    [q, recurso],
  );

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await envio.ejecutar(() =>
      api.post(`/personas/${personaId}/internaciones`, { recurso_id: recurso?.id ?? null, lugar_texto: recurso ? null : lugar, modalidad, desde, observaciones: obs || null }),
    );
    if (ok) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <div className="campo">
        <span className="campo-etiqueta">Residencia (del mapa de recursos)</span>
        {recurso ? (
          <div className="fila-botones">
            <strong>{recurso.nombre}</strong>
            <button type="button" className="boton boton-chico" onClick={() => setRecurso(null)}>
              Cambiar
            </button>
          </div>
        ) : (
          <>
            <input type="search" value={q} onChange={(e) => setQ(valor(e))} placeholder="Buscar por nombre" aria-label="Buscar residencia" />
            {(resultados.datos ?? []).map((r) => (
              <button type="button" key={r.id} className="boton boton-chico" onClick={() => setRecurso({ id: r.id, nombre: r.nombre })}>
                {r.nombre}
                {r.localidad ? ` · ${r.localidad}` : ""}
              </button>
            ))}
          </>
        )}
      </div>
      {!recurso && (
        <Campo etiqueta="O escriba el lugar" ayuda="Solo si la residencia todavía no está cargada en el mapa de recursos.">
          <input value={lugar} onChange={(e) => setLugar(valor(e))} maxLength={300} />
        </Campo>
      )}
      <Campo etiqueta="Modalidad">
        <select value={modalidad} onChange={(e) => setModalidad(valor(e))}>
          {cat.modalidades.map((m) => (
            <option key={m.codigo} value={m.codigo}>
              {m.texto}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta="Fecha de ingreso">
        <input type="date" value={desde} max={hoyIso()} onChange={(e) => setDesde(valor(e))} required />
      </Campo>
      <Campo etiqueta="Observaciones">
        <textarea value={obs} onChange={(e) => setObs(valor(e))} rows={3} maxLength={3000} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando || (!recurso && !lugar.trim())}>
          Registrar
        </button>
      </div>
    </form>
  );
}

function FormEgreso({ i, cat, alGuardar }: { i: Internacion; cat: CatalogoResidencias; alGuardar: () => void }) {
  const [hasta, setHasta] = useState(i.hasta ?? (i.vigente ? hoyIso() : ""));
  const [motivo, setMotivo] = useState(i.motivo_egreso ?? "");
  const [obs, setObs] = useState(i.observaciones ?? "");
  const envio = useEnvio();
  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await envio.ejecutar(() => api.patch(`/internaciones/${i.id}`, { hasta: hasta || null, motivo_egreso: hasta ? motivo || null : null, observaciones: obs || null }));
    if (ok) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      {envio.error ? <Aviso error={envio.error} /> : null}
      <p>
        {i.lugar} · desde {fecha(i.desde)}
      </p>
      <Campo etiqueta="Fecha de egreso" ayuda={i.vigente ? "Dejela vacía si sigue internada y solo quiere cambiar las observaciones." : undefined}>
        <input type="date" value={hasta} min={i.desde} max={hoyIso()} onChange={(e) => setHasta(valor(e))} />
      </Campo>
      {hasta && (
        <Campo etiqueta="Motivo">
          <select value={motivo} onChange={(e) => setMotivo(valor(e))} required>
            <option value="">—</option>
            {cat.motivos_egreso.map((m) => (
              <option key={m.codigo} value={m.codigo}>
                {m.texto}
              </option>
            ))}
          </select>
        </Campo>
      )}
      <Campo etiqueta="Observaciones">
        <textarea value={obs} onChange={(e) => setObs(valor(e))} rows={3} maxLength={3000} />
      </Campo>
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={envio.enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- panel

interface FilaPanel {
  id: string;
  nombre: string;
  localidad: string | null;
  departamento: string | null;
  telefono: string | null;
  internados: number;
  estados: Record<string, string>;
  estado: string;
  proximo_vencimiento: string | null;
}

function Cifra({ valor, texto, alerta }: { valor: number; texto: string; alerta?: boolean }) {
  return (
    <div className={`indicador ${alerta && valor > 0 ? "indicador-alerta" : ""}`}>
      <span className="indicador-valor">{valor}</span>
      <span className="indicador-texto">{texto}</span>
    </div>
  );
}

export function PaginaResidencias() {
  const panel = useDatos(
    () =>
      api.get<{
        resumen: { residencias: number; internados: number; con_documentos_vencidos: number; con_documentos_por_vencer: number; con_documentos_faltantes: number };
        tipos: TipoDoc[];
        items: FilaPanel[];
      }>("/residencias/panel"),
    [],
  );
  const [soloProblemas, setSoloProblemas] = useState(false);
  if (panel.error) return <Aviso error={panel.error} />;
  if (!panel.datos) return <Cargando />;
  const { resumen, tipos, items } = panel.datos;
  const filas = soloProblemas ? items.filter((f) => f.estado !== "vigente") : items;
  return (
    <>
      <h1>Residencias de larga estadía</h1>
      <p className="tenue">Documentación de cada residencia y personas internadas. Para cargar una residencia nueva, agréguela en «Recursos y mapa» con el tipo «Residencia de larga estadía».</p>
      <div className="indicadores">
        <Cifra valor={resumen.residencias} texto="residencias" />
        <Cifra valor={resumen.internados} texto="personas internadas" />
        <Cifra valor={resumen.con_documentos_vencidos} texto="con documentación vencida" alerta />
        <Cifra valor={resumen.con_documentos_por_vencer} texto="con documentación por vencer" alerta />
        <Cifra valor={resumen.con_documentos_faltantes} texto="con documentación faltante" alerta />
      </div>
      <label style={{ display: "block", margin: "0.5rem 0" }}>
        <input type="checkbox" checked={soloProblemas} onChange={(e) => setSoloProblemas(e.target.checked)} /> Mostrar solo las que tienen algo para resolver
      </label>
      {filas.length === 0 ? (
        <Vacio>{items.length === 0 ? "No hay residencias cargadas." : "No hay residencias con documentación para resolver."}</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Residencia</th>
              <th>Internados</th>
              {tipos.map((t) => (
                <th key={t.codigo}>{t.texto}</th>
              ))}
              <th>Próximo vencimiento</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.id}>
                <td>
                  <Enlace a={`/recursos/${f.id}`}>{f.nombre}</Enlace>
                  <div className="tenue">{[f.localidad, f.departamento].filter(Boolean).join(", ")}</div>
                </td>
                <td>{f.internados}</td>
                {tipos.map((t) => (
                  <td key={t.codigo}>
                    <MarcaEstado estado={f.estados[t.codigo] ?? "falta"} />
                  </td>
                ))}
                <td>{f.proximo_vencimiento ? fecha(f.proximo_vencimiento) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

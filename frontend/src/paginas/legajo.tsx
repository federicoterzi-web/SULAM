import { CarpetaFisica, SeccionCarpeta } from "./archivo";
import { SeccionNegativa } from "./anses";
import { SeccionInformes } from "./informes";
import { UbicacionDomicilio } from "./ubicacion";
import { useState, type FormEvent, Fragment } from "react";
import { ApiError, api, type Caso, type EventoAuditoria, type Expediente, type Legajo, type PersonaResumen, type Vinculado } from "../api";
import {
  Aviso,
  Campo,
  Cargando,
  Enlace,
  Estado,
  Modal,
  Seccion,
  Vacio,
  documento,
  edad,
  fecha,
  fechaHora,
  navegar,
  nombre,
  useDatos,
  useEnvio,
  useSesion,
} from "../comun";
import { FormDocumento, TablaDocumentos } from "./documentos";
import { FotoPersona, PanelDocumentacion, RecorteFoto } from "./foto-documentacion";
import { SeccionInternacion } from "./residencias";
import { SeccionSubsidios } from "./subsidios";
import { FormCaratula, textoDe, textoLista } from "./formularios";
import { FormPersona, SelectorPersona } from "./legajos";

type Dialogo = null | "editar" | "caso" | "expediente" | "vinculado" | "documento" | "unificar" | "foto";

export function PaginaLegajo({ id }: { id: string }) {
  const { formularios } = useSesion();
  const { datos: l, error, recargar } = useDatos(() => api.get<Legajo>(`/personas/${id}`), [id]);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [vinculadoEditado, setVinculadoEditado] = useState<Vinculado | null>(null);
  const [versionFoto, setVersionFoto] = useState(0);

  if (error instanceof ApiError && error.status === 409 && error.detalle?.unificada_en_id) {
    return (
      <div className="aviso aviso-info">
        Este legajo fue unificado con otro.{" "}
        <Enlace a={`/legajos/${error.detalle.unificada_en_id}`}>Ir al legajo vigente</Enlace>
      </div>
    );
  }
  if (error) return <Aviso error={error} />;
  if (!l) return <Cargando />;

  const cerrar = () => setDialogo(null);
  const listo = () => {
    setDialogo(null);
    setVinculadoEditado(null);
    recargar();
  };

  return (
    <>
      <div className="ficha">
        <FotoPersona personaId={l.id} tiene={!!l.tiene_foto} nombre={nombre(l)} version={versionFoto} />
        <div style={{ flex: 1 }}>
          <span className="ficha-legajo">
            Legajo {l.numero_legajo}
            {l.legajo_provisorio && l.legajo_provisorio !== l.numero_legajo && ` (antes ${l.legajo_provisorio})`}
            {l.legajo_provisorio === l.numero_legajo && " · provisorio hasta tener DNI"}
          </span>
          <h1>{nombre(l)}</h1>
          <p className="ficha-datos">
            {documento(l)}
            {l.fecha_nacimiento && (
              <>
                {" · "}
                {fecha(l.fecha_nacimiento)} ({l.fecha_nacimiento_aproximada ? "aprox. " : ""}
                {edad(l.fecha_nacimiento)} años)
              </>
            )}
            {l.localidad && <> · {l.localidad}</>}
          </p>
        </div>
        <div className="fila-botones">
          {l.permisos.modificar && (
            <button className="boton" onClick={() => setDialogo("editar")}>
              Editar datos
            </button>
          )}
          {l.permisos.modificar && (
            <button className="boton" onClick={() => setDialogo("foto")}>
              {l.tiene_foto ? "Cambiar foto" : "Foto del DNI"}
            </button>
          )}
          {l.permisos.unificar && (
            <button className="boton" onClick={() => setDialogo("unificar")}>
              Unificar con otro legajo
            </button>
          )}
        </div>
      </div>

      <nav className="indice" aria-label="Secciones del legajo">
        <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-casos")?.scrollIntoView(); }}>Casos ({l.casos.length})</a>
        <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-exp")?.scrollIntoView(); }}>Expedientes ({l.expedientes.length})</a>
        <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-vinc")?.scrollIntoView(); }}>Vinculados ({l.vinculados.length})</a>
        <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-docs")?.scrollIntoView(); }}>Documentos ({l.documentos.length})</a>
        <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-act")?.scrollIntoView(); }}>Actividad</a>
      </nav>

      <Seccion titulo="Datos personales">
        <dl className="datos">
          <dt>Domicilio</dt>
          <dd>{l.domicilio || "—"}</dd>
          <dt>Teléfono</dt>
          <dd>{l.telefono || "—"}</dd>
          <dt>CUIL</dt>
          <dd>{l.cuil || "—"}</dd>
          {l.sin_documento && (
            <>
              <dt>Situación del documento</dt>
              <dd>{l.motivo_sin_documento || "—"}</dd>
            </>
          )}
          <dt>Género</dt>
          <dd>{textoDe(formularios.generos, l.genero) || "—"}</dd>
          <dt>Barrio / departamento</dt>
          <dd>{[l.barrio, l.departamento].filter(Boolean).join(" · ") || "—"}</dd>
          <dt>Cobertura de salud</dt>
          <dd>
            {textoLista(formularios.cobertura_salud, l.cobertura_salud) || "—"}
            {l.obra_social && ` (${l.obra_social})`}
          </dd>
          <dt>Cobertura previsional</dt>
          <dd>
            {textoLista(formularios.cobertura_previsional, l.cobertura_previsional) || "—"}
            {l.trabajo_informal && " · trabajo informal"}
          </dd>
          <dt>CUD</dt>
          <dd>{textoDe(formularios.cud, l.cud) || "—"}</dd>
          <dt>Discapacidad</dt>
          <dd>{textoLista(formularios.discapacidad, l.discapacidades) || "—"}</dd>
          <dt>Observaciones</dt>
          <dd className="texto-largo">{l.observaciones || "—"}</dd>
          <dt>Legajo creado</dt>
          <dd>{fechaHora(l.creado_en)}</dd>
        </dl>
      </Seccion>

      <SeccionCarpeta personaId={l.id} />

      <SeccionNegativa personaId={l.id} />

      <SeccionInternacion personaId={l.id} />

      <SeccionSubsidios personaId={l.id} />

      <Seccion titulo="Ubicación del domicilio">
        <UbicacionDomicilio persona={l} puedeModificar={l.permisos.modificar} alCambiar={recargar} />
      </Seccion>

      <Seccion
        id="s-casos"
        titulo="Casos"
        acciones={
          l.permisos.crear_caso && (
            <button className="boton boton-primario" onClick={() => setDialogo("caso")}>
              Nuevo caso
            </button>
          )
        }
      >
        <TablaCasos casos={l.casos} />
      </Seccion>

      <Seccion
        id="s-exp"
        titulo="Expedientes"
        acciones={
          l.permisos.crear_expediente && (
            <button className="boton" onClick={() => setDialogo("expediente")}>
              Vincular expediente
            </button>
          )
        }
      >
        <TablaExpedientes expedientes={l.expedientes} casos={l.casos} />
      </Seccion>

      <Seccion
        id="s-vinc"
        titulo="Personas e instituciones vinculadas"
        acciones={
          l.permisos.modificar && (
            <button className="boton" onClick={() => setDialogo("vinculado")}>
              Agregar
            </button>
          )
        }
      >
        {l.vinculados.length === 0 ? (
          <Vacio>No hay personas vinculadas registradas.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Vínculo</th>
                <th>Nombre</th>
                <th>Contacto</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {l.vinculados.map((v) => (
                <tr key={v.id} className={v.activo ? "" : "fila-inactiva"}>
                  <td>
                    {v.tipo_vinculo.nombre} {!v.activo && <small>(inactivo)</small>}
                  </td>
                  <>
                      <td>
                        {v.es_institucion ? v.nombre_institucion : `${(v.apellidos ?? "").toUpperCase()}, ${v.nombres ?? ""}`}
                        {v.numero_documento && <small className="tenue"> · Doc. {v.numero_documento}</small>}
                        {v.observaciones && <div className="tenue">{v.observaciones}</div>}
                      </td>
                      <td>
                        {v.telefono}
                        {v.domicilio && <div className="tenue">{v.domicilio}</div>}
                      </td>
                      <td>
                        {l.permisos.modificar && (
                          <button className="boton boton-chico" onClick={() => setVinculadoEditado(v)}>
                            Editar
                          </button>
                        )}
                      </td>
                  </>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>

      <SeccionInformes personaId={l.id} puedeCrear={l.permisos.modificar} />

      <PanelDocumentacion personaId={l.id} puedeCargar={!!l.permisos.cargar_documento} alCargar={() => setDialogo("documento")} version={l.documentos.length} />

      <Seccion
        id="s-docs"
        titulo="Documentos"
        acciones={
          l.permisos.cargar_documento && (
            <button className="boton" onClick={() => setDialogo("documento")}>
              Cargar documento
            </button>
          )
        }
      >
        <TablaDocumentos documentos={l.documentos} alCambiar={recargar} />
      </Seccion>

      {l.ingresos.length > 0 && (
        <Seccion titulo="Ingresos de Mesa de Entrada">
          <ul className="lista-simple">
            {l.ingresos.map((i) => (
              <li key={i.id}>
                <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace> · {fecha(i.fecha_ingreso)} · {i.asunto}
                {i.remitente && <span className="tenue"> — {i.remitente}</span>}
              </li>
            ))}
          </ul>
        </Seccion>
      )}

      <Actividad personaId={l.id} />

      {dialogo === "editar" && (
        <Modal titulo="Editar datos del legajo" alCerrar={cerrar} ancho>
          <FormPersona persona={l} alGuardar={listo} alCancelar={cerrar} />
        </Modal>
      )}
      {dialogo === "caso" && (
        <Modal titulo="Nuevo caso · Carátula de legajo" alCerrar={cerrar} ancho>
          <FormCaso personaId={l.id} alGuardar={(c) => navegar(`/casos/${c.id}`)} />
        </Modal>
      )}
      {dialogo === "expediente" && (
        <Modal titulo="Vincular expediente" alCerrar={cerrar}>
          <FormExpediente personaId={l.id} casos={l.casos} alGuardar={listo} />
        </Modal>
      )}
      {(dialogo === "vinculado" || vinculadoEditado) && (
        <Modal titulo={vinculadoEditado ? "Editar persona vinculada" : "Agregar persona o institución vinculada"} alCerrar={() => { cerrar(); setVinculadoEditado(null); }}>
          <FormVinculado personaId={l.id} vinculado={vinculadoEditado ?? undefined} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "documento" && (
        <Modal titulo="Cargar documento" alCerrar={cerrar}>
          <FormDocumento personaId={l.id} casos={l.casos} expedientes={l.expedientes} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "foto" && (
        <RecorteFoto
          personaId={l.id}
          documentos={l.documentos}
          alCerrar={cerrar}
          alGuardar={() => {
            setVersionFoto((v) => v + 1);
            listo();
          }}
        />
      )}
      {dialogo === "unificar" && (
        <Modal titulo="Unificar legajos" alCerrar={cerrar} ancho>
          <Unificar destino={l} alTerminar={listo} />
        </Modal>
      )}
    </>
  );
}

export function TablaCasos({ casos, conPersona }: { casos: Caso[]; conPersona?: boolean }) {
  if (casos.length === 0) return <Vacio>No hay casos.</Vacio>;
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Caso</th>
          {conPersona && <th>Persona</th>}
          <th>Estado</th>
          <th>Área</th>
          <th>Responsables</th>
          <th>Apertura</th>
        </tr>
      </thead>
      <tbody>
        {casos.map((c) => (
          <tr key={c.id}>
            <td>
              <Enlace a={`/casos/${c.id}`}>{c.numero}</Enlace>
              {c.motivo && <div className="tenue recorte">{c.motivo}</div>}
            </td>
            {conPersona && <td>{c.persona && <Enlace a={`/legajos/${c.persona.id}`}>{nombre(c.persona)}</Enlace>}</td>}
            <td>
              <Estado estado={c.estado} />
            </td>
            <td>{c.area?.nombre ?? "—"}</td>
            <td>{c.responsables.map((r) => r.nombre_completo).join(", ") || <span className="texto-alerta">Sin asignar</span>}</td>
            <td>{fecha(c.abierto_en)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TablaExpedientes({ expedientes, casos = [] }: { expedientes: Expediente[]; casos?: Caso[] }) {
  const [carpeta, setCarpeta] = useState<string | null>(null);
  if (expedientes.length === 0) return <Vacio>No hay expedientes vinculados.</Vacio>;
  const numeroCaso = Object.fromEntries(casos.map((c) => [c.id, c.numero]));
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Número</th>
          <th>Tipo</th>
          <th>Organismo</th>
          <th>Carátula</th>
          <th>Caso</th>
          <th>En papel</th>
        </tr>
      </thead>
      <tbody>
        {expedientes.map((x) => (
          <Fragment key={x.id}>
          <tr>
            <td>
              <strong>
                <Enlace a={`/expedientes/${x.id}`}>{x.numero}</Enlace>
              </strong>
            </td>
            <td>{x.tipo === "judicial" ? "Judicial" : "Administrativo"}</td>
            <td>{x.organismo ?? "—"}</td>
            <td>{x.caratula ?? "—"}</td>
            <td>{x.caso_id ? <Enlace a={`/casos/${x.caso_id}`}>{numeroCaso[x.caso_id] ?? "Ver caso"}</Enlace> : "—"}</td>
            <td>
              <button className="boton boton-chico" onClick={() => setCarpeta(carpeta === x.id ? null : x.id)}>
                {carpeta === x.id ? "Cerrar" : "Dónde está"}
              </button>
            </td>
          </tr>
          {carpeta === x.id && (
            <tr className="fila-detalle">
              <td colSpan={6}>
                <CarpetaFisica expedienteId={x.id} />
              </td>
            </tr>
          )}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

export function FormCaso({ personaId, ingresoId, alGuardar }: { personaId: string; ingresoId?: string; alGuardar: (c: Caso) => void }) {
  return <FormCaratula personaId={personaId} ingresoId={ingresoId} alGuardar={alGuardar} />;
}

export function FormExpediente({ personaId, casos, alGuardar }: { personaId: string; casos: Caso[]; alGuardar: () => void }) {
  const [d, setD] = useState({ numero: "", tipo: "administrativo", organismo: "", caratula: "", caso_id: "", observaciones: "" });
  const { enviando, error, ejecutar } = useEnvio();
  const cambia = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() =>
      api.post("/expedientes", {
        persona_id: personaId,
        numero: d.numero,
        tipo: d.tipo,
        organismo: d.organismo || null,
        caratula: d.caratula || null,
        caso_id: d.caso_id || null,
        observaciones: d.observaciones || null,
      }),
    );
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <div className="grilla">
        <Campo etiqueta="Número *">
          <input value={d.numero} onChange={cambia("numero")} required autoFocus />
        </Campo>
        <Campo etiqueta="Tipo *">
          <select value={d.tipo} onChange={cambia("tipo")}>
            <option value="administrativo">Administrativo</option>
            <option value="judicial">Judicial</option>
          </select>
        </Campo>
        <Campo etiqueta="Organismo">
          <input value={d.organismo} onChange={cambia("organismo")} />
        </Campo>
        <Campo etiqueta="Caso">
          <select value={d.caso_id} onChange={cambia("caso_id")}>
            <option value="">Sin caso</option>
            {casos.map((c) => (
              <option key={c.id} value={c.id}>
                {c.numero}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Carátula" ancho="completo">
          <input value={d.caratula} onChange={cambia("caratula")} />
        </Campo>
        <Campo etiqueta="Observaciones" ancho="completo">
          <textarea rows={2} value={d.observaciones} onChange={cambia("observaciones")} />
        </Campo>
      </div>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

export function FormVinculado({ personaId, vinculado, alGuardar }: { personaId: string; vinculado?: Vinculado; alGuardar: () => void }) {
  const { catalogos } = useSesion();
  const [d, setD] = useState({
    tipo_vinculo_id: String(vinculado?.tipo_vinculo.id ?? ""),
    es_institucion: vinculado?.es_institucion ?? false,
    apellidos: vinculado?.apellidos ?? "",
    nombres: vinculado?.nombres ?? "",
    nombre_institucion: vinculado?.nombre_institucion ?? "",
    numero_documento: vinculado?.numero_documento ?? "",
    telefono: vinculado?.telefono ?? "",
    domicilio: vinculado?.domicilio ?? "",
    observaciones: vinculado?.observaciones ?? "",
    activo: vinculado?.activo ?? true,
  });
  const { enviando, error, ejecutar } = useEnvio();
  const cambia = (k: keyof typeof d) => (e: { target: { value: string; type?: string; checked?: boolean } }) =>
    setD({ ...d, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const { es_institucion, activo, ...resto } = d;
    const cuerpo = { ...resto, tipo_vinculo_id: Number(d.tipo_vinculo_id) };
    const r = await ejecutar(() =>
      vinculado
        ? api.patch(`/vinculados/${vinculado.id}`, { ...cuerpo, activo })
        : api.post(`/personas/${personaId}/vinculados`, { ...cuerpo, es_institucion }),
    );
    if (r) alGuardar();
  };

  return (
    <form onSubmit={enviar} className="formulario">
      <div className="grilla">
        <Campo etiqueta="Tipo de vínculo *">
          <select value={d.tipo_vinculo_id} onChange={cambia("tipo_vinculo_id")} required>
            <option value="">Elegir…</option>
            {catalogos.tipos_vinculo.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </select>
        </Campo>
        {!vinculado && (
          <label className="casilla">
            <input type="checkbox" checked={d.es_institucion} onChange={cambia("es_institucion")} />
            Es una institución
          </label>
        )}
        {d.es_institucion ? (
          <Campo etiqueta="Nombre de la institución *" ancho="completo">
            <input value={d.nombre_institucion} onChange={cambia("nombre_institucion")} required />
          </Campo>
        ) : (
          <>
            <Campo etiqueta="Apellidos">
              <input value={d.apellidos} onChange={cambia("apellidos")} />
            </Campo>
            <Campo etiqueta="Nombres">
              <input value={d.nombres} onChange={cambia("nombres")} />
            </Campo>
            <Campo etiqueta="Documento">
              <input value={d.numero_documento} onChange={cambia("numero_documento")} />
            </Campo>
          </>
        )}
        <Campo etiqueta="Teléfono">
          <input value={d.telefono} onChange={cambia("telefono")} />
        </Campo>
        <Campo etiqueta="Domicilio" ancho="completo">
          <input value={d.domicilio} onChange={cambia("domicilio")} />
        </Campo>
        <Campo etiqueta="Observaciones" ancho="completo">
          <textarea rows={2} value={d.observaciones} onChange={cambia("observaciones")} />
        </Campo>
      </div>
      {vinculado && (
        <label className="casilla">
          <input type="checkbox" checked={d.activo} onChange={cambia("activo")} />
          Vínculo vigente
        </label>
      )}
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

function Unificar({ destino, alTerminar }: { destino: Legajo; alTerminar: () => void }) {
  const [origen, setOrigen] = useState<PersonaResumen | null>(null);
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!origen) return;
    const r = await ejecutar(() =>
      api.post(`/personas/${destino.id}/unificar`, { legajo_a_absorber_id: origen.id, motivo }),
    );
    if (r) alTerminar();
  };

  if (!origen)
    return (
      <>
        <p>
          Se conservará el legajo <strong>{destino.numero_legajo}</strong>. Busque el legajo duplicado que será absorbido:
        </p>
        <SelectorPersona alElegir={(p) => (p.id === destino.id ? null : setOrigen(p))} />
      </>
    );

  return (
    <form onSubmit={enviar} className="formulario">
      <div className="aviso aviso-advertencia">
        Los casos, expedientes, ingresos, documentos y vinculados del legajo <strong>{origen.numero_legajo}</strong> (
        {nombre(origen)}) pasarán al legajo <strong>{destino.numero_legajo}</strong> ({nombre(destino)}). El legajo
        absorbido queda inactivo y redirige al vigente. La operación queda registrada en la auditoría.
      </div>
      <Campo etiqueta="Motivo de la unificación *">
        <input value={motivo} onChange={(e) => setMotivo(e.target.value)} required minLength={5} />
      </Campo>
      <Aviso error={error} />
      <div className="fila-botones">
        <button type="button" className="boton" onClick={() => setOrigen(null)}>
          Elegir otro
        </button>
        <button className="boton boton-peligro" disabled={enviando}>
          Unificar
        </button>
      </div>
    </form>
  );
}

const ACCIONES: Record<string, string> = {
  crear: "Creó",
  modificar: "Modificó",
  cargar: "Cargó documento",
  descargar: "Descargó documento",
  eliminar: "Dio de baja",
  vincular: "Vinculó ingreso",
  asignar: "Asignó",
  finalizar_asignacion: "Finalizó asignación",
  cambiar_estado: "Cambió estado",
  reabrir: "Reabrió",
  unificar: "Unificó legajos",
  unificado_en: "Legajo absorbido",
  consultar_legajo: "Consultó el legajo",
  consultar_caso: "Consultó el caso",
  consultar_ingreso: "Consultó ingreso",
};

const ENTIDADES: Record<string, string> = {
  persona: "legajo",
  caso: "caso",
  documento: "documento",
  expediente: "expediente",
  ingreso: "ingreso",
  vinculado: "vinculado",
};

export function textoAccion(a: EventoAuditoria): string {
  const verbo = ACCIONES[a.accion] ?? a.accion;
  const ent = ENTIDADES[a.entidad] ?? a.entidad;
  const extra =
    a.detalle?.titulo ?? a.detalle?.numero ?? (a.detalle?.de ? `${a.detalle.de} → ${a.detalle.a}` : null) ?? a.detalle?.usuario;
  return `${verbo} ${["crear", "modificar"].includes(a.accion) ? ent : ""}${extra ? ` · ${extra}` : ""}`.trim();
}

function Actividad({ personaId }: { personaId: string }) {
  const [eventos, setEventos] = useState<EventoAuditoria[] | null>(null);
  const { enviando, error, ejecutar } = useEnvio();
  const cargar = async () => {
    const r = await ejecutar(() => api.get<EventoAuditoria[]>(`/personas/${personaId}/actividad`));
    if (r) setEventos(r);
  };
  return (
    <Seccion
      id="s-act"
      titulo="Actividad del legajo"
      acciones={
        !eventos && (
          <button className="boton" onClick={cargar} disabled={enviando}>
            Ver historial
          </button>
        )
      }
    >
      <Aviso error={error} />
      {eventos &&
        (eventos.length === 0 ? (
          <Vacio>Sin actividad registrada.</Vacio>
        ) : (
          <ol className="linea-tiempo">
            {eventos.map((a) => (
              <li key={a.id}>
                <time>{fechaHora(a.en)}</time> <strong>{a.usuario}</strong> — {textoAccion(a)}
              </li>
            ))}
          </ol>
        ))}
    </Seccion>
  );
}

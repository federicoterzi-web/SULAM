import { useState, type FormEvent } from "react";
import { api, type Ingreso, type PersonaResumen } from "../api";
import {
  Aviso,
  Campo,
  Cargando,
  Enlace,
  Modal,
  Seccion,
  Vacio,
  documento,
  fechaHora,
  navegar,
  nombre,
  useDatos,
  useEnvio,
  useSesion,
} from "../comun";
import { FormDocumento, TablaDocumentos } from "./documentos";
import { FormCaso } from "./legajo";
import { FormPersona, ListaPersonas, SelectorPersona } from "./legajos";

export function PaginaMesa() {
  const { puede } = useSesion();
  const [pendientes, setPendientes] = useState(false);
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState("");
  const [nuevo, setNuevo] = useState(false);
  const { datos, error } = useDatos(
    () => api.get<Ingreso[]>("/ingresos", { pendientes: pendientes || undefined, q: filtro, limite: 100 }),
    [pendientes, filtro],
  );

  return (
    <>
      <div className="titulo-pagina">
        <h1>Mesa de Entrada</h1>
        {puede("mesa_entrada", "crear") && (
          <button className="boton boton-primario" onClick={() => setNuevo(true)}>
            Registrar ingreso
          </button>
        )}
      </div>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltro(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="N° de ingreso, asunto, remitente o persona" aria-label="Buscar ingreso" />
        <label className="casilla">
          <input type="checkbox" checked={pendientes} onChange={(e) => setPendientes(e.target.checked)} />
          Solo sin legajo asociado
        </label>
        <button className="boton">Filtrar</button>
      </form>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : datos.length === 0 ? (
        <Vacio>No hay ingresos registrados con esos criterios.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Ingreso</th>
              <th>Fecha</th>
              <th>Asunto</th>
              <th>Remitente</th>
              <th>Legajo</th>
            </tr>
          </thead>
          <tbody>
            {datos.map((i) => (
              <tr key={i.id}>
                <td>
                  <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace>
                </td>
                <td>{fechaHora(i.fecha_ingreso)}</td>
                <td>
                  {i.asunto}
                  {i.persona_mencionada && <div className="tenue">Menciona a: {i.persona_mencionada}</div>}
                </td>
                <td>{i.remitente ?? "—"}</td>
                <td>
                  {i.persona ? (
                    <Enlace a={`/legajos/${i.persona.id}`}>{i.persona.numero_legajo}</Enlace>
                  ) : (
                    <span className="insignia pendiente">Pendiente</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {nuevo && (
        <Modal titulo="Registrar ingreso" alCerrar={() => setNuevo(false)} ancho>
          <FormIngreso alGuardar={(i) => navegar(`/mesa/${i.id}`)} />
        </Modal>
      )}
    </>
  );
}

export function FormIngreso({ alGuardar }: { alGuardar: (i: Ingreso) => void }) {
  const { catalogos } = useSesion();
  const [d, setD] = useState({
    asunto: "",
    remitente: "",
    tipo_documental_id: "",
    folios: "",
    persona_mencionada: "",
    documento_mencionado: "",
    numero_expediente_externo: "",
    observaciones: "",
  });
  const { enviando, error, ejecutar } = useEnvio();
  const cambia = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const i = await ejecutar(() =>
      api.post<Ingreso>("/ingresos", {
        asunto: d.asunto,
        remitente: d.remitente || null,
        tipo_documental_id: d.tipo_documental_id ? Number(d.tipo_documental_id) : null,
        folios: d.folios ? Number(d.folios) : null,
        persona_mencionada: d.persona_mencionada || null,
        documento_mencionado: d.documento_mencionado || null,
        numero_expediente_externo: d.numero_expediente_externo || null,
        observaciones: d.observaciones || null,
      }),
    );
    if (i) alGuardar(i);
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <p className="tenue">
        El ingreso se registra aunque todavía no exista el legajo. La fecha y hora se toman automáticamente.
      </p>
      <div className="grilla">
        <Campo etiqueta="Asunto *" ancho="completo">
          <input value={d.asunto} onChange={cambia("asunto")} required autoFocus />
        </Campo>
        <Campo etiqueta="Remitente / quién lo presenta">
          <input value={d.remitente} onChange={cambia("remitente")} />
        </Campo>
        <Campo etiqueta="Tipo de documento">
          <select value={d.tipo_documental_id} onChange={cambia("tipo_documental_id")}>
            <option value="">—</option>
            {catalogos.tipos_documentales.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Folios">
          <input type="number" min={0} value={d.folios} onChange={cambia("folios")} />
        </Campo>
        <Campo etiqueta="N° de expediente externo">
          <input value={d.numero_expediente_externo} onChange={cambia("numero_expediente_externo")} />
        </Campo>
        <Campo etiqueta="Persona mayor mencionada" ayuda="Tal como figura en la documentación.">
          <input value={d.persona_mencionada} onChange={cambia("persona_mencionada")} />
        </Campo>
        <Campo etiqueta="Documento mencionado">
          <input value={d.documento_mencionado} onChange={cambia("documento_mencionado")} />
        </Campo>
        <Campo etiqueta="Observaciones" ancho="completo">
          <textarea rows={2} value={d.observaciones} onChange={cambia("observaciones")} />
        </Campo>
      </div>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Registrar
        </button>
      </div>
    </form>
  );
}

type Dialogo = null | "vincular" | "nuevo-legajo" | "documento" | "caso";

export function PaginaIngreso({ id }: { id: string }) {
  const { puede } = useSesion();
  const { datos: i, error, recargar } = useDatos(() => api.get<Ingreso>(`/ingresos/${id}`), [id]);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const vincular = useEnvio();

  if (error) return <Aviso error={error} />;
  if (!i) return <Cargando />;

  const vincularA = async (p: PersonaResumen) => {
    const r = await vincular.ejecutar(() => api.post(`/ingresos/${i.id}/vincular`, { persona_id: p.id }));
    if (r) {
      setDialogo(null);
      recargar();
    }
  };

  return (
    <>
      <div className="ficha">
        <div>
          <span className="ficha-legajo">Ingreso {i.numero}</span>
          <h1>{i.asunto}</h1>
          <p className="ficha-datos">
            {fechaHora(i.fecha_ingreso)}
            {i.remitente && <> · {i.remitente}</>}
            {i.folios !== null && <> · {i.folios} folios</>}
          </p>
        </div>
        <div className="fila-botones">
          {(puede("mesa_entrada", "crear") || puede("documentos", "crear")) && (
            <button className="boton" onClick={() => setDialogo("documento")}>
              Adjuntar escaneo
            </button>
          )}
        </div>
      </div>

      <Seccion titulo="Datos registrados">
        <dl className="datos">
          <dt>Tipo</dt>
          <dd>{i.tipo_documental?.nombre ?? "—"}</dd>
          <dt>Persona mencionada</dt>
          <dd>{i.persona_mencionada ?? "—"}</dd>
          <dt>Documento mencionado</dt>
          <dd>{i.documento_mencionado ?? "—"}</dd>
          <dt>Expediente externo</dt>
          <dd>{i.numero_expediente_externo ?? "—"}</dd>
          <dt>Observaciones</dt>
          <dd className="texto-largo">{i.observaciones ?? "—"}</dd>
        </dl>
      </Seccion>

      <Seccion titulo="Legajo">
        {i.persona ? (
          <p>
            Asociado a <Enlace a={`/legajos/${i.persona.id}`}>{i.persona.numero_legajo} · {nombre(i.persona)}</Enlace> (
            {documento(i.persona)}) el {fechaHora(i.vinculado_en)}.
            {i.caso_id && (
              <>
                {" "}
                Caso: <Enlace a={`/casos/${i.caso_id}`}>ver caso</Enlace>.
              </>
            )}
          </p>
        ) : (
          <>
            <div className="aviso aviso-advertencia">Este ingreso todavía no está asociado a ningún legajo.</div>
            {i.sugerencias && i.sugerencias.length > 0 && (
              <>
                <h3>Legajos que podrían corresponder</h3>
                <ListaPersonas personas={i.sugerencias} alElegir={puede("mesa_entrada", "modificar") ? vincularA : undefined} />
              </>
            )}
            {puede("mesa_entrada", "modificar") && (
              <div className="fila-botones">
                <button className="boton" onClick={() => setDialogo("vincular")}>
                  Buscar otro legajo
                </button>
                {puede("personas", "crear") && (
                  <button className="boton" onClick={() => setDialogo("nuevo-legajo")}>
                    Crear legajo nuevo
                  </button>
                )}
              </div>
            )}
          </>
        )}
        {i.persona && !i.caso_id && puede("casos", "crear") && (
          <button className="boton" onClick={() => setDialogo("caso")}>
            Abrir caso a partir de este ingreso
          </button>
        )}
        <Aviso error={vincular.error} />
      </Seccion>

      <Seccion titulo="Documentación adjunta">
        <TablaDocumentos documentos={i.documentos ?? []} alCambiar={recargar} />
      </Seccion>

      {dialogo === "vincular" && (
        <Modal titulo="Asociar a un legajo" alCerrar={() => setDialogo(null)} ancho>
          <SelectorPersona alElegir={vincularA} />
          <Aviso error={vincular.error} />
        </Modal>
      )}
      {dialogo === "nuevo-legajo" && (
        <Modal titulo="Crear legajo y asociar el ingreso" alCerrar={() => setDialogo(null)} ancho>
          {i.persona_mencionada && (
            <p className="tenue">Mencionada en el ingreso como: «{i.persona_mencionada}»</p>
          )}
          <FormPersona
            sugerido={{ numero_documento: i.documento_mencionado ?? "" }}
            alGuardar={(p) => vincularA(p)}
            alCancelar={() => setDialogo(null)}
          />
        </Modal>
      )}
      {dialogo === "documento" && (
        <Modal titulo="Adjuntar documentación al ingreso" alCerrar={() => setDialogo(null)}>
          <FormDocumento
            ingresoId={i.id}
            personaId={i.persona_id ?? undefined}
            alGuardar={() => {
              setDialogo(null);
              recargar();
            }}
          />
        </Modal>
      )}
      {dialogo === "caso" && i.persona_id && (
        <Modal titulo="Nuevo caso" alCerrar={() => setDialogo(null)}>
          <FormCaso personaId={i.persona_id} ingresoId={i.id} alGuardar={(c) => navegar(`/casos/${c.id}`)} />
        </Modal>
      )}
    </>
  );
}


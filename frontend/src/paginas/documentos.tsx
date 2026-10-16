import { useState, type FormEvent } from "react";
import { api, type Caso, type Documento, type Expediente } from "../api";
import { Aviso, Campo, Modal, Reservado, Vacio, fechaHora, tamano, useEnvio, useSesion } from "../comun";

export function TablaDocumentos({
  documentos,
  alCambiar,
}: {
  documentos: Documento[];
  alCambiar?: () => void;
}) {
  const { puede } = useSesion();
  const [eliminar, setEliminar] = useState<Documento | null>(null);
  if (documentos.length === 0) return <Vacio>No hay documentos cargados.</Vacio>;
  return (
    <>
      <table className="tabla">
        <thead>
          <tr>
            <th>Documento</th>
            <th>Tipo</th>
            <th>Cargado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {documentos.map((d) =>
            d.contenido_restringido ? (
              <tr key={d.id} className="fila-restringida">
                <td>
                  <Reservado texto="Documento reservado" />
                </td>
                <td>{d.tipo_documental.nombre}</td>
                <td>{fechaHora(d.cargado_en)}</td>
                <td></td>
              </tr>
            ) : (
              <tr key={d.id}>
                <td>
                  <strong>{d.titulo}</strong> {d.reservado && <Reservado />}
                  <br />
                  <small className="tenue">
                    {d.nombre_original} · {tamano(d.tamano)}
                  </small>
                  {d.descripcion && <div className="tenue">{d.descripcion}</div>}
                </td>
                <td>{d.tipo_documental.nombre}</td>
                <td>
                  {fechaHora(d.cargado_en)}
                  <br />
                  <small className="tenue">{d.cargado_por?.nombre_completo}</small>
                </td>
                <td className="acciones-fila">
                  {puede("documentos", "descargar") && (
                    <>
                      <a className="boton boton-chico" href={`/api/documentos/${d.id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
                        Ver
                      </a>
                      <a className="boton boton-chico" href={`/api/documentos/${d.id}/archivo`}>
                        Descargar
                      </a>
                    </>
                  )}
                  {puede("documentos", "administrar") && alCambiar && (
                    <button className="boton boton-chico boton-peligro" onClick={() => setEliminar(d)}>
                      Dar de baja
                    </button>
                  )}
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      {eliminar && (
        <Modal titulo="Dar de baja documento" alCerrar={() => setEliminar(null)}>
          <BajaDocumento
            documento={eliminar}
            alTerminar={() => {
              setEliminar(null);
              alCambiar?.();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function BajaDocumento({ documento, alTerminar }: { documento: Documento; alTerminar: () => void }) {
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/documentos/${documento.id}/eliminar`, { motivo }));
    if (r) alTerminar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <p>
        El documento <strong>{documento.titulo}</strong> dejará de mostrarse en el legajo. El archivo y su registro se
        conservan y la baja queda en la auditoría.
      </p>
      <Campo etiqueta="Motivo *">
        <input value={motivo} onChange={(e) => setMotivo(e.target.value)} minLength={5} required autoFocus />
      </Campo>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-peligro" disabled={enviando}>
          Dar de baja
        </button>
      </div>
    </form>
  );
}

export function FormDocumento({
  personaId,
  ingresoId,
  casos = [],
  expedientes = [],
  casoFijo,
  registroDemandaId,
  tipoInicial,
  alGuardar,
}: {
  personaId?: string;
  ingresoId?: string;
  registroDemandaId?: string;
  tipoInicial?: string;
  casos?: Caso[];
  expedientes?: Expediente[];
  casoFijo?: string;
  alGuardar: (d: Documento) => void;
}) {
  const { catalogos } = useSesion();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState(
    String(catalogos.tipos_documentales.find((t) => t.nombre === tipoInicial)?.id ?? ""),
  );
  const [descripcion, setDescripcion] = useState("");
  const [casoId, setCasoId] = useState(casoFijo ?? "");
  const [expedienteId, setExpedienteId] = useState("");
  const [reservado, setReservado] = useState(false);
  const [advertencias, setAdvertencias] = useState<string[]>([]);
  const { enviando, error, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!archivo) return;
    const fd = new FormData();
    fd.append("archivo", archivo);
    fd.append("titulo", titulo);
    fd.append("tipo_documental_id", tipo);
    if (descripcion) fd.append("descripcion", descripcion);
    if (personaId) fd.append("persona_id", personaId);
    if (ingresoId) fd.append("ingreso_id", ingresoId);
    if (registroDemandaId) fd.append("registro_demanda_id", registroDemandaId);
    if (casoId) fd.append("caso_id", casoId);
    if (expedienteId) fd.append("expediente_id", expedienteId);
    fd.append("reservado", String(reservado));
    const d = await ejecutar(() => api.post<Documento>("/documentos", fd));
    if (d) {
      if (d.advertencias?.length) {
        setAdvertencias(d.advertencias);
        setTimeout(() => alGuardar(d), 2500);
      } else alGuardar(d);
    }
  };

  const tipoElegido = catalogos.tipos_documentales.find((t) => String(t.id) === tipo);

  return (
    <form onSubmit={enviar} className="formulario">
      <Campo etiqueta="Archivo (PDF, JPG o PNG) *">
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setArchivo(f);
            if (f && !titulo) setTitulo(f.name.replace(/\.[^.]+$/, ""));
          }}
          required
        />
      </Campo>
      <div className="grilla">
        <Campo etiqueta="Tipo documental *">
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} required>
            <option value="">Elegir…</option>
            {catalogos.tipos_documentales.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
                {t.reservado ? " (reservado)" : ""}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Título *">
          <input value={titulo} onChange={(e) => setTitulo(e.target.value)} required maxLength={300} />
        </Campo>
        {!casoFijo && casos.length > 0 && (
          <Campo etiqueta="Caso">
            <select value={casoId} onChange={(e) => setCasoId(e.target.value)}>
              <option value="">Sin caso (documento del legajo)</option>
              {casos
                .filter((c) => !c.contenido_restringido)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.numero}
                  </option>
                ))}
            </select>
          </Campo>
        )}
        {expedientes.length > 0 && (
          <Campo etiqueta="Expediente">
            <select value={expedienteId} onChange={(e) => setExpedienteId(e.target.value)}>
              <option value="">Ninguno</option>
              {expedientes.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.numero}
                </option>
              ))}
            </select>
          </Campo>
        )}
        <Campo etiqueta="Descripción" ancho="completo">
          <textarea rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
        </Campo>
      </div>
      {tipoElegido?.reservado ? (
        <p className="tenue">Este tipo documental es reservado: solo lo verán quienes tengan acceso a información reservada o el caso asignado.</p>
      ) : (
        <label className="casilla">
          <input type="checkbox" checked={reservado} onChange={(e) => setReservado(e.target.checked)} />
          Documento reservado
        </label>
      )}
      {advertencias.map((a) => (
        <Aviso key={a} error={a} tipo="info" />
      ))}
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando || !archivo || advertencias.length > 0}>
          {enviando ? "Cargando…" : "Cargar documento"}
        </button>
      </div>
    </form>
  );
}

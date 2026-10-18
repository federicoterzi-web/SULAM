import { useState, type FormEvent } from "react";
import { api, type Caso, type Documento, type Expediente } from "../api";
import { VerTexto } from "./textos";
import { Aviso, Campo, Modal, Vacio, fecha, fechaHora, tamano, useEnvio, useSesion } from "../comun";

export function TablaDocumentos({
  documentos,
  alCambiar,
}: {
  documentos: Documento[];
  alCambiar?: () => void;
}) {
  const { puede } = useSesion();
  const [eliminar, setEliminar] = useState<Documento | null>(null);
  const [verTexto, setVerTexto] = useState<Documento | null>(null);
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
          {documentos.map((d) => (
              <tr key={d.id}>
                <td>
                  <strong>{d.titulo}</strong>
                  <br />
                  <small className="tenue">
                    {d.nombre_original} · {tamano(d.tamano)}
                  </small>
                  {d.descripcion && <div className="tenue">{d.descripcion}</div>}
                  <DatosDelDocumento d={d} />
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
                  <button className="boton boton-chico" onClick={() => setVerTexto(d)}>
                    Texto
                  </button>
                  {puede("documentos", "administrar") && alCambiar && (
                    <button className="boton boton-chico boton-peligro" onClick={() => setEliminar(d)}>
                      Dar de baja
                    </button>
                  )}
                </td>
              </tr>
          ))}
        </tbody>
      </table>
      {verTexto && <VerTexto documento={verTexto} alCerrar={() => setVerTexto(null)} />}
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

/** Datos que pide la plantilla del tipo. El vencimiento se avisa solo acá, dentro del legajo. */
function DatosDelDocumento({ d }: { d: Documento }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const etiquetas = new Map((d.tipo_documental.campos ?? []).map((c) => [c.clave, c]));
  const propios = Object.entries(d.datos ?? {}).filter(([k]) => etiquetas.has(k));
  if (!d.fecha_emision && !d.vence && !d.numero && propios.length === 0) return null;
  const vencido = !!d.vence && d.vence < hoy;
  return (
    <div className="doc-datos">
      {d.numero && <span>N° {d.numero}</span>}
      {d.fecha_emision && <span>Emitido {fecha(d.fecha_emision)}</span>}
      {d.vence && <span className={vencido ? "doc-vencido" : "doc-vigente"}>{vencido ? "Vencido el" : "Vence"} {fecha(d.vence)}</span>}
      {propios.map(([k, v]) => {
        const c = etiquetas.get(k)!;
        return (
          <span key={k}>
            {c.etiqueta}: {c.tipo === "fecha" ? fecha(v) : v}
          </span>
        );
      })}
    </div>
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
  const [advertencias, setAdvertencias] = useState<string[]>([]);
  const [emision, setEmision] = useState("");
  const [vence, setVence] = useState("");
  const [numero, setNumero] = useState("");
  const [propios, setPropios] = useState<Record<string, string>>({});
  const { enviando, error, ejecutar } = useEnvio();
  const tipoElegido = catalogos.tipos_documentales.find((t) => String(t.id) === tipo);

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
    if (emision) fd.append("fecha_emision", emision);
    if (tipoElegido?.tiene_vencimiento && vence) fd.append("vence", vence);
    if (tipoElegido?.usa_numero && numero) fd.append("numero", numero);
    if (Object.keys(propios).length) fd.append("datos", JSON.stringify(propios));
    const d = await ejecutar(() => api.post<Documento>("/documentos", fd));
    if (d) {
      if (d.advertencias?.length) {
        setAdvertencias(d.advertencias);
        setTimeout(() => alGuardar(d), 2500);
      } else alGuardar(d);
    }
  };

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
          <select
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value);
              setPropios({});
              setVence("");
            }}
            required
          >
            <option value="">Elegir…</option>
            {catalogos.tipos_documentales.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
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
              {casos.map((c) => (
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
        {tipoElegido && (tipoElegido.tiene_vencimiento || tipoElegido.usa_numero || tipoElegido.campos.length > 0) && (
          <>
            <Campo etiqueta="Fecha de emisión">
              <input
                type="date"
                value={emision}
                onChange={(e) => {
                  setEmision(e.target.value);
                  if (tipoElegido.tiene_vencimiento && tipoElegido.vigencia_dias && e.target.value) {
                    const d = new Date(e.target.value + "T12:00:00");
                    d.setDate(d.getDate() + tipoElegido.vigencia_dias);
                    setVence(d.toISOString().slice(0, 10));
                  }
                }}
              />
            </Campo>
            {tipoElegido.tiene_vencimiento && (
              <Campo etiqueta="Vence">
                <input type="date" value={vence} onChange={(e) => setVence(e.target.value)} />
              </Campo>
            )}
            {tipoElegido.usa_numero && (
              <Campo etiqueta="Número o código">
                <input value={numero} maxLength={100} onChange={(e) => setNumero(e.target.value)} />
              </Campo>
            )}
            {tipoElegido.campos.map((c) => (
              <Campo key={c.clave} etiqueta={c.etiqueta}>
                <input
                  type={c.tipo === "fecha" ? "date" : "text"}
                  maxLength={300}
                  value={propios[c.clave] ?? ""}
                  onChange={(e) => setPropios({ ...propios, [c.clave]: e.target.value })}
                />
              </Campo>
            ))}
          </>
        )}
        <Campo etiqueta="Descripción" ancho="completo">
          <textarea rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
        </Campo>
      </div>
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

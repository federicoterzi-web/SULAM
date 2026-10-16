import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, type Coincidencia, type PersonaDetalle, type PersonaResumen } from "../api";
import {
  Aviso,
  Campo,
  Enlace,
  Modal,
  Seccion,
  Vacio,
  documento,
  edad,
  fecha,
  navegar,
  nombre,
  useEnvio,
  useSesion,
} from "../comun";

export function PaginaLegajos() {
  const { puede } = useSesion();
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<PersonaResumen[] | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const { enviando, error, ejecutar } = useEnvio();

  const buscar = async (e?: FormEvent) => {
    e?.preventDefault();
    const r = await ejecutar(() => api.get<PersonaResumen[]>("/personas", { q, limite: 50 }));
    if (r) setResultados(r);
  };

  return (
    <>
      <div className="titulo-pagina">
        <h1>Legajos</h1>
        {puede("personas", "crear") && (
          <button className="boton boton-primario" onClick={() => setNuevo(true)}>
            Nuevo legajo
          </button>
        )}
      </div>
      <form className="buscador" onSubmit={buscar}>
        <input
          type="search"
          autoFocus
          placeholder="Apellido y/o nombre, número de documento o número de legajo"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Buscar legajo"
        />
        <button className="boton boton-primario" disabled={enviando}>
          Buscar
        </button>
      </form>
      <Aviso error={error} />
      {resultados && <ListaPersonas personas={resultados} />}
      {nuevo && (
        <Modal titulo="Nuevo legajo" alCerrar={() => setNuevo(false)} ancho>
          <FormPersona
            alGuardar={(p) => {
              setNuevo(false);
              navegar(`/legajos/${p.id}`);
            }}
            alCancelar={() => setNuevo(false)}
          />
        </Modal>
      )}
    </>
  );
}

export function ListaPersonas({ personas, alElegir }: { personas: PersonaResumen[]; alElegir?: (p: PersonaResumen) => void }) {
  if (personas.length === 0) return <Vacio>No se encontraron legajos.</Vacio>;
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Legajo</th>
          <th>Apellidos y nombres</th>
          <th>Documento</th>
          <th>Nacimiento</th>
          <th>Localidad</th>
          {alElegir && <th></th>}
        </tr>
      </thead>
      <tbody>
        {personas.map((p) => (
          <tr key={p.id}>
            <td>
              <Enlace a={`/legajos/${p.id}`}>{p.numero_legajo}</Enlace>
            </td>
            <td>
              <Enlace a={`/legajos/${p.id}`}>{nombre(p)}</Enlace>
            </td>
            <td>{documento(p)}</td>
            <td>
              {fecha(p.fecha_nacimiento)}
              {p.fecha_nacimiento && ` (${p.fecha_nacimiento_aproximada ? "aprox. " : ""}${edad(p.fecha_nacimiento)} años)`}
            </td>
            <td>{p.localidad ?? "—"}</td>
            {alElegir && (
              <td>
                <button type="button" className="boton boton-chico" onClick={() => alElegir(p)}>
                  Elegir
                </button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const TIPOS_DOC = ["DNI", "LC", "LE", "CI", "Pasaporte", "Otro"];

interface DatosPersona {
  apellidos: string;
  nombres: string;
  tipo_documento: string;
  numero_documento: string;
  sin_documento: boolean;
  motivo_sin_documento: string;
  fecha_nacimiento: string;
  fecha_nacimiento_aproximada: boolean;
  domicilio: string;
  localidad: string;
  telefono: string;
  observaciones: string;
}

function inicial(p?: PersonaDetalle, sugerido?: Partial<DatosPersona>): DatosPersona {
  return {
    ...valoresVacios(),
    ...sugerido,
    ...(p ? desdePersona(p) : {}),
  };
}

function valoresVacios(): DatosPersona {
  return desdePersona(undefined);
}

function desdePersona(p?: PersonaDetalle): DatosPersona {
  return {
    apellidos: p?.apellidos ?? "",
    nombres: p?.nombres ?? "",
    tipo_documento: p?.tipo_documento ?? "DNI",
    numero_documento: p?.numero_documento ?? "",
    sin_documento: p?.sin_documento ?? false,
    motivo_sin_documento: p?.motivo_sin_documento ?? "",
    fecha_nacimiento: p?.fecha_nacimiento ?? "",
    fecha_nacimiento_aproximada: p?.fecha_nacimiento_aproximada ?? false,
    domicilio: p?.domicilio ?? "",
    localidad: p?.localidad ?? "",
    telefono: p?.telefono ?? "",
    observaciones: p?.observaciones ?? "",
  };
}

export function FormPersona({
  persona,
  sugerido,
  alGuardar,
  alCancelar,
}: {
  persona?: PersonaDetalle;
  sugerido?: Partial<DatosPersona>;
  alGuardar: (p: PersonaDetalle) => void;
  alCancelar: () => void;
}) {
  const [d, setD] = useState<DatosPersona>(inicial(persona, sugerido));
  const [coincidencias, setCoincidencias] = useState<Coincidencia[]>([]);
  const [confirmado, setConfirmado] = useState(false);
  const [motivoConfirmacion, setMotivoConfirmacion] = useState("");
  const [motivoCambio, setMotivoCambio] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  const cambia = (k: keyof DatosPersona) => (e: { target: { value: string; type?: string; checked?: boolean } }) =>
    setD((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  // Aviso temprano de posibles duplicados mientras se completa el formulario.
  useEffect(() => {
    if (d.apellidos.trim().length < 2 || d.nombres.trim().length < 2) return;
    const t = setTimeout(() => {
      api
        .post<{ coincidencias: Coincidencia[] }>("/personas/verificar-duplicados", {
          apellidos: d.apellidos,
          nombres: d.nombres,
          tipo_documento: d.sin_documento ? null : d.tipo_documento,
          numero_documento: d.sin_documento ? null : d.numero_documento || null,
          fecha_nacimiento: d.fecha_nacimiento || null,
          fecha_nacimiento_aproximada: d.fecha_nacimiento_aproximada,
          excluir_id: persona?.id ?? null,
        })
        .then((r) => setCoincidencias(r.coincidencias))
        .catch(() => {});
    }, 600);
    return () => clearTimeout(t);
  }, [d.apellidos, d.nombres, d.tipo_documento, d.numero_documento, d.sin_documento, d.fecha_nacimiento, d.fecha_nacimiento_aproximada, persona?.id]);

  const docOriginal = persona?.numero_documento ?? "";
  const corrigeDocumento = !!persona && !!docOriginal && d.numero_documento.replace(/\D/g, "") !== docOriginal.replace(/\D/g, "");

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo: Record<string, unknown> = {
      apellidos: d.apellidos,
      nombres: d.nombres,
      sin_documento: d.sin_documento,
      tipo_documento: d.sin_documento || !d.numero_documento ? null : d.tipo_documento,
      numero_documento: d.sin_documento ? null : d.numero_documento || null,
      motivo_sin_documento: d.sin_documento ? d.motivo_sin_documento : null,
      fecha_nacimiento: d.fecha_nacimiento || null,
      fecha_nacimiento_aproximada: d.fecha_nacimiento_aproximada,
      domicilio: d.domicilio,
      localidad: d.localidad,
      telefono: d.telefono,
      observaciones: d.observaciones,
      confirmar_posible_duplicado: confirmado,
    };
    if (persona) cuerpo.motivo_cambio = motivoCambio || null;
    else cuerpo.motivo_confirmacion = confirmado ? motivoConfirmacion : null;
    const r = await ejecutar(async () => {
        try {
          return persona
            ? await api.patch<PersonaDetalle>(`/personas/${persona.id}`, cuerpo)
            : await api.post<PersonaDetalle>("/personas", cuerpo);
        } catch (err) {
          if (err instanceof ApiError && err.status === 409 && err.detalle?.coincidencias) {
            setCoincidencias(err.detalle.coincidencias);
          }
          throw err;
        }
      });
    if (r) alGuardar(r);
  };

  const bloqueante = coincidencias.some((c) => c.nivel === "bloqueante");
  const ini = inicial(persona);
  const cambioIdentidad =
    !persona ||
    (["apellidos", "nombres", "numero_documento", "tipo_documento", "fecha_nacimiento"] as const).some((k) => d[k] !== ini[k]);
  const requiereConfirmar = coincidencias.length > 0 && !bloqueante && cambioIdentidad;

  return (
    <form onSubmit={enviar} className="formulario">
      <div className="grilla">
        <Campo etiqueta="Apellidos *">
          <input value={d.apellidos} onChange={cambia("apellidos")} required maxLength={200} autoFocus />
        </Campo>
        <Campo etiqueta="Nombres *">
          <input value={d.nombres} onChange={cambia("nombres")} required maxLength={200} />
        </Campo>
        <label className="casilla campo-completo">
          <input type="checkbox" checked={d.sin_documento} onChange={cambia("sin_documento")} />
          La persona no tiene documento o no se conoce el número
        </label>
        {d.sin_documento ? (
          <Campo etiqueta="Motivo / situación del documento" ancho="completo">
            <input value={d.motivo_sin_documento} onChange={cambia("motivo_sin_documento")} placeholder="Ej.: extraviado, en trámite, no informado" />
          </Campo>
        ) : (
          <>
            <Campo etiqueta="Tipo de documento">
              <select value={d.tipo_documento} onChange={cambia("tipo_documento")}>
                {TIPOS_DOC.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Campo>
            <Campo etiqueta="Número de documento" ayuda="Sin puntos ni espacios (se quitan solos).">
              <input value={d.numero_documento} onChange={cambia("numero_documento")} inputMode="numeric" maxLength={30} />
            </Campo>
          </>
        )}
        {corrigeDocumento && (
          <Campo etiqueta="Motivo de la corrección del documento *" ancho="completo">
            <input value={motivoCambio} onChange={(e) => setMotivoCambio(e.target.value)} required />
          </Campo>
        )}
        <Campo etiqueta="Fecha de nacimiento">
          <input type="date" value={d.fecha_nacimiento} onChange={cambia("fecha_nacimiento")} max={new Date().toISOString().slice(0, 10)} />
        </Campo>
        <label className="casilla">
          <input type="checkbox" checked={d.fecha_nacimiento_aproximada} onChange={cambia("fecha_nacimiento_aproximada")} />
          Fecha aproximada
        </label>
        <Campo etiqueta="Domicilio" ancho="completo">
          <input value={d.domicilio} onChange={cambia("domicilio")} />
        </Campo>
        <Campo etiqueta="Localidad">
          <input value={d.localidad} onChange={cambia("localidad")} />
        </Campo>
        <Campo etiqueta="Teléfono">
          <input value={d.telefono} onChange={cambia("telefono")} />
        </Campo>
        <Campo etiqueta="Observaciones" ancho="completo">
          <textarea rows={3} value={d.observaciones} onChange={cambia("observaciones")} />
        </Campo>
      </div>

      {coincidencias.length > 0 && cambioIdentidad && (
        <div className={`aviso ${bloqueante ? "aviso-error" : "aviso-advertencia"}`}>
          <strong>{bloqueante ? "Ya existe un legajo con ese documento." : "Posibles legajos de la misma persona:"}</strong>
          <ul className="lista-coincidencias">
            {coincidencias.map((c) => (
              <li key={c.persona.id}>
                <a href={`#/legajos/${c.persona.id}`} target="_blank" rel="noreferrer">
                  {c.persona.numero_legajo} · {nombre(c.persona)}
                </a>{" "}
                — {documento(c.persona)}, nac. {fecha(c.persona.fecha_nacimiento)}
                <br />
                <small>
                  Coincidencia {c.nivel}: {c.motivos.join("; ")}
                </small>
              </li>
            ))}
          </ul>
          {!bloqueante && requiereConfirmar && (
            <>
              <label className="casilla">
                <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} />
                Revisé los legajos indicados y se trata de otra persona
              </label>
              {confirmado && !persona && (
                <Campo etiqueta="¿Cómo lo verificó?">
                  <input value={motivoConfirmacion} onChange={(e) => setMotivoConfirmacion(e.target.value)} placeholder="Ej.: distinta fecha de nacimiento confirmada con la familia" />
                </Campo>
              )}
            </>
          )}
        </div>
      )}

      <Aviso error={error instanceof ApiError && error.detalle?.coincidencias ? null : error} />
      <div className="fila-botones">
        <button type="button" className="boton" onClick={alCancelar}>
          Cancelar
        </button>
        <button className="boton boton-primario" disabled={enviando || bloqueante || (requiereConfirmar && !confirmado)}>
          {persona ? "Guardar cambios" : "Crear legajo"}
        </button>
      </div>
    </form>
  );
}

export function SelectorPersona({ alElegir }: { alElegir: (p: PersonaResumen) => void }) {
  const [q, setQ] = useState("");
  const [r, setR] = useState<PersonaResumen[] | null>(null);
  const { error, ejecutar } = useEnvio();
  const buscar = async (e: FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const x = await ejecutar(() => api.get<PersonaResumen[]>("/personas", { q, limite: 20 }));
    if (x) setR(x);
  };
  return (
    <Seccion titulo="Buscar legajo">
      <form className="buscador" onSubmit={buscar}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Apellido, documento o N° de legajo" autoFocus />
        <button className="boton">Buscar</button>
      </form>
      <Aviso error={error} />
      {r && <ListaPersonas personas={r} alElegir={alElegir} />}
    </Seccion>
  );
}

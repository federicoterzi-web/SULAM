// Articulación con otras instituciones en un caso. Cada contacto nuevo que se
// registra acá entra al directorio institucional (origen: articulación en un caso).
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Modal, Seccion, Vacio, fecha, useDatos, useEnvio } from "../comun";
import { categoriasInstitucion, type Contacto } from "./contactos";
import { telefonoLimpio, useCatalogoRecursos } from "./recursos";

export interface Articulacion {
  id: number;
  fecha: string;
  motivo: string | null;
  resultado: string | null;
  contacto: Contacto | null;
  recurso: { id: string; nombre: string; tipo: string } | null;
  usuario: { nombre_completo: string } | null;
}

function hoy() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function SeccionArticulaciones({ casoId, puedeAgregar }: { casoId: string; puedeAgregar: boolean }) {
  const lista = useDatos(() => api.get<Articulacion[]>(`/casos/${casoId}/articulaciones`), [casoId]);
  const [nueva, setNueva] = useState(false);
  return (
    <Seccion
      titulo="Articulación con otras instituciones"
      acciones={
        puedeAgregar && (
          <button className="boton" onClick={() => setNueva(true)}>
            Registrar articulación
          </button>
        )
      }
    >
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <Vacio>Sin articulaciones registradas. Las personas de contacto que se agreguen acá quedan en el directorio institucional.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Con quién</th>
              <th>Motivo</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {lista.datos.map((a) => (
              <tr key={a.id}>
                <td>{fecha(a.fecha)}</td>
                <td>
                  {a.contacto ? (
                    <>
                      <strong>{a.contacto.nombre}</strong>
                      <div className="tenue">{[a.contacto.cargo, a.contacto.institucion].filter(Boolean).join(" · ")}</div>
                      {a.contacto.telefono && <a href={`tel:${telefonoLimpio(a.contacto.telefono)}`}>{a.contacto.telefono}</a>}
                    </>
                  ) : (
                    a.recurso && <strong>{a.recurso.nombre}</strong>
                  )}
                </td>
                <td>{a.motivo ?? "—"}</td>
                <td>
                  {a.resultado ?? "—"}
                  {a.usuario && <div className="tenue">Registró: {a.usuario.nombre_completo}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {nueva && (
        <Modal titulo="Registrar articulación" alCerrar={() => setNueva(false)} ancho>
          <FormArticulacion
            casoId={casoId}
            alGuardar={() => {
              setNueva(false);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </Seccion>
  );
}

export function FormArticulacion({ casoId, alGuardar }: { casoId: string; alGuardar: () => void }) {
  const cat = useCatalogoRecursos();
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<Contacto[] | null>(null);
  const [elegido, setElegido] = useState<Contacto | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [c, setC] = useState({ nombre: "", cargo: "", institucion: "", categoria: "", telefono: "", whatsapp: "" });
  const [d, setD] = useState({ fecha: hoy(), motivo: "", resultado: "" });
  const { enviando, error, ejecutar } = useEnvio();

  useEffect(() => {
    if (q.trim().length < 2) {
      setResultados(null);
      return;
    }
    const t = setTimeout(() => {
      api
        .get<Contacto[]>("/contactos", { q: q.trim() })
        .then((r) => setResultados(r.slice(0, 8)))
        .catch(() => setResultados([]));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  if (!cat.datos) return cat.error ? <Aviso error={cat.error} /> : <Cargando />;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = {
      ...d,
      motivo: d.motivo || null,
      resultado: d.resultado || null,
      contacto_id: !nuevo && elegido ? elegido.id : null,
      nuevo_contacto: nuevo ? { ...c, categoria: c.categoria || null } : null,
    };
    const r = await ejecutar(() => api.post(`/casos/${casoId}/articulaciones`, cuerpo));
    if (r) alGuardar();
  };

  return (
    <form onSubmit={enviar} className="formulario">
      {!nuevo ? (
        <>
          {elegido ? (
            <div className="aviso aviso-info">
              <strong>{elegido.nombre}</strong> · {[elegido.cargo, elegido.institucion].filter(Boolean).join(" · ")}{" "}
              <button type="button" className="boton-enlace" onClick={() => setElegido(null)}>
                cambiar
              </button>
            </div>
          ) : (
            <>
              <Campo etiqueta="¿Con quién se articuló?" ayuda="Busque en el directorio por nombre, institución o localidad.">
                <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus placeholder="Ej.: comuna de Lules, defensoría…" />
              </Campo>
              {resultados && (
                <ul className="resultados-busqueda">
                  {resultados.map((x) => (
                    <li key={x.id}>
                      <button type="button" className="boton-enlace" onClick={() => setElegido(x)}>
                        {x.nombre}
                      </button>{" "}
                      <span className="tenue">{[x.cargo, x.institucion, x.departamento].filter(Boolean).join(" · ")}</span>
                    </li>
                  ))}
                  {resultados.length === 0 && <li className="tenue">No está en el directorio.</li>}
                </ul>
              )}
              <button type="button" className="boton boton-chico" onClick={() => setNuevo(true)}>
                No está en el directorio: agregarlo
              </button>
            </>
          )}
        </>
      ) : (
        <>
          <p className="tenue">Se agrega al directorio de contactos, con origen «Articulación en un caso».</p>
          <div className="grilla">
            <Campo etiqueta="Apellido y nombre *">
              <input value={c.nombre} onChange={(e) => setC({ ...c, nombre: e.target.value })} required minLength={2} autoFocus />
            </Campo>
            <Campo etiqueta="Cargo o función">
              <input value={c.cargo} onChange={(e) => setC({ ...c, cargo: e.target.value })} />
            </Campo>
            <Campo etiqueta="Institución">
              <input value={c.institucion} onChange={(e) => setC({ ...c, institucion: e.target.value })} />
            </Campo>
            <Campo etiqueta="Tipo de institución">
              <select value={c.categoria} onChange={(e) => setC({ ...c, categoria: e.target.value })}>
                <option value="">—</option>
                {categoriasInstitucion(cat.datos).map((x) => (
                  <option key={x.codigo} value={x.codigo}>
                    {x.texto}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo etiqueta="Teléfono">
              <input type="tel" value={c.telefono} onChange={(e) => setC({ ...c, telefono: e.target.value })} />
            </Campo>
            <Campo etiqueta="WhatsApp">
              <input type="tel" value={c.whatsapp} onChange={(e) => setC({ ...c, whatsapp: e.target.value })} placeholder="381 15 400-1111" />
            </Campo>
          </div>
          <button type="button" className="boton-enlace" onClick={() => setNuevo(false)}>
            Buscar en el directorio
          </button>
        </>
      )}
      <div className="grilla">
        <Campo etiqueta="Fecha">
          <input type="date" value={d.fecha} max={hoy()} onChange={(e) => setD({ ...d, fecha: e.target.value })} required />
        </Campo>
      </div>
      <Campo etiqueta="Motivo">
        <textarea rows={2} value={d.motivo} onChange={(e) => setD({ ...d, motivo: e.target.value })} placeholder="Qué se pidió o se coordinó" />
      </Campo>
      <Campo etiqueta="Resultado">
        <textarea rows={2} value={d.resultado} onChange={(e) => setD({ ...d, resultado: e.target.value })} />
      </Campo>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando || (!nuevo && !elegido)}>
          Registrar
        </button>
      </div>
    </form>
  );
}

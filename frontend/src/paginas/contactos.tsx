// Directorio de contactos: técnicos de gobiernos locales y referentes de instituciones.
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Enlace, Modal, Vacio, useDatos, useEnvio, useSesion } from "../comun";
import { CampoOrigen, telefonoLimpio, textoOrigen, useCatalogoRecursos, type CatalogoRecursos } from "./recursos";

export interface Contacto {
  id: string;
  nombre: string;
  cargo: string | null;
  institucion: string | null;
  categoria: string | null;
  recurso_id: string | null;
  recurso: { id: string; nombre: string; tipo: string } | null;
  localidad: string | null;
  departamento: string | null;
  telefono: string | null;
  telefono_alternativo: string | null;
  whatsapp: string | null;
  email: string | null;
  temas: string | null;
  observaciones: string | null;
  origen: string | null;
  origen_detalle: string | null;
  articulaciones: number;
  activo: boolean;
  creado_por: string | null;
}

export function categoriasInstitucion(cat: CatalogoRecursos) {
  return cat.tipos.find((t) => t.codigo === "institucion")?.categorias ?? [];
}

export function enlaceWhatsapp(numero: string) {
  return `https://wa.me/${numero}`;
}

export function PaginaContactos() {
  const cat = useCatalogoRecursos();
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const [departamento, setDepartamento] = useState("");
  const [categoria, setCategoria] = useState("");
  const [editar, setEditar] = useState<Contacto | "nuevo" | null>(null);
  const lista = useDatos(
    () => api.get<Contacto[]>("/contactos", { q: filtroQ, departamento: departamento || undefined, categoria: categoria || undefined }),
    [filtroQ, departamento, categoria],
  );
  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  const c = cat.datos;
  return (
    <>
      <div className="inicio-cabecera">
        <h1>Contactos</h1>
        {c.puede.crear && (
          <button className="boton boton-primario" onClick={() => setEditar("nuevo")}>
            Agregar contacto
          </button>
        )}
      </div>
      <p className="tenue">
        Técnicos de municipios y comunas y referentes de otras instituciones con las que se articula. Los lugares están en{" "}
        <Enlace a="/recursos">Recursos y mapa</Enlace>.
      </p>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltroQ(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre, institución, cargo, localidad o tema" aria-label="Buscar contacto" />
        <select value={departamento} onChange={(e) => setDepartamento(e.target.value)} aria-label="Departamento">
          <option value="">Todos los departamentos</option>
          {c.departamentos.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
        <select value={categoria} onChange={(e) => setCategoria(e.target.value)} aria-label="Tipo de institución">
          <option value="">Todas las instituciones</option>
          {categoriasInstitucion(c).map((x) => (
            <option key={x.codigo} value={x.codigo}>
              {x.texto}
            </option>
          ))}
        </select>
        <button className="boton">Buscar</button>
      </form>
      <Aviso error={lista.error} />
      {!lista.datos ? <Cargando /> : <TablaContactos contactos={lista.datos} cat={c} alEditar={setEditar} />}
      {editar && (
        <Modal titulo={editar === "nuevo" ? "Agregar contacto" : editar.nombre} alCerrar={() => setEditar(null)} ancho>
          <FormContacto
            cat={c}
            contacto={editar === "nuevo" ? undefined : editar}
            alGuardar={() => {
              setEditar(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

export function TablaContactos({ contactos, cat, alEditar }: { contactos: Contacto[]; cat: CatalogoRecursos; alEditar?: (c: Contacto) => void }) {
  const { yo } = useSesion();
  if (contactos.length === 0) return <Vacio>No hay contactos cargados.</Vacio>;
  const puede = (c: Contacto) => cat.puede.modificar === "todos" || (cat.puede.modificar === "propios" && c.creado_por === yo.id);
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Contacto</th>
          <th>Institución</th>
          <th>Teléfono</th>
          <th>Temas</th>
          {alEditar && <th />}
        </tr>
      </thead>
      <tbody>
        {contactos.map((x) => (
          <tr key={x.id}>
            <td>
              <strong>{x.nombre}</strong>
              {x.cargo && <div className="tenue">{x.cargo}</div>}
              {textoOrigen(cat, x) && <div className="tenue origen">Origen: {textoOrigen(cat, x)}</div>}
              {x.articulaciones > 0 && (
                <div className="tenue">
                  Articulado en {x.articulaciones} {x.articulaciones === 1 ? "caso" : "casos"}
                </div>
              )}
            </td>
            <td>
              {x.recurso ? <Enlace a={`/recursos/${x.recurso.id}`}>{x.institucion ?? x.recurso.nombre}</Enlace> : x.institucion ?? "—"}
              {(x.localidad || x.departamento) && <div className="tenue">{[x.localidad, x.departamento].filter(Boolean).join(", ")}</div>}
            </td>
            <td className="celda-contacto">
              {x.telefono && <a href={`tel:${telefonoLimpio(x.telefono)}`}>{x.telefono}</a>}
              {x.telefono_alternativo && <a href={`tel:${telefonoLimpio(x.telefono_alternativo)}`}>{x.telefono_alternativo}</a>}
              {x.whatsapp && (
                <a href={enlaceWhatsapp(x.whatsapp)} target="_blank" rel="noreferrer">
                  WhatsApp
                </a>
              )}
              {x.email && <a href={`mailto:${x.email}`}>{x.email}</a>}
            </td>
            <td>{x.temas ?? ""}</td>
            {alEditar && (
              <td>
                {puede(x) && (
                  <button className="boton boton-chico" onClick={() => alEditar(x)}>
                    Editar
                  </button>
                )}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FormContacto({
  cat,
  contacto,
  recurso,
  alGuardar,
}: {
  cat: CatalogoRecursos;
  contacto?: Contacto;
  recurso?: { id: string; nombre: string; categoria: string | null; departamento: string | null; localidad: string | null };
  alGuardar: () => void;
}) {
  const [d, setD] = useState({
    nombre: contacto?.nombre ?? "",
    cargo: contacto?.cargo ?? "",
    institucion: contacto?.institucion ?? recurso?.nombre ?? "",
    categoria: contacto?.categoria ?? recurso?.categoria ?? "",
    localidad: contacto?.localidad ?? recurso?.localidad ?? "",
    departamento: contacto?.departamento ?? recurso?.departamento ?? "",
    telefono: contacto?.telefono ?? "",
    telefono_alternativo: contacto?.telefono_alternativo ?? "",
    whatsapp: contacto?.whatsapp ?? "",
    email: contacto?.email ?? "",
    temas: contacto?.temas ?? "",
    observaciones: contacto?.observaciones ?? "",
    origen: contacto?.origen ?? (recurso ? "relevamiento" : ""),
    origen_detalle: contacto?.origen_detalle ?? "",
    activo: contacto?.activo ?? true,
  });
  const { enviando, error, ejecutar } = useEnvio();
  const set = (c: Partial<typeof d>) => setD({ ...d, ...c });
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = { ...d, recurso_id: contacto?.recurso_id ?? recurso?.id ?? null };
    const r = await ejecutar(() => (contacto ? api.patch(`/contactos/${contacto.id}`, cuerpo) : api.post("/contactos", cuerpo)));
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <div className="grilla">
        <Campo etiqueta="Apellido y nombre *">
          <input value={d.nombre} onChange={(e) => set({ nombre: e.target.value })} required minLength={2} autoFocus />
        </Campo>
        <Campo etiqueta="Cargo o función">
          <input value={d.cargo} onChange={(e) => set({ cargo: e.target.value })} placeholder="Ej.: trabajadora social" />
        </Campo>
        <Campo etiqueta="Institución">
          <input value={d.institucion} onChange={(e) => set({ institucion: e.target.value })} placeholder="Ej.: Municipalidad de …" />
        </Campo>
        <Campo etiqueta="Tipo de institución">
          <select value={d.categoria} onChange={(e) => set({ categoria: e.target.value })}>
            <option value="">—</option>
            {categoriasInstitucion(cat).map((x) => (
              <option key={x.codigo} value={x.codigo}>
                {x.texto}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Localidad">
          <input value={d.localidad} onChange={(e) => set({ localidad: e.target.value })} />
        </Campo>
        <Campo etiqueta="Departamento">
          <select value={d.departamento} onChange={(e) => set({ departamento: e.target.value })}>
            <option value="">—</option>
            {cat.departamentos.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Teléfono">
          <input type="tel" value={d.telefono} onChange={(e) => set({ telefono: e.target.value })} />
        </Campo>
        <Campo etiqueta="Otro teléfono">
          <input type="tel" value={d.telefono_alternativo} onChange={(e) => set({ telefono_alternativo: e.target.value })} />
        </Campo>
        <Campo etiqueta="WhatsApp" ayuda="Característica y número, como se marca en Tucumán: 381 15 400-1111.">
          <input type="tel" value={d.whatsapp} onChange={(e) => set({ whatsapp: e.target.value })} />
        </Campo>
        <Campo etiqueta="Correo">
          <input type="email" value={d.email} onChange={(e) => set({ email: e.target.value })} />
        </Campo>
      </div>
      <Campo etiqueta="Temas con los que se articula">
        <input value={d.temas} onChange={(e) => set({ temas: e.target.value })} placeholder="Ej.: subsidios, PAMI, salud mental, violencia" />
      </Campo>
      <Campo etiqueta="Observaciones">
        <textarea rows={2} value={d.observaciones} onChange={(e) => set({ observaciones: e.target.value })} />
      </Campo>
      <CampoOrigen cat={cat} origen={d.origen} detalle={d.origen_detalle} alCambiar={(o, det) => set({ origen: o, origen_detalle: det })} />
      {contacto && (
        <label className="casilla">
          <input type="checkbox" checked={!d.activo} onChange={(e) => set({ activo: !e.target.checked })} />
          Ya no trabaja ahí (se da de baja; no se borra)
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

/** Contactos de un recurso (en su ficha). */
export function ContactosDelRecurso({ cat, recurso }: { cat: CatalogoRecursos; recurso: { id: string; nombre: string; categoria: string | null; departamento: string | null; localidad: string | null } }) {
  const lista = useDatos(() => api.get<Contacto[]>("/contactos", { recurso_id: recurso.id }), [recurso.id]);
  const [editar, setEditar] = useState<Contacto | "nuevo" | null>(null);
  return (
    <>
      {!lista.datos ? <Cargando /> : <TablaContactos contactos={lista.datos} cat={cat} alEditar={setEditar} />}
      {cat.puede.crear && (
        <button className="boton boton-chico" onClick={() => setEditar("nuevo")}>
          Agregar contacto
        </button>
      )}
      {editar && (
        <Modal titulo={editar === "nuevo" ? `Contacto en ${recurso.nombre}` : editar.nombre} alCerrar={() => setEditar(null)} ancho>
          <FormContacto
            cat={cat}
            contacto={editar === "nuevo" ? undefined : editar}
            recurso={recurso}
            alGuardar={() => {
              setEditar(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

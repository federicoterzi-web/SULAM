// Red de recursos: centros, instituciones y cuidadores, en lista y en el mapa.
import { useMemo, useState, type FormEvent } from "react";
import { BarraFiltros, parametroF, useFiltrosUrl } from "./filtros";
import { api } from "../api";
import { Aviso, Campo, Cargando, Enlace, Seccion, Vacio, fechaHora, navegar, useDatos, useEnvio, useSesion } from "../comun";
import { MapaRecursos, MapaSelector, enlaceComoLlegar, type ConfigMapa, type Punto } from "../mapa";
import { ContactosDelRecurso } from "./contactos";
import { DocumentacionDelRecurso, PersonasInternadas } from "./residencias";
import { ubicacionActual } from "./ubicacion";

export interface TipoRecurso {
  codigo: string;
  texto: string;
  categorias?: { codigo: string; texto: string }[];
}

export interface CatalogoRecursos {
  tipos: TipoRecurso[];
  origenes: { codigo: string; texto: string }[];
  departamentos: string[];
  mapa: ConfigMapa;
  geocodificador: boolean;
  puede: { crear: boolean; modificar: string | null };
}

export interface Recurso {
  id: string;
  tipo: string;
  categoria: string | null;
  nombre: string;
  direccion: string | null;
  localidad: string | null;
  departamento: string | null;
  lat: number | null;
  lng: number | null;
  telefono: string | null;
  telefono_alternativo: string | null;
  email: string | null;
  horario: string | null;
  referente: string | null;
  referente_cargo: string | null;
  servicios: string | null;
  observaciones: string | null;
  zonas: string[];
  formacion: string | null;
  disponibilidad: string | null;
  origen: string | null;
  origen_detalle: string | null;
  activo: boolean;
  creado_por: string | null;
  actualizado_en: string | null;
}

export function textoTipo(cat: CatalogoRecursos, r: Pick<Recurso, "tipo" | "categoria">): string {
  const t = cat.tipos.find((x) => x.codigo === r.tipo);
  const c = t?.categorias?.find((x) => x.codigo === r.categoria);
  return c ? c.texto : t?.texto ?? r.tipo;
}

export function telefonoLimpio(t: string) {
  return t.replace(/[^\d+]/g, "");
}

export function textoOrigen(cat: CatalogoRecursos, x: { origen: string | null; origen_detalle: string | null }): string | null {
  if (!x.origen && !x.origen_detalle) return null;
  const t = cat.origenes.find((o) => o.codigo === x.origen)?.texto;
  return [t, x.origen_detalle].filter(Boolean).join(" · ");
}

/** De dónde salió el dato: alimenta la base institucional desde todas las fuentes. */
export function CampoOrigen({
  cat,
  origen,
  detalle,
  alCambiar,
}: {
  cat: CatalogoRecursos;
  origen: string;
  detalle: string;
  alCambiar: (origen: string, detalle: string) => void;
}) {
  return (
    <div className="grilla">
      <Campo etiqueta="Cómo se obtuvo el dato">
        <select value={origen} onChange={(e) => alCambiar(e.target.value, detalle)}>
          <option value="">—</option>
          {cat.origenes.map((o) => (
            <option key={o.codigo} value={o.codigo}>
              {o.texto}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta="Detalle" ayuda="Ej.: nombre y fecha de la capacitación, caso, nota recibida.">
        <input value={detalle} onChange={(e) => alCambiar(origen, e.target.value)} />
      </Campo>
    </div>
  );
}

export function useCatalogoRecursos() {
  return useDatos(() => api.get<CatalogoRecursos>("/recursos/catalogo"), []);
}

// ---------------------------------------------------------------- listado + mapa

export function PaginaRecursos() {
  const cat = useCatalogoRecursos();
  const [tipos, setTipos] = useState<string[]>([]);
  const [departamento, setDepartamento] = useState("");
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const [elegido, setElegido] = useState<string | null>(null);
  const [filtros, setFiltros] = useFiltrosUrl();
  const [total, setTotal] = useState<number | null>(null);
  const lista = useDatos(async () => {
    const r = await api.get<{ total: number; items: Recurso[] }>("/recursos", {
      tipo: tipos.join(",") || undefined, departamento: departamento || undefined, q: filtroQ, con_total: true, f: parametroF(filtros),
    });
    setTotal(r.total);
    return r.items;
  }, [tipos.join(","), departamento, filtroQ, JSON.stringify(filtros)]);
  const puntos = useMemo<Punto[]>(
    () =>
      (lista.datos ?? [])
        .filter((r) => r.lat !== null && r.lng !== null)
        .map((r) => ({ id: r.id, lat: r.lat!, lng: r.lng!, tipo: r.tipo, titulo: r.nombre })),
    [lista.datos],
  );

  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  const c = cat.datos;
  const sinUbicacion = (lista.datos ?? []).filter((r) => r.lat === null).length;
  const alternar = (t: string) => setTipos(tipos.includes(t) ? tipos.filter((x) => x !== t) : [...tipos, t]);

  return (
    <>
      <div className="inicio-cabecera">
        <h1>Recursos</h1>
        {c.puede.crear && (
          <Enlace a="/recursos/nuevo" className="boton boton-primario">
            Agregar recurso
          </Enlace>
        )}
      </div>
      <p className="tenue">Centros de día, centros de jubilados, residencias, instituciones con las que se articula y cuidadores domiciliarios formados.</p>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltroQ(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre, localidad, referente o servicio" aria-label="Buscar recurso" />
        <select value={departamento} onChange={(e) => setDepartamento(e.target.value)} aria-label="Departamento">
          <option value="">Todos los departamentos</option>
          {c.departamentos.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
        <button className="boton">Buscar</button>
      </form>
      <BarraFiltros lista="recursos" filtros={filtros} alCambiar={setFiltros} total={total} sustantivo={["recurso", "recursos"]} />
      <div className="chips" role="group" aria-label="Tipos de recurso">
        {c.tipos.map((t) => (
          <button key={t.codigo} type="button" className={`chip chip-${t.codigo} ${tipos.includes(t.codigo) ? "activo" : ""}`} onClick={() => alternar(t.codigo)} aria-pressed={tipos.includes(t.codigo)}>
            <span className={`pin pin-${t.codigo} pin-chico`} aria-hidden />
            {t.texto}
          </button>
        ))}
      </div>
      <Aviso error={lista.error} />
      <div className="recursos-vista">
        <MapaRecursos cfg={c.mapa} puntos={puntos} elegido={elegido} alElegir={setElegido} />
        <div className="recursos-lista">
          {!lista.datos ? (
            <Cargando />
          ) : lista.datos.length === 0 ? (
            <Vacio>No hay recursos con esos filtros.</Vacio>
          ) : (
            <>
              <p className="tenue">
                {lista.datos.length} {lista.datos.length === 1 ? "recurso" : "recursos"}
                {sinUbicacion > 0 && ` · ${sinUbicacion} sin ubicación en el mapa`}
              </p>
              {lista.datos.map((r) => (
                <TarjetaRecurso key={r.id} r={r} cat={c} elegido={r.id === elegido} alElegir={() => setElegido(r.id)} />
              ))}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function TarjetaRecurso({ r, cat, elegido, alElegir }: { r: Recurso; cat: CatalogoRecursos; elegido: boolean; alElegir: () => void }) {
  return (
    <article className={`recurso ${elegido ? "recurso-elegido" : ""}`} onClick={alElegir} ref={(el) => {
        if (elegido) el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }}>
      <div className="recurso-cabecera">
        <span className={`pin pin-${r.tipo} pin-chico`} aria-hidden />
        <Enlace a={`/recursos/${r.id}`}>
          <strong>{r.nombre}</strong>
        </Enlace>
      </div>
      <div className="tenue">
        {textoTipo(cat, r)}
        {(r.localidad || r.departamento) && ` · ${[r.localidad, r.departamento].filter(Boolean).join(", ")}`}
      </div>
      {r.tipo === "cuidador" && r.zonas.length > 0 && <div className="tenue">Trabaja en: {r.zonas.join(", ")}</div>}
      {r.referente && (
        <div>
          {r.referente}
          {r.referente_cargo && ` (${r.referente_cargo})`}
        </div>
      )}
      <div className="recurso-acciones">
        {r.telefono && (
          <a href={`tel:${telefonoLimpio(r.telefono)}`} onClick={(e) => e.stopPropagation()}>
            ✆ {r.telefono}
          </a>
        )}
        {r.lat !== null && r.lng !== null && (
          <a href={enlaceComoLlegar(r.lat, r.lng)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            Cómo llegar
          </a>
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------- ficha y formulario

export function PaginaRecurso({ id }: { id: string }) {
  const { yo } = useSesion();
  const cat = useCatalogoRecursos();
  const nuevo = id === "nuevo";
  const { datos, error, recargar } = useDatos(() => (nuevo ? Promise.resolve(null) : api.get<Recurso>(`/recursos/${id}`)), [id]);
  const [editando, setEditando] = useState(false);
  if (cat.error || error) return <Aviso error={cat.error ?? error} />;
  if (!cat.datos || (!nuevo && !datos)) return <Cargando />;
  const c = cat.datos;
  if (nuevo || editando) {
    return (
      <>
        <h1>{nuevo ? "Agregar recurso" : `Editar: ${datos!.nombre}`}</h1>
        <FormRecurso
          cat={c}
          recurso={datos ?? undefined}
          alGuardar={(r) => {
            setEditando(false);
            if (nuevo) navegar(`/recursos/${r.id}`);
            else recargar();
          }}
          alCancelar={() => (nuevo ? navegar("/recursos") : setEditando(false))}
        />
      </>
    );
  }
  const r = datos!;
  const puedeEditar = c.puede.modificar === "todos" || (c.puede.modificar === "propios" && r.creado_por === yo.id);
  const fila = (t: string, v: string | null | undefined) =>
    v ? (
      <div className="dato-recurso">
        <dt>{t}</dt>
        <dd>{v}</dd>
      </div>
    ) : null;
  return (
    <>
      <div className="inicio-cabecera">
        <h1>
          {r.nombre} {!r.activo && <small className="tenue">(dado de baja)</small>}
        </h1>
        <div className="fila-botones">
          <Enlace a="/recursos" className="boton">
            Volver al mapa
          </Enlace>
          {puedeEditar && (
            <button className="boton boton-primario" onClick={() => setEditando(true)}>
              Editar
            </button>
          )}
        </div>
      </div>
      <p className="tenue">{textoTipo(c, r)}</p>
      <div className="inicio-columnas">
        <Seccion titulo="Datos">
          <dl className="datos-recurso">
            {fila("Dirección", [r.direccion, r.localidad, r.departamento].filter(Boolean).join(", "))}
            {fila("Teléfono", [r.telefono, r.telefono_alternativo].filter(Boolean).join(" · "))}
            {fila("Correo", r.email)}
            {fila("Horario", r.horario)}
            {fila("Referente", r.referente ? `${r.referente}${r.referente_cargo ? ` (${r.referente_cargo})` : ""}` : null)}
            {fila("Servicios", r.servicios)}
            {r.tipo === "cuidador" && fila("Zonas donde trabaja", r.zonas.join(", "))}
            {r.tipo === "cuidador" && fila("Formación", r.formacion)}
            {r.tipo === "cuidador" && fila("Disponibilidad", r.disponibilidad)}
            {fila("Observaciones", r.observaciones)}
            {fila("Cómo se obtuvo", textoOrigen(c, r))}
          </dl>
          <p className="tenue">Actualizado el {fechaHora(r.actualizado_en)}.</p>
          <div className="fila-botones">
            {r.telefono && (
              <a className="boton" href={`tel:${telefonoLimpio(r.telefono)}`}>
                Llamar
              </a>
            )}
            {r.lat !== null && r.lng !== null && (
              <a className="boton" href={enlaceComoLlegar(r.lat, r.lng)} target="_blank" rel="noreferrer">
                Cómo llegar
              </a>
            )}
          </div>
        </Seccion>
        <Seccion titulo="Ubicación">
          {r.lat !== null && r.lng !== null ? (
            <MapaRecursos cfg={c.mapa} puntos={[{ id: r.id, lat: r.lat, lng: r.lng, tipo: r.tipo, titulo: r.nombre }]} alto={320} />
          ) : (
            <Vacio>Sin ubicación cargada.</Vacio>
          )}
        </Seccion>
      </div>
      {r.tipo !== "cuidador" && (
        <Seccion titulo="Contactos">
          <ContactosDelRecurso cat={c} recurso={r} />
        </Seccion>
      )}
      {(r.tipo === "residencia" || r.tipo === "centro_dia") && <DocumentacionDelRecurso recursoId={r.id} nombre={r.nombre} />}
      {r.tipo === "residencia" && <PersonasInternadas recursoId={r.id} />}
    </>
  );
}

export function FormRecurso({
  cat,
  recurso,
  alGuardar,
  alCancelar,
}: {
  cat: CatalogoRecursos;
  recurso?: Recurso;
  alGuardar: (r: Recurso) => void;
  alCancelar: () => void;
}) {
  const [d, setD] = useState({
    tipo: recurso?.tipo ?? "centro_jubilados",
    categoria: recurso?.categoria ?? "",
    nombre: recurso?.nombre ?? "",
    direccion: recurso?.direccion ?? "",
    localidad: recurso?.localidad ?? "",
    departamento: recurso?.departamento ?? "",
    telefono: recurso?.telefono ?? "",
    telefono_alternativo: recurso?.telefono_alternativo ?? "",
    email: recurso?.email ?? "",
    horario: recurso?.horario ?? "",
    referente: recurso?.referente ?? "",
    referente_cargo: recurso?.referente_cargo ?? "",
    servicios: recurso?.servicios ?? "",
    observaciones: recurso?.observaciones ?? "",
    zonas: recurso?.zonas ?? ([] as string[]),
    formacion: recurso?.formacion ?? "",
    disponibilidad: recurso?.disponibilidad ?? "",
    origen: recurso?.origen ?? "",
    origen_detalle: recurso?.origen_detalle ?? "",
    activo: recurso?.activo ?? true,
  });
  const [ubicacion, setUbicacion] = useState<{ lat: number; lng: number } | null>(
    recurso?.lat != null && recurso?.lng != null ? { lat: recurso.lat, lng: recurso.lng } : null,
  );
  const [resultados, setResultados] = useState<{ lat: number; lng: number; descripcion: string }[] | null>(null);
  const busqueda = useEnvio();
  const { enviando, error, ejecutar } = useEnvio();
  const set = (c: Partial<typeof d>) => setD({ ...d, ...c });
  const tipo = cat.tipos.find((t) => t.codigo === d.tipo);
  const cuidador = d.tipo === "cuidador";

  const usarGps = async () => {
    busqueda.setError(null);
    try {
      const u = await ubicacionActual();
      setUbicacion({ lat: Math.round(u.lat * 1e6) / 1e6, lng: Math.round(u.lng * 1e6) / 1e6 });
    } catch (e) {
      busqueda.setError(e);
    }
  };

  const buscarDireccion = async () => {
    const texto = [d.direccion, d.localidad, d.departamento, "Tucumán"].filter(Boolean).join(", ");
    const r = await busqueda.ejecutar(() => api.get<{ lat: number; lng: number; descripcion: string }[]>("/recursos/geocodificar", { q: texto }));
    if (r) {
      setResultados(r);
      if (r.length > 0) setUbicacion({ lat: r[0].lat, lng: r[0].lng });
    }
  };

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = {
      ...d,
      categoria: d.tipo === "institucion" ? d.categoria || null : null,
      zonas: cuidador ? d.zonas : [],
      lat: ubicacion?.lat ?? null,
      lng: ubicacion?.lng ?? null,
    };
    const r = await ejecutar(() => (recurso ? api.patch<Recurso>(`/recursos/${recurso.id}`, cuerpo) : api.post<Recurso>("/recursos", cuerpo)));
    if (r) alGuardar(r);
  };

  return (
    <form onSubmit={enviar} className="formulario">
      <div className="inicio-columnas">
        <div>
          <div className="grilla">
            <Campo etiqueta="Tipo *">
              <select value={d.tipo} onChange={(e) => set({ tipo: e.target.value })}>
                {cat.tipos.map((t) => (
                  <option key={t.codigo} value={t.codigo}>
                    {t.texto}
                  </option>
                ))}
              </select>
            </Campo>
            {tipo?.categorias && (
              <Campo etiqueta="Categoría">
                <select value={d.categoria} onChange={(e) => set({ categoria: e.target.value })}>
                  <option value="">—</option>
                  {tipo.categorias.map((x) => (
                    <option key={x.codigo} value={x.codigo}>
                      {x.texto}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            <Campo etiqueta={cuidador ? "Apellido y nombre *" : "Nombre *"} ancho="completo">
              <input value={d.nombre} onChange={(e) => set({ nombre: e.target.value })} required minLength={2} />
            </Campo>
            <Campo etiqueta="Dirección" ancho="completo">
              <input value={d.direccion} onChange={(e) => set({ direccion: e.target.value })} />
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
            <Campo etiqueta="Correo">
              <input type="email" value={d.email} onChange={(e) => set({ email: e.target.value })} />
            </Campo>
            {!cuidador && (
              <>
                <Campo etiqueta="Horario">
                  <input value={d.horario} onChange={(e) => set({ horario: e.target.value })} placeholder="Ej.: lunes a viernes de 8 a 13" />
                </Campo>
                <Campo etiqueta="Referente">
                  <input value={d.referente} onChange={(e) => set({ referente: e.target.value })} />
                </Campo>
                <Campo etiqueta="Cargo del referente">
                  <input value={d.referente_cargo} onChange={(e) => set({ referente_cargo: e.target.value })} />
                </Campo>
              </>
            )}
          </div>
          {cuidador && (
            <>
              <fieldset className="opciones opciones-linea">
                <legend>Departamentos donde trabaja</legend>
                {cat.departamentos.map((x) => (
                  <label key={x} className="casilla">
                    <input
                      type="checkbox"
                      checked={d.zonas.includes(x)}
                      onChange={(e) => set({ zonas: e.target.checked ? [...d.zonas, x] : d.zonas.filter((z) => z !== x) })}
                    />
                    <span>{x}</span>
                  </label>
                ))}
              </fieldset>
              <Campo etiqueta="Formación">
                <textarea rows={2} value={d.formacion} onChange={(e) => set({ formacion: e.target.value })} placeholder="Curso, institución, año" />
              </Campo>
              <Campo etiqueta="Disponibilidad">
                <input value={d.disponibilidad} onChange={(e) => set({ disponibilidad: e.target.value })} placeholder="Ej.: mañanas, fines de semana, con retiro" />
              </Campo>
            </>
          )}
          <Campo etiqueta={cuidador ? "Tareas que realiza" : "Servicios y actividades"}>
            <textarea rows={3} value={d.servicios} onChange={(e) => set({ servicios: e.target.value })} />
          </Campo>
          <Campo etiqueta="Observaciones">
            <textarea rows={2} value={d.observaciones} onChange={(e) => set({ observaciones: e.target.value })} />
          </Campo>
          <CampoOrigen cat={cat} origen={d.origen} detalle={d.origen_detalle} alCambiar={(o, det) => set({ origen: o, origen_detalle: det })} />
          {recurso && (
            <label className="casilla">
              <input type="checkbox" checked={!d.activo} onChange={(e) => set({ activo: !e.target.checked })} />
              Dar de baja (deja de aparecer en el mapa; no se borra)
            </label>
          )}
        </div>
        <div>
          <h3>Ubicación</h3>
          <p className="tenue">
            Toque el mapa para marcar el lugar; el marcador se puede arrastrar.
            {cuidador && " Para cuidadores, marque su domicilio: sirve para ver quién vive cerca de cada caso."}
          </p>
          <div className="fila-botones fila-izquierda">
            <button type="button" className="boton boton-chico" onClick={usarGps}>
              Estoy en el lugar: usar mi ubicación
            </button>
            {cat.geocodificador && (
              <button type="button" className="boton boton-chico" onClick={buscarDireccion} disabled={busqueda.enviando || !d.direccion}>
                {busqueda.enviando ? "Buscando…" : "Buscar la dirección en el mapa"}
              </button>
            )}
            {ubicacion && (
              <button type="button" className="boton boton-chico" onClick={() => setUbicacion(null)}>
                Quitar ubicación
              </button>
            )}
          </div>
          <Aviso error={busqueda.error} />
          {resultados && resultados.length === 0 && <Aviso error="No se encontró la dirección. Marque el lugar tocando el mapa." tipo="info" />}
          {resultados && resultados.length > 1 && (
            <select className="resultados-geo" onChange={(e) => setUbicacion(resultados[Number(e.target.value)])} aria-label="Resultados de la búsqueda">
              {resultados.map((x, i) => (
                <option key={i} value={i}>
                  {x.descripcion}
                </option>
              ))}
            </select>
          )}
          <MapaSelector cfg={cat.mapa} valor={ubicacion} alCambiar={setUbicacion} tipo={d.tipo} />
          {ubicacion && (
            <p className="tenue">
              {ubicacion.lat.toFixed(5)}, {ubicacion.lng.toFixed(5)}
            </p>
          )}
        </div>
      </div>
      <Aviso error={error} />
      <div className="fila-botones">
        <button type="button" className="boton" onClick={alCancelar}>
          Cancelar
        </button>
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

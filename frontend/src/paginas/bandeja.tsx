// Captura con el celular: se sacan todas las fotos seguidas, y después se eligen las hojas que forman
// cada documento, se indica el legajo y el tipo (con los datos que pide su plantilla) y se guarda.
// Si el tipo no existe, se crea ahí mismo con su plantilla (vencimiento, número, campos propios).
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api, subirConProgreso, type Caso, type Documento, type PersonaResumen, type TipoDocumental } from "../api";
import { Aviso, Campo, Cargando, Seccion, Vacio, documento as docPersona, nombre, useDatos, useEnvio, useSesion } from "../comun";
import { achicar } from "../movil/fotos";

interface Pagina {
  id: string;
  creada_en: string;
  tamano: number;
}

const MESES_A_DIAS = 30.4375;

function sumarDias(iso: string, dias: number): string {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

export function PaginaBandeja({ movil = false }: { movil?: boolean }) {
  const { puede } = useSesion();
  const { datos, error, recargar } = useDatos(() => api.get<{ cantidad: number; paginas: Pagina[] }>("/capturas"), []);
  const [elegidas, setElegidas] = useState<string[]>([]);
  const [subiendo, setSubiendo] = useState<{ hecho: number; total: number } | null>(null);
  const [errorSubida, setErrorSubida] = useState<unknown>(null);
  const [clasificando, setClasificando] = useState(false);
  const [guardado, setGuardado] = useState<string | null>(null);
  const camara = useRef<HTMLInputElement>(null);
  const galeria = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Lo elegido que ya no está en la bandeja (clasificado o descartado) se saca de la selección.
    if (datos) setElegidas((e) => e.filter((id) => datos.paginas.some((p) => p.id === id)));
  }, [datos]);

  if (!puede("documentos", "crear")) return <Aviso error="No tiene permiso para cargar documentos." />;

  const subir = async (lista: FileList | null) => {
    if (!lista || lista.length === 0) return;
    const archivos = Array.from(lista).filter((a) => a.type.startsWith("image/"));
    setErrorSubida(null);
    setGuardado(null);
    setSubiendo({ hecho: 0, total: archivos.length });
    try {
      for (let i = 0; i < archivos.length; i++) {
        const blob = await achicar(archivos[i]);
        const fd = new FormData();
        fd.append("foto", blob, `captura-${Date.now()}-${i}.jpg`);
        await subirConProgreso("/capturas", fd, () => undefined);
        setSubiendo({ hecho: i + 1, total: archivos.length });
      }
    } catch (e) {
      setErrorSubida(e instanceof ApiError ? e : new Error("No se pudo enviar una de las fotos. Reintente: las anteriores ya quedaron guardadas."));
    } finally {
      setSubiendo(null);
      if (camara.current) camara.current.value = "";
      if (galeria.current) galeria.current.value = "";
      recargar();
    }
  };

  const alternar = (id: string) => setElegidas((e) => (e.includes(id) ? e.filter((x) => x !== id) : [...e, id]));

  const descartar = async () => {
    if (!window.confirm(`¿Descartar ${elegidas.length} ${elegidas.length === 1 ? "foto" : "fotos"}? No se guardan en ningún legajo.`)) return;
    for (const id of elegidas) await api.post(`/capturas/${id}/descartar`);
    setElegidas([]);
    recargar();
  };

  return (
    <div className={movil ? "band band-movil" : "band"}>
      {!movil && <h1>Digitalización de documentos</h1>}
      <p className="tenue">
        Saque todas las fotos seguidas. Después elija las hojas de cada documento, indique el legajo y el tipo, y se guarda como un solo PDF.
      </p>
      <div className="band-captura">
        <input ref={camara} type="file" accept="image/*" capture="environment" hidden onChange={(e) => subir(e.target.files)} />
        <input ref={galeria} type="file" accept="image/*" multiple hidden onChange={(e) => subir(e.target.files)} />
        <button className="boton boton-primario" disabled={!!subiendo} onClick={() => camara.current?.click()}>
          Sacar foto
        </button>
        <button className="boton" disabled={!!subiendo} onClick={() => galeria.current?.click()}>
          {movil ? "Elegir de la galería" : "Subir imágenes"}
        </button>
        {subiendo && (
          <span role="status">
            Subiendo {subiendo.hecho + 1} de {subiendo.total}…
          </span>
        )}
      </div>
      <Aviso error={errorSubida} />
      {guardado && <Aviso tipo="exito" error={guardado} />}
      {error ? (
        <Aviso error={error} />
      ) : !datos ? (
        <Cargando />
      ) : datos.paginas.length === 0 ? (
        <Vacio>No hay fotos esperando. Las que saque aparecen acá.</Vacio>
      ) : (
        <>
          <p>
            <strong>{datos.cantidad}</strong> {datos.cantidad === 1 ? "foto" : "fotos"} sin clasificar. Toque las hojas de un mismo documento, en
            orden.
          </p>
          <div className="band-grilla">
            {datos.paginas.map((p, i) => {
              const n = elegidas.indexOf(p.id);
              return (
                <figure key={p.id} className={`band-hoja ${n >= 0 ? "elegida" : ""}`}>
                  <button type="button" onClick={() => alternar(p.id)} aria-pressed={n >= 0} aria-label={`Foto ${i + 1}${n >= 0 ? `, hoja ${n + 1} del documento` : ""}`}>
                    <img src={`/api/capturas/${p.id}/imagen?miniatura=true`} alt="" loading="lazy" />
                    {n >= 0 && <span className="band-orden">{n + 1}</span>}
                  </button>
                  <figcaption>
                    Foto {i + 1} ·{" "}
                    <a href={`/api/capturas/${p.id}/imagen`} target="_blank" rel="noreferrer">
                      ampliar
                    </a>
                  </figcaption>
                </figure>
              );
            })}
          </div>
        </>
      )}
      {elegidas.length > 0 && (
        <div className="band-barra" role="region" aria-label="Acciones sobre las hojas elegidas">
          <span>
            {elegidas.length} {elegidas.length === 1 ? "hoja elegida" : "hojas elegidas"}
          </span>
          <button className="boton boton-primario" onClick={() => setClasificando(true)}>
            Armar documento
          </button>
          <button className="boton" onClick={() => setElegidas([])}>
            Soltar
          </button>
          <button className="boton boton-peligro" onClick={descartar}>
            Descartar
          </button>
        </div>
      )}
      {clasificando && (
        <ClasificarHojas
          hojas={elegidas}
          alMover={setElegidas}
          alCerrar={() => setClasificando(false)}
          alGuardar={(d, quien) => {
            setClasificando(false);
            setElegidas([]);
            setGuardado(`Documento «${d.titulo}» guardado en el legajo de ${quien}.`);
            recargar();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- armar un documento

function ClasificarHojas({
  hojas,
  alMover,
  alCerrar,
  alGuardar,
}: {
  hojas: string[];
  alMover: (h: string[]) => void;
  alCerrar: () => void;
  alGuardar: (d: Documento, persona: string) => void;
}) {
  const { catalogos, recargarCatalogos } = useSesion();
  const [persona, setPersona] = useState<PersonaResumen | null>(null);
  const [tipoId, setTipoId] = useState("");
  const [nuevoTipo, setNuevoTipo] = useState(false);
  const [titulo, setTitulo] = useState("");
  const [tituloEditado, setTituloEditado] = useState(false);
  const [emision, setEmision] = useState("");
  const [vence, setVence] = useState("");
  const [venceEditado, setVenceEditado] = useState(false);
  const [numero, setNumero] = useState("");
  const [propios, setPropios] = useState<Record<string, string>>({});
  const [casoId, setCasoId] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const tipo = catalogos.tipos_documentales.find((t) => String(t.id) === tipoId);

  const casos = useDatos(() => (persona ? api.get<Caso[]>("/casos", { persona_id: persona.id, limite: 50 }) : Promise.resolve([] as Caso[])), [persona?.id]);

  useEffect(() => {
    if (tipo && !tituloEditado) setTitulo(tipo.nombre);
  }, [tipo, tituloEditado]);

  // El vencimiento se sugiere desde la emisión y la vigencia habitual del tipo.
  useEffect(() => {
    if (tipo?.tiene_vencimiento && tipo.vigencia_dias && emision && !venceEditado) setVence(sumarDias(emision, tipo.vigencia_dias));
  }, [tipo, emision, venceEditado]);

  const mover = (i: number, d: number) => {
    const n = [...hojas];
    [n[i], n[i + d]] = [n[i + d], n[i]];
    alMover(n);
  };

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    if (!persona || !tipo) return;
    const d = await ejecutar(() =>
      api.post<Documento>("/capturas/clasificar", {
        paginas: hojas,
        tipo_documental_id: tipo.id,
        titulo,
        descripcion: descripcion || null,
        persona_id: persona.id,
        caso_id: casoId || null,
        fecha_emision: emision || null,
        vence: tipo.tiene_vencimiento && vence ? vence : null,
        numero: tipo.usa_numero && numero ? numero : null,
        datos: propios,
      }),
    );
    if (d) alGuardar(d, nombre(persona));
  };

  return (
    <div className="modal-fondo" onMouseDown={(e) => e.target === e.currentTarget && alCerrar()}>
      <div className="modal modal-ancho band-modal" role="dialog" aria-modal="true" aria-label="Armar documento">
        <header className="modal-cabecera">
          <h2>Armar documento ({hojas.length} {hojas.length === 1 ? "hoja" : "hojas"})</h2>
          <button type="button" className="boton-icono" onClick={alCerrar} aria-label="Cerrar">
            ×
          </button>
        </header>
        <form className="modal-cuerpo formulario" onSubmit={guardar}>
          <div className="band-orden-hojas" aria-label="Orden de las hojas">
            {hojas.map((id, i) => (
              <figure key={id}>
                <img src={`/api/capturas/${id}/imagen?miniatura=true`} alt={`Hoja ${i + 1}`} />
                <figcaption>
                  <button type="button" disabled={i === 0} onClick={() => mover(i, -1)} aria-label={`Subir la hoja ${i + 1}`}>
                    ◀
                  </button>
                  <span>{i + 1}</span>
                  <button type="button" disabled={i === hojas.length - 1} onClick={() => mover(i, 1)} aria-label={`Bajar la hoja ${i + 1}`}>
                    ▶
                  </button>
                </figcaption>
              </figure>
            ))}
          </div>

          {persona ? (
            <p>
              <strong>Legajo:</strong> {nombre(persona)} · {docPersona(persona)}{" "}
              <button type="button" className="boton boton-chico" onClick={() => setPersona(null)}>
                Cambiar
              </button>
            </p>
          ) : (
            <BuscarLegajo alElegir={setPersona} />
          )}

          <div className="grilla">
            <Campo etiqueta="Tipo de documento *">
              <select
                value={nuevoTipo ? "__nuevo" : tipoId}
                onChange={(e) => {
                  if (e.target.value === "__nuevo") setNuevoTipo(true);
                  else {
                    setNuevoTipo(false);
                    setTipoId(e.target.value);
                    setVenceEditado(false);
                    setPropios({});
                  }
                }}
                required
              >
                <option value="">Elegir…</option>
                {catalogos.tipos_documentales.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nombre}
                  </option>
                ))}
                <option value="__nuevo">＋ Es un tipo nuevo…</option>
              </select>
            </Campo>
            <Campo etiqueta="Título *">
              <input
                value={titulo}
                maxLength={300}
                required
                onChange={(e) => {
                  setTitulo(e.target.value);
                  setTituloEditado(true);
                }}
              />
            </Campo>
          </div>

          {nuevoTipo && (
            <FormTipoNuevo
              alCancelar={() => setNuevoTipo(false)}
              alCrear={(t) => {
                recargarCatalogos();
                setNuevoTipo(false);
                setTipoId(String(t.id));
                // El catálogo se recarga en segundo plano: mientras, se usa la plantilla recién creada.
                catalogos.tipos_documentales.push(t);
              }}
            />
          )}

          {tipo && !nuevoTipo && (
            <div className="grilla">
              {tipo.descripcion && <p className="tenue">{tipo.descripcion}</p>}
              <Campo etiqueta="Fecha de emisión">
                <input type="date" value={emision} onChange={(e) => setEmision(e.target.value)} />
              </Campo>
              {tipo.tiene_vencimiento && (
                <Campo
                  etiqueta="Vence"
                  ayuda={tipo.vigencia_dias ? `Se sugiere según la vigencia habitual (${Math.round(tipo.vigencia_dias / MESES_A_DIAS)} meses).` : undefined}
                >
                  <input
                    type="date"
                    value={vence}
                    onChange={(e) => {
                      setVence(e.target.value);
                      setVenceEditado(true);
                    }}
                  />
                </Campo>
              )}
              {tipo.usa_numero && (
                <Campo etiqueta="Número o código">
                  <input value={numero} maxLength={100} onChange={(e) => setNumero(e.target.value)} />
                </Campo>
              )}
              {tipo.campos.map((c) => (
                <Campo key={c.clave} etiqueta={c.etiqueta}>
                  <input
                    type={c.tipo === "fecha" ? "date" : "text"}
                    inputMode={c.tipo === "numero" ? "decimal" : undefined}
                    maxLength={300}
                    value={propios[c.clave] ?? ""}
                    onChange={(e) => setPropios({ ...propios, [c.clave]: e.target.value })}
                  />
                </Campo>
              ))}
              {persona && (casos.datos?.length ?? 0) > 0 && (
                <Campo etiqueta="Caso">
                  <select value={casoId} onChange={(e) => setCasoId(e.target.value)}>
                    <option value="">Sin caso (documento del legajo)</option>
                    {casos.datos!.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.numero}
                      </option>
                    ))}
                  </select>
                </Campo>
              )}
              <Campo etiqueta="Descripción" ancho="completo">
                <textarea rows={2} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
              </Campo>
            </div>
          )}

          <Aviso error={error} />
          <div className="fila-botones">
            <button className="boton boton-primario" disabled={enviando || !persona || !tipo || nuevoTipo}>
              {enviando ? "Guardando…" : "Guardar en el legajo"}
            </button>
            <button type="button" className="boton" onClick={alCerrar}>
              Volver
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Buscador de legajo compacto (sirve también en la pantalla del celular). */
function BuscarLegajo({ alElegir }: { alElegir: (p: PersonaResumen) => void }) {
  const [q, setQ] = useState("");
  const [r, setR] = useState<PersonaResumen[] | null>(null);
  const { error, enviando, ejecutar } = useEnvio();
  const buscar = async (e: FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const x = await ejecutar(() => api.get<PersonaResumen[]>("/personas", { q, limite: 15 }));
    if (x) setR(x);
  };
  return (
    <div className="band-buscar">
      <strong>¿De quién es? *</strong>
      <div className="buscador">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Apellido, documento o N° de legajo"
          aria-label="Buscar legajo"
          onKeyDown={(e) => e.key === "Enter" && buscar(e)}
        />
        <button type="button" className="boton" disabled={enviando || q.trim().length < 2} onClick={buscar}>
          Buscar
        </button>
      </div>
      <Aviso error={error} />
      {r && (r.length === 0 ? <Vacio>No se encontraron legajos.</Vacio> : (
        <ul className="band-resultados">
          {r.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => alElegir(p)}>
                <strong>{nombre(p)}</strong>
                <small>
                  {docPersona(p)} · Legajo {p.numero_legajo}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- tipo de documento nuevo

function FormTipoNuevo({ alCrear, alCancelar }: { alCrear: (t: TipoDocumental) => void; alCancelar: () => void }) {
  const [nombreTipo, setNombreTipo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [vence, setVence] = useState(false);
  const [meses, setMeses] = useState("");
  const [numero, setNumero] = useState(false);
  const [campos, setCampos] = useState<{ etiqueta: string; tipo: "texto" | "fecha" | "numero" }[]>([]);
  const { enviando, error, ejecutar } = useEnvio();

  const crear = async () => {
    const t = await ejecutar(() =>
      api.post<TipoDocumental>("/tipos-documentales", {
        nombre: nombreTipo,
        descripcion: descripcion || null,
        tiene_vencimiento: vence,
        vigencia_dias: vence && meses ? Math.round(Number(meses.replace(",", ".")) * MESES_A_DIAS) : null,
        usa_numero: numero,
        campos: campos.filter((c) => c.etiqueta.trim()),
      }),
    );
    if (t) alCrear(t);
  };

  return (
    <Seccion titulo="Tipo de documento nuevo">
      <p className="tenue">Queda guardado como plantilla: la próxima vez se pedirán estos mismos datos.</p>
      <div className="grilla">
        <Campo etiqueta="Nombre del tipo *">
          <input value={nombreTipo} maxLength={200} onChange={(e) => setNombreTipo(e.target.value)} autoFocus />
        </Campo>
        <Campo etiqueta="Para qué sirve (opcional)">
          <input value={descripcion} maxLength={1000} onChange={(e) => setDescripcion(e.target.value)} />
        </Campo>
        <label className="campo campo-casilla">
          <input type="checkbox" checked={vence} onChange={(e) => setVence(e.target.checked)} /> Tiene fecha de caducidad
        </label>
        {vence && (
          <Campo etiqueta="Vigencia habitual (meses)" ayuda="Sugiere la fecha de vencimiento desde la emisión. Puede dejarse vacío.">
            <input inputMode="decimal" value={meses} onChange={(e) => setMeses(e.target.value)} placeholder="Ej.: 6" />
          </Campo>
        )}
        <label className="campo campo-casilla">
          <input type="checkbox" checked={numero} onChange={(e) => setNumero(e.target.checked)} /> Lleva número o código
        </label>
      </div>
      <div className="band-campos">
        <strong>Otros datos a registrar</strong>
        {campos.map((c, i) => (
          <div key={i} className="fila-campo">
            <input
              aria-label={`Nombre del dato ${i + 1}`}
              placeholder="Ej.: Emisor"
              value={c.etiqueta}
              maxLength={80}
              onChange={(e) => setCampos(campos.map((x, j) => (j === i ? { ...x, etiqueta: e.target.value } : x)))}
            />
            <select
              aria-label={`Tipo del dato ${i + 1}`}
              value={c.tipo}
              onChange={(e) => setCampos(campos.map((x, j) => (j === i ? { ...x, tipo: e.target.value as "texto" | "fecha" | "numero" } : x)))}
            >
              <option value="texto">Texto</option>
              <option value="fecha">Fecha</option>
              <option value="numero">Número</option>
            </select>
            <button type="button" className="boton boton-chico" onClick={() => setCampos(campos.filter((_, j) => j !== i))}>
              Quitar
            </button>
          </div>
        ))}
        {campos.length < 12 && (
          <button type="button" className="boton boton-chico" onClick={() => setCampos([...campos, { etiqueta: "", tipo: "texto" }])}>
            ＋ Agregar un dato
          </button>
        )}
      </div>
      <Aviso error={error} />
      <div className="fila-botones">
        <button type="button" className="boton boton-primario" disabled={enviando || nombreTipo.trim().length < 2} onClick={crear}>
          Crear tipo y usarlo
        </button>
        <button type="button" className="boton" onClick={alCancelar}>
          Cancelar
        </button>
      </div>
    </Seccion>
  );
}


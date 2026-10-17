// Novedades: circulares e información de la Dirección (para todos) y de cada área,
// con confirmación de lectura. Publican la Dirección y las jefaturas (su área).
import { useEffect, useRef, useState } from "react";
import { api, subirConProgreso, type UsuarioBreve } from "../api";
import { Aviso, Cargando, Modal, Vacio, fechaHora, useDatos, useEnvio, useSesion } from "../comun";
import { BarraFormato, EditorTexto } from "./informes";

export interface Novedad {
  id: string;
  titulo: string;
  cuerpo: string;
  area: { id: number; nombre: string } | null;
  requiere_confirmacion: boolean;
  fijada: boolean;
  archivo: { nombre: string; mime: string; tamano: number } | null;
  autor: UsuarioBreve | null;
  publicada_en: string;
  es_destinatario: boolean;
  confirmada_en: string | null;
  puede_gestionar: boolean;
  lecturas?: { destinatarios: number; confirmaron: number };
}

interface Listado {
  novedades: Novedad[];
  puede_publicar: boolean;
  areas_publicables: { id: number | null; nombre: string }[];
}

export interface Pendientes {
  cantidad: number;
  novedades: { id: string; titulo: string; area: string | null; autor: string | null; publicada_en: string; resumen: string; archivo: boolean }[];
}

export function usePendientes() {
  const r = useDatos(() => api.get<Pendientes>("/novedades/pendientes"), []);
  // Cuando se confirma una lectura en cualquier parte, se actualizan todos los contadores.
  useEffect(() => {
    const f = () => r.recargar();
    window.addEventListener("sulam:novedades", f);
    return () => window.removeEventListener("sulam:novedades", f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return r;
}

function avisarCambio() {
  window.dispatchEvent(new Event("sulam:novedades"));
}

function corta(nombre: string) {
  return nombre.replace(/^(Departamento|División)\s+/, "");
}

const FILTROS: [string, string][] = [
  ["todas", "Todas"],
  ["pendientes", "Sin confirmar"],
  ["direccion", "De la Dirección"],
  ["area", "De las áreas"],
];

export function PaginaNovedades({ movil }: { movil?: boolean }) {
  const [filtro, setFiltro] = useState(() => (new URLSearchParams(location.hash.split("?")[1] ?? "").get("filtro") ?? "todas"));
  const lista = useDatos(() => api.get<Listado>("/novedades", { filtro }), [filtro]);
  const [nueva, setNueva] = useState(false);
  const [lecturas, setLecturas] = useState<Novedad | null>(null);
  const d = lista.datos;
  return (
    <div className={movil ? "novedades-movil" : ""}>
      {!movil && (
        <header className="inicio-cabecera">
          <h1>Novedades</h1>
          {d?.puede_publicar && (
            <button className="boton boton-primario" onClick={() => setNueva(true)}>
              Publicar novedad
            </button>
          )}
        </header>
      )}
      {movil && d?.puede_publicar && (
        <button className="m-boton m-boton-primario" onClick={() => setNueva(true)}>
          Publicar novedad
        </button>
      )}
      <div className={movil ? "m-chips" : "segmentado"} role="group" aria-label="Filtro">
        {FILTROS.map(([k, t]) => (
          <button key={k} type="button" className={filtro === k ? "activo" : ""} onClick={() => setFiltro(k)}>
            {t}
          </button>
        ))}
      </div>
      <Aviso error={lista.error} />
      {!d ? (
        <Cargando />
      ) : d.novedades.length === 0 ? (
        <Vacio>{filtro === "pendientes" ? "No tiene novedades sin confirmar." : "No hay novedades."}</Vacio>
      ) : (
        <div className="lista-novedades">
          {d.novedades.map((n) => (
            <TarjetaNovedad key={n.id} n={n} alCambiar={lista.recargar} alVerLecturas={() => setLecturas(n)} />
          ))}
        </div>
      )}
      {nueva && d && (
        <Modal titulo="Publicar novedad" alCerrar={() => setNueva(false)} ancho>
          <FormNovedad
            areas={d.areas_publicables}
            alPublicar={() => {
              setNueva(false);
              lista.recargar();
            }}
          />
        </Modal>
      )}
      {lecturas && (
        <Modal titulo={`Lecturas · ${lecturas.titulo}`} alCerrar={() => setLecturas(null)}>
          <Lecturas id={lecturas.id} />
        </Modal>
      )}
    </div>
  );
}

function TarjetaNovedad({ n, alCambiar, alVerLecturas }: { n: Novedad; alCambiar: () => void; alVerLecturas: () => void }) {
  const envio = useEnvio();
  const pendiente = n.requiere_confirmacion && n.es_destinatario && !n.confirmada_en;
  return (
    <article className={`novedad ${pendiente ? "novedad-pendiente" : ""} ${n.fijada ? "novedad-fijada" : ""}`}>
      <header>
        <span className={`novedad-origen ${n.area ? "" : "novedad-direccion"}`}>{n.area ? corta(n.area.nombre) : "Dirección · para todos"}</span>
        {n.fijada && <span className="novedad-fija">Fijada</span>}
        <h2>{n.titulo}</h2>
        <p className="tenue">
          {n.autor?.nombre_completo ?? "—"} · {fechaHora(n.publicada_en)}
        </p>
      </header>
      {/* HTML limpiado en el servidor (solo párrafos, listas, negrita, cursiva y subrayado). */}
      {n.cuerpo && <div className="novedad-cuerpo" dangerouslySetInnerHTML={{ __html: n.cuerpo }} />}
      {n.archivo && (
        <a className="novedad-archivo" href={`/api/novedades/${n.id}/archivo`} target="_blank" rel="noreferrer">
          📎 {n.archivo.nombre}
        </a>
      )}
      <footer>
        {pendiente ? (
          <button
            className="boton boton-primario"
            disabled={envio.enviando}
            onClick={() =>
              envio.ejecutar(() => api.post(`/novedades/${n.id}/confirmar`)).then((r) => {
                if (r) {
                  alCambiar();
                  avisarCambio();
                }
              })
            }
          >
            Leí y estoy al tanto
          </button>
        ) : n.confirmada_en ? (
          <span className="novedad-confirmada">✓ Confirmó la lectura el {fechaHora(n.confirmada_en)}</span>
        ) : null}
        {n.lecturas && (
          <button type="button" className="boton boton-chico" onClick={alVerLecturas}>
            Leída por {n.lecturas.confirmaron} de {n.lecturas.destinatarios}
          </button>
        )}
        {n.puede_gestionar && (
          <button
            type="button"
            className="boton boton-chico boton-texto"
            onClick={() => {
              if (confirm("¿Retirar esta novedad? Deja de verse para todos (queda registrada).")) envio.ejecutar(() => api.post(`/novedades/${n.id}/retirar`)).then((r) => r && alCambiar());
            }}
          >
            Retirar
          </button>
        )}
      </footer>
      <Aviso error={envio.error} />
    </article>
  );
}

function Lecturas({ id }: { id: string }) {
  const { datos, error } = useDatos(
    () =>
      api.get<{ confirmaron: { usuario: UsuarioBreve; area: string | null; confirmada_en: string }[]; faltan: { usuario: UsuarioBreve; area: string | null }[] }>(
        `/novedades/${id}/lecturas`,
      ),
    [id],
  );
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  return (
    <div className="lecturas">
      <h3>Faltan confirmar ({datos.faltan.length})</h3>
      {datos.faltan.length === 0 ? (
        <p className="tenue">Todos confirmaron.</p>
      ) : (
        <ul className="lista-simple">
          {datos.faltan.map((x) => (
            <li key={x.usuario.id}>
              {x.usuario.nombre_completo} {x.area && <span className="tenue">· {corta(x.area)}</span>}
            </li>
          ))}
        </ul>
      )}
      <h3>Confirmaron ({datos.confirmaron.length})</h3>
      <ul className="lista-simple">
        {datos.confirmaron.map((x) => (
          <li key={x.usuario.id}>
            {x.usuario.nombre_completo} <span className="tenue">· {fechaHora(x.confirmada_en)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FormNovedad({ areas, alPublicar }: { areas: { id: number | null; nombre: string }[]; alPublicar: () => void }) {
  const { yo } = useSesion();
  const [titulo, setTitulo] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [area, setArea] = useState<string>(areas.length ? String(areas[0].id) : "");
  const [confirmacion, setConfirmacion] = useState(true);
  const [fijada, setFijada] = useState(false);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const publicar = async (e: React.FormEvent) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append("titulo", titulo);
    fd.append("cuerpo", cuerpo);
    if (area && area !== "null") fd.append("area_id", area);
    fd.append("requiere_confirmacion", String(confirmacion));
    fd.append("fijada", String(fijada));
    if (archivo) fd.append("archivo", archivo);
    setEnviando(true);
    setError(null);
    try {
      await subirConProgreso("/novedades", fd, () => {});
      alPublicar();
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(false);
    }
  };
  const destino = areas.find((a) => String(a.id) === area);
  return (
    <form className="formulario form-novedad" onSubmit={publicar}>
      <label className="campo">
        <span className="campo-etiqueta">Para</span>
        <select value={area} onChange={(e) => setArea(e.target.value)} disabled={areas.length === 1}>
          {areas.map((a) => (
            <option key={String(a.id)} value={String(a.id)}>
              {a.nombre}
            </option>
          ))}
        </select>
        {areas.length === 1 && yo.area && <span className="campo-ayuda">Publica para su área. Las novedades para todos las publica la Dirección.</span>}
      </label>
      <label className="campo">
        <span className="campo-etiqueta">Título *</span>
        <input required minLength={3} value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Ej.: Circular 3/2026 — Nuevo horario de atención" />
      </label>
      <div className="campo">
        <span className="campo-etiqueta">Texto</span>
        <BarraFormato />
        <EditorTexto uid="novedad-nueva" inicial="" alCambiar={setCuerpo} etiqueta="Texto de la novedad" placeholder="Lo que todos tienen que saber…" />
      </div>
      <div className="campo">
        <span className="campo-etiqueta">Circular o documento adjunto (PDF, JPG o PNG)</span>
        <input ref={entrada} type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
      </div>
      <label className="casilla">
        <input type="checkbox" checked={confirmacion} onChange={(e) => setConfirmacion(e.target.checked)} /> Pedir confirmación de lectura
      </label>
      <label className="casilla">
        <input type="checkbox" checked={fijada} onChange={(e) => setFijada(e.target.checked)} /> Fijar arriba de todo
      </label>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          {enviando ? "Publicando…" : `Publicar para ${destino ? (destino.id === null ? "toda la Dirección" : corta(destino.nombre)) : "…"}`}
        </button>
      </div>
    </form>
  );
}

/** Bloque del inicio: novedades sin confirmar (computadora y celular). */
export function NovedadesPendientes({ movil }: { movil?: boolean }) {
  const { datos } = usePendientes();
  const envio = useEnvio();
  if (!datos || datos.cantidad === 0) return null;
  const ruta = movil ? "#/m/novedades" : "#/novedades";
  return (
    <section className={`novedades-inicio ${movil ? "novedades-inicio-movil" : ""}`} aria-label="Novedades sin confirmar">
      <header>
        <strong>
          {datos.cantidad === 1 ? "1 novedad para leer" : `${datos.cantidad} novedades para leer`}
        </strong>
        <a href={`${ruta}?filtro=pendientes`}>Ver todas</a>
      </header>
      {datos.novedades.map((n) => (
        <div key={n.id} className="novedad-inicio">
          <div>
            <small>{n.area ? corta(n.area) : "Dirección"} · {fechaHora(n.publicada_en)}</small>
            <a href={`${ruta}?filtro=pendientes`}>
              <strong>{n.titulo}</strong>
            </a>
            {n.resumen && <p>{n.resumen}</p>}
            {n.archivo && (
              <a href={`/api/novedades/${n.id}/archivo`} target="_blank" rel="noreferrer">
                📎 Ver la circular
              </a>
            )}
          </div>
          <button
            type="button"
            className={movil ? "m-boton" : "boton boton-chico boton-primario"}
            disabled={envio.enviando}
            onClick={() => envio.ejecutar(() => api.post(`/novedades/${n.id}/confirmar`)).then((r) => r && avisarCambio())}
          >
            Leí y estoy al tanto
          </button>
        </div>
      ))}
      <Aviso error={envio.error} />
    </section>
  );
}

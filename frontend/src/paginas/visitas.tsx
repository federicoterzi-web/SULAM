// Mapa de casos y armado de salidas de visita.
import { useMemo, useState } from "react";
import { api, type UsuarioBreve } from "../api";
import { Aviso, Cargando, Enlace, ESTADOS, Seccion, Vacio, fecha, useDatos } from "../comun";
import { MapaRecursos, type Punto } from "../mapa";
import { enlacesRecorrido, kilometros, ordenarRecorrido, type Lugar } from "../rutas";
import { useConfigMapa } from "./ubicacion";
import type { Recurso } from "./recursos";

export interface CasoEnMapa {
  caso_id: string;
  numero: string;
  actuacion: string;
  estado: string;
  reservado: boolean;
  area: string | null;
  responsables: UsuarioBreve[];
  maltrato: boolean;
  sin_actividad: boolean;
  ultima_evolucion: string | null;
  persona: { id: string; nombre: string; domicilio: string | null; localidad: string | null; departamento: string | null; telefono: string | null };
  lat?: number;
  lng?: number;
}

export interface MapaCasos {
  puntos: (CasoEnMapa & { lat: number; lng: number })[];
  sin_ubicacion: CasoEnMapa[];
  partida: [number, number];
}

export type Alcance = "mios" | "area" | "todos";

export function tipoDePunto(c: CasoEnMapa) {
  return c.maltrato ? "caso-grave" : c.sin_actividad ? "caso-quieto" : "caso";
}

/** Estado compartido por la versión de escritorio y la de celular. */
export function useSalida(datos: MapaCasos | null, partida: Lugar | null) {
  const [elegidos, setElegidos] = useState<string[]>([]);
  const orden = useMemo(() => {
    if (!datos || !partida) return [];
    const sel = datos.puntos.filter((p) => elegidos.includes(p.caso_id));
    return ordenarRecorrido(partida, sel);
  }, [datos, partida, elegidos]);
  const alternar = (id: string) => setElegidos((e) => (e.includes(id) ? e.filter((x) => x !== id) : [...e, id]));
  return { elegidos, orden, alternar, vaciar: () => setElegidos([]) };
}

export function puntosDelMapa(datos: MapaCasos | null, orden: { caso_id: string }[], recursos: Recurso[] = []): Punto[] {
  const posicion = new Map(orden.map((o, i) => [o.caso_id, i + 1]));
  return [
    ...(datos?.puntos ?? []).map((c) => ({
      id: c.caso_id,
      lat: c.lat,
      lng: c.lng,
      // En la salida: marcador más grande, con el número de parada.
      tipo: posicion.has(c.caso_id) ? `${tipoDePunto(c)} pin-en-salida` : tipoDePunto(c),
      titulo: `${c.persona.nombre}${c.persona.domicilio ? ` · ${c.persona.domicilio}` : ""}`,
      etiqueta: posicion.has(c.caso_id) ? String(posicion.get(c.caso_id)) : "",
    })),
    ...recursos.filter((r) => r.lat !== null).map((r) => ({ id: "r:" + r.id, lat: r.lat!, lng: r.lng!, tipo: r.tipo, titulo: r.nombre })),
  ];
}

export function PaginaVisitas() {
  const cfg = useConfigMapa();
  const [de, setDe] = useState<Alcance>("mios");
  const [conRecursos, setConRecursos] = useState(false);
  const [elegido, setElegido] = useState<string | null>(null);
  const { datos, error } = useDatos(() => api.get<MapaCasos>("/mapa/casos", { de }), [de]);
  const recursos = useDatos(() => (conRecursos ? api.get<Recurso[]>("/recursos") : Promise.resolve([] as Recurso[])), [conRecursos]);
  const partida = cfg.datos ? { lat: cfg.datos.partida[0], lng: cfg.datos.partida[1] } : null;
  const salida = useSalida(datos, partida);
  const puntos = useMemo(() => puntosDelMapa(datos, salida.orden, recursos.datos ?? []), [datos, salida.orden, recursos.datos]);

  if (cfg.error || error) return <Aviso error={cfg.error ?? error} />;
  if (!cfg.datos || !datos) return <Cargando />;
  const enlaces = enlacesRecorrido(salida.orden, partida);

  return (
    <>
      <div className="inicio-cabecera">
        <h1>Mapa de casos y salidas</h1>
        <div className="segmentado" role="group" aria-label="Qué casos mostrar">
          {(
            [
              ["mios", "Mis casos"],
              ["area", "Mi área"],
              ["todos", "Todos"],
            ] as [Alcance, string][]
          ).map(([k, t]) => (
            <button key={k} className={de === k ? "activo" : ""} onClick={() => setDe(k)}>
              {t}
            </button>
          ))}
        </div>
      </div>
      <p className="tenue">
        Casos activos con el domicilio ubicado. Elija los que va a visitar: SULAM sugiere un orden y arma el recorrido. Rojo: maltrato ·
        naranja: sin movimiento hace más de 30 días.{" "}
        <label className="casilla casilla-linea">
          <input type="checkbox" checked={conRecursos} onChange={(e) => setConRecursos(e.target.checked)} /> Mostrar también recursos
        </label>
      </p>
        <section className="salida">
          <h2>
            Salida {salida.orden.length > 0 && `· ${salida.orden.length} ${salida.orden.length === 1 ? "parada" : "paradas"} · ~${kilometros(partida!, salida.orden)} km en línea recta`}
          </h2>
          {salida.orden.length === 0 ? (
            <p className="tenue">Toque un caso en el mapa o use «Agregar» en la lista.</p>
          ) : (
            <>
              <ol className="salida-lista">
                {salida.orden.map((c) => (
                  <li key={c.caso_id}>
                    <strong>{c.persona.nombre}</strong>
                    <span className="tenue"> · {c.persona.domicilio ?? "sin dirección"}</span>
                    <button className="boton-enlace" onClick={() => salida.alternar(c.caso_id)}>
                      quitar
                    </button>
                  </li>
                ))}
              </ol>
              <div className="fila-botones fila-izquierda">
                {enlaces.map((u, i) => (
                  <a key={u} className="boton boton-primario boton-chico" href={u} target="_blank" rel="noreferrer">
                    {enlaces.length === 1 ? "Abrir recorrido en Google Maps" : `Tramo ${i + 1} en Google Maps`}
                  </a>
                ))}
                <a className="boton boton-chico" href={`#/imprimir/salida?ids=${salida.orden.map((c) => c.caso_id).join(",")}`} target="_blank" rel="noreferrer">
                  Imprimir hoja de salida
                </a>
                <button className="boton boton-chico" onClick={salida.vaciar}>
                  Vaciar
                </button>
              </div>
            </>
          )}
        </section>
      <div className="recursos-vista">
        <MapaRecursos
          cfg={cfg.datos}
          puntos={puntos}
          elegido={elegido}
          alElegir={(id) => {
            if (id.startsWith("r:")) return;
            setElegido(id);
            salida.alternar(id);
          }}
        />
        <div className="recursos-lista">
          {datos.puntos.length === 0 && <Vacio>No hay casos activos con ubicación en esta vista.</Vacio>}
          {datos.puntos.map((c) => (
            <article key={c.caso_id} className={`recurso ${elegido === c.caso_id ? "recurso-elegido" : ""}`} onClick={() => setElegido(c.caso_id)}>
              <div className="recurso-cabecera">
                <span className={`pin pin-${tipoDePunto(c)} pin-chico`} aria-hidden />
                <Enlace a={`/casos/${c.caso_id}`}>
                  <strong>{c.persona.nombre}</strong>
                </Enlace>
              </div>
              <div className="tenue">
                {c.persona.domicilio ?? "Sin dirección"}
                {c.persona.localidad && `, ${c.persona.localidad}`}
              </div>
              <div className="tenue">
                Actuación {c.actuacion} · {ESTADOS[c.estado]} · {c.responsables.map((r) => r.nombre_completo).join(", ") || "sin responsable"}
                {c.ultima_evolucion && ` · última evolución ${fecha(c.ultima_evolucion)}`}
              </div>
              <button
                className={`boton boton-chico ${salida.elegidos.includes(c.caso_id) ? "" : "boton-primario"}`}
                onClick={(e) => {
                  e.stopPropagation();
                  salida.alternar(c.caso_id);
                }}
              >
                {salida.elegidos.includes(c.caso_id) ? "Quitar de la salida" : "Agregar a la salida"}
              </button>
            </article>
          ))}
        </div>
      </div>
      {datos.sin_ubicacion.length > 0 && (
        <Seccion titulo={`Sin ubicación (${datos.sin_ubicacion.length})`}>
          <p className="tenue">Para que aparezcan en el mapa, abra el legajo y marque el domicilio (o use la ubicación del celular en la próxima visita).</p>
          <ul className="lista-simple">
            {datos.sin_ubicacion.map((c) => (
              <li key={c.caso_id}>
                <Enlace a={`/legajos/${c.persona.id}`}>{c.persona.nombre}</Enlace> · {c.persona.domicilio ?? "sin dirección"}
                {c.persona.localidad && `, ${c.persona.localidad}`}
              </li>
            ))}
          </ul>
        </Seccion>
      )}
    </>
  );
}

/** Hoja de salida imprimible, en el orden elegido. */
export function HojaDeSalida({ ids }: { ids: string[] }) {
  const { datos, error } = useDatos(() => api.get<MapaCasos>("/mapa/casos", { de: "todos" }), []);
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  const porId = new Map(datos.puntos.map((p) => [p.caso_id, p]));
  const paradas = ids.map((id) => porId.get(id)).filter(Boolean) as MapaCasos["puntos"];
  return (
    <article className="hoja hoja-salida">
      <header className="encabezado-imp">
        <h1>Hoja de salida · {fecha(new Date().toISOString())}</h1>
      </header>
      <p>
        {paradas.length} {paradas.length === 1 ? "visita" : "visitas"}, en el orden sugerido. Equipo: ______________________________
      </p>
      <table className="tabla-salida">
        <thead>
          <tr>
            <th>#</th>
            <th>Persona</th>
            <th>Domicilio</th>
            <th>Teléfono</th>
            <th>Caso</th>
            <th>Hora · observaciones</th>
          </tr>
        </thead>
        <tbody>
          {paradas.map((c, i) => (
            <tr key={c.caso_id}>
              <td>{i + 1}</td>
              <td>
                <strong>{c.persona.nombre}</strong>
                {c.maltrato && <div>▲ Maltrato</div>}
              </td>
              <td>{[c.persona.domicilio, c.persona.localidad].filter(Boolean).join(", ") || "—"}</td>
              <td>{c.persona.telefono ?? "—"}</td>
              <td>
                {c.actuacion}
                <div className="pie-imp-chico">{c.responsables.map((r) => r.nombre_completo).join(", ")}</div>
              </td>
              <td className="celda-notas" />
            </tr>
          ))}
        </tbody>
      </table>
      <p className="pie-imp">Generado por SULAM. Contiene datos personales: no dejar a la vista ni descartar sin destruir.</p>
    </article>
  );
}

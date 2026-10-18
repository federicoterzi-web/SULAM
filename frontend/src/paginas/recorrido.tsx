// Recorrido de una salida ya agendada: volver a ver el orden de las paradas, abrirlo en Google Maps e imprimir la hoja de salida.
import { api } from "../api";
import { Aviso, Cargando, useDatos, useSesion } from "../comun";
import { enlacesRecorrido } from "../rutas";
import type { MapaCasos } from "./visitas";

interface Parada {
  orden: number;
  evento_id: string;
  estado: "programado" | "realizado" | "no_realizado" | "cancelado";
  caso_id: string | null;
  persona: string | null;
  actual: boolean;
}

const ICONO: Record<string, string> = { programado: "🕒", realizado: "✅", no_realizado: "⚠️", cancelado: "✖️" };

export function RecorridoSalida({ actividadId }: { actividadId: string }) {
  const { puede } = useSesion();
  const salida = useDatos(() => api.get<{ inicio: string; paradas: Parada[] }>(`/agenda/${actividadId}/salida`), [actividadId]);
  // El mapa trae domicilio y coordenadas de los casos activos a los que se tiene acceso; si no hay permiso, queda solo la lista.
  const mapa = useDatos(
    () => (puede("casos", "consultar") ? api.get<MapaCasos>("/mapa/casos", { de: "todos" }).catch(() => null) : Promise.resolve(null)),
    [actividadId],
  );
  if (salida.error) return <Aviso error={salida.error} />;
  if (!salida.datos) return <Cargando />;
  const paradas = salida.datos.paradas;
  if (paradas.length === 0) return null;
  const puntos = new Map((mapa.datos?.puntos ?? []).map((p) => [p.caso_id, p]));
  const ubicadas = paradas.map((p) => (p.caso_id ? puntos.get(p.caso_id) : undefined)).filter(Boolean) as { lat: number; lng: number }[];
  const partida = mapa.datos ? { lat: mapa.datos.partida[0], lng: mapa.datos.partida[1] } : null;
  const enlaces = ubicadas.length > 0 ? enlacesRecorrido(ubicadas, partida) : [];
  const ids = paradas.map((p) => p.caso_id).filter(Boolean).join(",");
  return (
    <section className="recorrido-salida">
      <h3>
        Recorrido de la salida · {paradas.length} {paradas.length === 1 ? "parada" : "paradas"}
      </h3>
      <ol className="salida-lista">
        {paradas.map((p) => (
          <li key={p.evento_id} className={p.actual ? "recorrido-actual" : ""}>
            {ICONO[p.estado]} {p.persona ?? "Sin legajo"}
            {p.actual && <small className="tenue"> · esta visita</small>}
          </li>
        ))}
      </ol>
      <div className="fila-botones fila-izquierda">
        {enlaces.map((u, i) => (
          <a key={u} className="boton boton-primario boton-chico" href={u} target="_blank" rel="noreferrer">
            {enlaces.length === 1 ? "Ver el recorrido en Google Maps" : `Tramo ${i + 1} en Google Maps`}
          </a>
        ))}
        {ids && (
          <a className="boton boton-chico" href={`#/imprimir/salida?ids=${ids}`} target="_blank" rel="noreferrer">
            Imprimir hoja de salida
          </a>
        )}
      </div>
      {mapa.datos && ubicadas.length < paradas.length && (
        <p className="tenue">
          {paradas.length - ubicadas.length === 1 ? "Una parada no aparece" : `${paradas.length - ubicadas.length} paradas no aparecen`} en el recorrido: el caso se cerró, no tiene el
          domicilio ubicado en el mapa o no está a su alcance.
        </p>
      )}
    </section>
  );
}

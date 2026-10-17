// Salida de visitas desde el celular: elegir casos en el mapa y abrir el recorrido.
import { useMemo, useState } from "react";
import { api } from "../api";
import { Aviso, Cargando, useDatos } from "../comun";
import { MapaRecursos } from "../mapa";
import { enlacesRecorrido, kilometros, type Lugar } from "../rutas";
import { ubicacionActual, useConfigMapa } from "../paginas/ubicacion";
import { puntosDelMapa, tipoDePunto, useSalida, type Alcance, type MapaCasos } from "../paginas/visitas";

export function VisitasMovil() {
  const cfg = useConfigMapa();
  const [de, setDe] = useState<Alcance>("mios");
  const [desde, setDesde] = useState<Lugar | null>(null);
  const [aviso, setAviso] = useState<unknown>(null);
  const { datos, error } = useDatos(() => api.get<MapaCasos>("/mapa/casos", { de }), [de]);
  const partida = desde ?? (cfg.datos ? { lat: cfg.datos.partida[0], lng: cfg.datos.partida[1] } : null);
  const salida = useSalida(datos, partida);
  const puntos = useMemo(() => puntosDelMapa(datos, salida.orden), [datos, salida.orden]);
  if (cfg.error || error) return <Aviso error={cfg.error ?? error} />;
  if (!cfg.datos || !datos) return <Cargando />;

  const usarMiUbicacion = async () => {
    setAviso(null);
    try {
      const u = await ubicacionActual();
      setDesde({ lat: u.lat, lng: u.lng });
    } catch (e) {
      setAviso(e);
    }
  };
  // Sin «origen», Google Maps arranca desde donde está el teléfono.
  const enlaces = enlacesRecorrido(salida.orden, null);

  return (
    <>
      <div className="m-segmentado" role="tablist">
        {(
          [
            ["mios", "Mis casos"],
            ["area", "Mi área"],
            ["todos", "Todos"],
          ] as [Alcance, string][]
        ).map(([k, t]) => (
          <button key={k} role="tab" aria-selected={de === k} className={de === k ? "activo" : ""} onClick={() => setDe(k)}>
            {t}
          </button>
        ))}
      </div>
      <MapaRecursos cfg={cfg.datos} puntos={puntos} alElegir={salida.alternar} alto="45vh" />
      <p className="m-tenue">Toque los casos para sumarlos a la salida. Rojo: maltrato · naranja: sin movimiento.</p>
      <Aviso error={aviso} />
      {salida.orden.length > 0 && (
        <div className="m-tarjeta m-cabecera">
          <strong>
            Salida: {salida.orden.length} {salida.orden.length === 1 ? "parada" : "paradas"} · ~{kilometros(partida!, salida.orden)} km
          </strong>
          <ol className="salida-lista">
            {salida.orden.map((c) => (
              <li key={c.caso_id}>
                {c.persona.nombre} <span className="m-detalle">· {c.persona.domicilio ?? "sin dirección"}</span>
              </li>
            ))}
          </ol>
          {!desde && (
            <button className="m-boton-texto" onClick={usarMiUbicacion}>
              Ordenar desde donde estoy
            </button>
          )}
          {enlaces.map((u, i) => (
            <a key={u} className="m-accion m-accion-principal" href={u} target="_blank" rel="noreferrer">
              <span className="m-accion-icono" aria-hidden>
                ➜
              </span>
              {enlaces.length === 1 ? "Abrir recorrido en el mapa" : `Tramo ${i + 1}`}
            </a>
          ))}
          <button className="m-boton-texto" onClick={salida.vaciar}>
            Vaciar la salida
          </button>
        </div>
      )}
      {datos.puntos.map((c) => (
        <div key={c.caso_id} className="m-tarjeta">
          <span className="m-fila-titulo">
            <strong>
              <span className={`pin pin-${tipoDePunto(c)} pin-chico`} aria-hidden /> {c.persona.nombre}
            </strong>
          </span>
          <span className="m-detalle">{[c.persona.domicilio, c.persona.localidad].filter(Boolean).join(", ") || "Sin dirección"}</span>
          <div className="m-recurso-acciones">
            <button className={`m-accion ${salida.elegidos.includes(c.caso_id) ? "" : "m-accion-principal"}`} onClick={() => salida.alternar(c.caso_id)}>
              <span className="m-accion-icono" aria-hidden>
                {salida.elegidos.includes(c.caso_id) ? "−" : "+"}
              </span>
              {salida.elegidos.includes(c.caso_id) ? "Quitar de la salida" : "Agregar a la salida"}
            </button>
            <a className="m-accion" href={`#/m/caso/${c.caso_id}`}>
              <span className="m-accion-icono" aria-hidden>
                →
              </span>
              Abrir el caso
            </a>
          </div>
        </div>
      ))}
      {datos.sin_ubicacion.length > 0 && (
        <p className="m-tenue">
          {datos.sin_ubicacion.length} {datos.sin_ubicacion.length === 1 ? "caso no tiene" : "casos no tienen"} el domicilio ubicado. En la visita,
          abra el legajo y use «Estoy en el domicilio».
        </p>
      )}
    </>
  );
}

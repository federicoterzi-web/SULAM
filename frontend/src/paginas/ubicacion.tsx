// Ubicación del domicilio de la persona: se marca en el mapa o con el GPS en la visita.
import { useState } from "react";
import { api, type PersonaDetalle } from "../api";
import { Aviso, Cargando, fechaHora, useDatos, useEnvio } from "../comun";
import { MapaSelector, type ConfigMapa } from "../mapa";

export interface ConfigMapaCasos extends ConfigMapa {
  partida: [number, number];
}

export function useConfigMapa() {
  return useDatos(() => api.get<ConfigMapaCasos>("/mapa/config"), []);
}

/** Pide la ubicación al teléfono (GPS). */
export function ubicacionActual(): Promise<{ lat: number; lng: number; precision: number }> {
  return new Promise((ok, mal) => {
    if (!navigator.geolocation) return mal(new Error("Este dispositivo no permite obtener la ubicación."));
    navigator.geolocation.getCurrentPosition(
      (p) => ok({ lat: p.coords.latitude, lng: p.coords.longitude, precision: Math.round(p.coords.accuracy) }),
      (e) =>
        mal(
          new Error(
            e.code === e.PERMISSION_DENIED
              ? "No se dio permiso para usar la ubicación. Habilítelo en el navegador o marque el lugar en el mapa."
              : "No se pudo obtener la ubicación. Intente de nuevo al aire libre o marque el lugar en el mapa.",
          ),
        ),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
  });
}

export function UbicacionDomicilio({
  persona,
  puedeModificar,
  alCambiar,
}: {
  persona: Pick<PersonaDetalle, "id" | "domicilio"> & { lat?: number | null; lng?: number | null; ubicacion_actualizada_en?: string | null };
  puedeModificar: boolean;
  alCambiar: () => void;
}) {
  const cfg = useConfigMapa();
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState<{ lat: number; lng: number } | null>(
    persona.lat != null && persona.lng != null ? { lat: persona.lat, lng: persona.lng } : null,
  );
  const [origen, setOrigen] = useState<"mapa" | "gps">("mapa");
  const [precision, setPrecision] = useState<number | null>(null);
  const { enviando, error, setError, ejecutar } = useEnvio();
  if (cfg.error) return <Aviso error={cfg.error} />;
  if (!cfg.datos) return <Cargando />;

  const guardar = async (v: { lat: number; lng: number } | null) => {
    const r = await ejecutar(() => api.put(`/personas/${persona.id}/ubicacion`, { lat: v?.lat ?? null, lng: v?.lng ?? null, origen }));
    if (r) {
      setEditando(false);
      alCambiar();
    }
  };
  const gps = async () => {
    setError(null);
    try {
      const u = await ubicacionActual();
      setValor({ lat: u.lat, lng: u.lng });
      setPrecision(u.precision);
      setOrigen("gps");
      setEditando(true);
    } catch (e) {
      setError(e);
    }
  };

  const tiene = persona.lat != null && persona.lng != null;
  return (
    <div className="ubicacion-domicilio">
      {!editando ? (
        <>
          <p className="tenue">
            {tiene
              ? `Ubicación marcada${persona.ubicacion_actualizada_en ? ` el ${fechaHora(persona.ubicacion_actualizada_en)}` : ""}. La ven los equipos para organizar las visitas.`
              : "Todavía sin ubicación: márquela para que el caso aparezca en el mapa de visitas."}
          </p>
          {tiene && <MapaSelector cfg={cfg.datos} valor={valor} alCambiar={() => {}} tipo="caso" />}
          {puedeModificar && (
            <div className="fila-botones fila-izquierda">
              <button className="boton boton-chico" onClick={gps}>
                Estoy en el domicilio: usar mi ubicación
              </button>
              <button className="boton boton-chico" onClick={() => setEditando(true)}>
                {tiene ? "Corregir en el mapa" : "Marcar en el mapa"}
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="tenue">
            {origen === "gps"
              ? `Ubicación tomada del GPS${precision ? ` (precisión aprox. ${precision} m)` : ""}. Si no coincide con la casa, arrastre el marcador.`
              : `Toque el mapa en la casa${persona.domicilio ? ` (${persona.domicilio})` : ""}; el marcador se puede arrastrar.`}
          </p>
          <MapaSelector cfg={cfg.datos} valor={valor} alCambiar={setValor} tipo="caso" />
          <div className="fila-botones fila-izquierda">
            <button className="boton boton-primario boton-chico" disabled={!valor || enviando} onClick={() => guardar(valor)}>
              Guardar ubicación
            </button>
            {tiene && (
              <button className="boton boton-chico" disabled={enviando} onClick={() => guardar(null)}>
                Quitar ubicación
              </button>
            )}
            <button className="boton boton-chico" onClick={() => setEditando(false)}>
              Cancelar
            </button>
          </div>
        </>
      )}
      <Aviso error={error} />
    </div>
  );
}

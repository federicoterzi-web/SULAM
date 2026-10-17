// Mapas con Leaflet (vendor/leaflet). Las teselas y la atribución vienen del servidor.
import { useEffect, useRef } from "react";
import * as L from "../vendor/leaflet/leaflet-src.esm.js";
import "../vendor/leaflet/leaflet.css";

export interface ConfigMapa {
  teselas: string;
  atribucion: string;
  centro: [number, number];
  caja: { oeste: number; sur: number; este: number; norte: number };
}

export interface Punto {
  id: string;
  lat: number;
  lng: number;
  tipo: string;
  titulo: string;
  /** Texto dentro del marcador (por defecto, la letra del tipo). */
  etiqueta?: string;
}

const LETRAS: Record<string, string> = {
  centro_dia: "D",
  centro_jubilados: "J",
  residencia: "R",
  institucion: "I",
  cuidador: "C",
};

function icono(tipo: string, elegido: boolean, etiqueta?: string) {
  const texto = (etiqueta ?? LETRAS[tipo] ?? "•").replace(/[<>&"]/g, "");
  return L.divIcon({
    className: `pin pin-${tipo} ${elegido ? "pin-elegido" : ""}`,
    html: `<span>${texto}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function crearMapa(div: HTMLDivElement, cfg: ConfigMapa) {
  const m = L.map(div, { zoomControl: true, attributionControl: true }).setView(cfg.centro, 12);
  L.tileLayer(cfg.teselas, { attribution: cfg.atribucion, maxZoom: 19 }).addTo(m);
  return m;
}

/** Mapa con los recursos. Tocar un punto lo elige. */
export function MapaRecursos({
  cfg,
  puntos,
  elegido,
  alElegir,
  alto = 520,
}: {
  cfg: ConfigMapa;
  puntos: Punto[];
  elegido?: string | null;
  alElegir?: (id: string) => void;
  alto?: number | string;
}) {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<any>(null);
  const capa = useRef<any>(null);
  const marcadores = useRef<Record<string, any>>({});
  const encuadre = useRef("");
  const elegirRef = useRef(alElegir);
  elegirRef.current = alElegir;

  useEffect(() => {
    if (!div.current) return;
    mapa.current = crearMapa(div.current, cfg);
    capa.current = L.layerGroup().addTo(mapa.current);
    return () => {
      mapa.current?.stop();
      mapa.current?.remove();
      mapa.current = null;
    };
  }, [cfg]);

  // Dibuja los puntos y encuadra el mapa cuando cambia la lista.
  useEffect(() => {
    if (!mapa.current) return;
    capa.current.clearLayers();
    marcadores.current = {};
    for (const p of puntos) {
      const mk = L.marker([p.lat, p.lng], { icon: icono(p.tipo, false, p.etiqueta), title: p.titulo, keyboard: true });
      mk.on("click", () => elegirRef.current?.(p.id));
      mk.bindTooltip(p.titulo, { direction: "top", offset: [0, -14] });
      mk.addTo(capa.current);
      marcadores.current[p.id] = mk;
    }
    const firma = puntos.map((p) => p.id).sort().join(",");
    if (puntos.length > 0 && firma !== encuadre.current) {
      encuadre.current = firma;
      mapa.current.fitBounds(L.latLngBounds(puntos.map((p) => [p.lat, p.lng])), { padding: [30, 30], maxZoom: 15 });
    }
  }, [puntos]);

  useEffect(() => {
    for (const [id, mk] of Object.entries(marcadores.current)) {
      const p = puntos.find((x) => x.id === id);
      if (p) mk.setIcon(icono(p.tipo, id === elegido, p.etiqueta));
    }
    const mk = elegido ? marcadores.current[elegido] : null;
    if (mk && mapa.current) mapa.current.panTo(mk.getLatLng());
  }, [elegido, puntos]);

  return <div ref={div} className="mapa" style={{ height: alto }} role="region" aria-label="Mapa de recursos" />;
}

/** Para marcar un lugar: tocar el mapa o arrastrar el marcador. */
export function MapaSelector({
  cfg,
  valor,
  alCambiar,
  tipo,
}: {
  cfg: ConfigMapa;
  valor: { lat: number; lng: number } | null;
  alCambiar: (v: { lat: number; lng: number }) => void;
  tipo: string;
}) {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<any>(null);
  const mk = useRef<any>(null);
  const cambiar = useRef(alCambiar);
  cambiar.current = alCambiar;

  useEffect(() => {
    if (!div.current) return;
    const m = crearMapa(div.current, cfg);
    mapa.current = m;
    m.on("click", (e: any) => cambiar.current({ lat: redondear(e.latlng.lat), lng: redondear(e.latlng.lng) }));
    return () => {
      m.stop();
      m.remove();
      mapa.current = null;
      mk.current = null;
    };
  }, [cfg]);

  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    if (!valor) {
      mk.current?.remove();
      mk.current = null;
      return;
    }
    if (!mk.current) {
      mk.current = L.marker([valor.lat, valor.lng], { draggable: true, icon: icono(tipo, true) }).addTo(m);
      mk.current.on("dragend", () => {
        const p = mk.current.getLatLng();
        cambiar.current({ lat: redondear(p.lat), lng: redondear(p.lng) });
      });
      m.setView([valor.lat, valor.lng], Math.max(m.getZoom(), 15), { animate: false });
    } else {
      mk.current.setLatLng([valor.lat, valor.lng]);
      mk.current.setIcon(icono(tipo, true));
      m.panTo([valor.lat, valor.lng], { animate: false });
    }
  }, [valor, tipo]);

  return <div ref={div} className="mapa mapa-selector" role="region" aria-label="Elegir la ubicación en el mapa" />;
}

function redondear(n: number) {
  return Math.round(n * 1e6) / 1e6;
}

export function enlaceComoLlegar(lat: number, lng: number) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

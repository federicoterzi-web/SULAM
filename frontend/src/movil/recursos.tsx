// Recursos en el celular: buscar, llamar y ver cómo llegar; el mapa, a un toque.
import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Cargando, useDatos } from "../comun";
import { MapaRecursos, enlaceComoLlegar, type Punto } from "../mapa";
import { telefonoLimpio, textoTipo, useCatalogoRecursos, type Recurso } from "../paginas/recursos";

export function RecursosMovil() {
  const cat = useCatalogoRecursos();
  const [tipo, setTipo] = useState("");
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const [verMapa, setVerMapa] = useState(false);
  const [elegido, setElegido] = useState<string | null>(null);
  const lista = useDatos(() => api.get<Recurso[]>("/recursos", { tipo: tipo || undefined, q: filtroQ }), [tipo, filtroQ]);
  const puntos = useMemo<Punto[]>(
    () => (lista.datos ?? []).filter((r) => r.lat !== null).map((r) => ({ id: r.id, lat: r.lat!, lng: r.lng!, tipo: r.tipo, titulo: r.nombre })),
    [lista.datos],
  );
  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  const c = cat.datos;
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    setFiltroQ(q.trim());
  };
  const mostrados = (lista.datos ?? []).filter((r) => !verMapa || !elegido || r.id === elegido);

  return (
    <>
      <form className="m-busqueda" onSubmit={enviar} role="search">
        <input type="search" enterKeyHint="search" placeholder="Nombre, localidad o servicio" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar recurso" />
        <button aria-label="Buscar">⌕</button>
      </form>
      <div className="m-chips" role="group" aria-label="Tipo">
        <button type="button" className={tipo === "" ? "activo" : ""} onClick={() => setTipo("")}>
          Todos
        </button>
        {c.tipos.map((t) => (
          <button key={t.codigo} type="button" className={tipo === t.codigo ? "activo" : ""} onClick={() => setTipo(t.codigo)}>
            <span className={`pin pin-${t.codigo} pin-chico`} aria-hidden /> {t.texto.replace(" domiciliario/a formado/a", "")}
          </button>
        ))}
      </div>
      <button type="button" className="m-boton-texto" onClick={() => setVerMapa(!verMapa)}>
        {verMapa ? "Ver solo la lista" : "Ver en el mapa"}
      </button>
      {verMapa && <MapaRecursos cfg={c.mapa} puntos={puntos} elegido={elegido} alElegir={setElegido} alto="50vh" />}
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : mostrados.length === 0 ? (
        <p className="m-tenue">No hay recursos con esa búsqueda.</p>
      ) : (
        mostrados.map((r) => (
          <div key={r.id} className="m-tarjeta">
            <strong className="m-nombre">
              <span className={`pin pin-${r.tipo} pin-chico`} aria-hidden /> {r.nombre}
            </strong>
            <span className="m-detalle">
              {textoTipo(c, r)}
              {(r.localidad || r.departamento) && ` · ${[r.localidad, r.departamento].filter(Boolean).join(", ")}`}
            </span>
            {r.tipo === "cuidador" && r.zonas.length > 0 && <span className="m-detalle">Trabaja en: {r.zonas.join(", ")}</span>}
            {r.referente && <span className="m-detalle">{r.referente}{r.referente_cargo && ` (${r.referente_cargo})`}</span>}
            {r.horario && <span className="m-detalle">{r.horario}</span>}
            <div className="m-recurso-acciones">
              {r.telefono && (
                <a className="m-llamar" href={`tel:${telefonoLimpio(r.telefono)}`}>
                  ✆ {r.telefono}
                </a>
              )}
              {r.lat !== null && r.lng !== null && (
                <a className="m-accion" href={enlaceComoLlegar(r.lat, r.lng)} target="_blank" rel="noreferrer">
                  <span className="m-accion-icono" aria-hidden>
                    ➜
                  </span>
                  Cómo llegar
                </a>
              )}
            </div>
          </div>
        ))
      )}
    </>
  );
}

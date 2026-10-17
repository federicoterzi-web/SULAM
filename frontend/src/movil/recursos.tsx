// Recursos en el celular: buscar, llamar y ver cómo llegar; el mapa, a un toque.
import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Cargando, useDatos, useSesion } from "../comun";
import { MapaRecursos, enlaceComoLlegar, type Punto } from "../mapa";
import { telefonoLimpio, textoTipo, useCatalogoRecursos, type CatalogoRecursos, type Recurso } from "../paginas/recursos";
import { enlaceWhatsapp, type Contacto } from "../paginas/contactos";

export function RecursosMovil() {
  const [vista, setVista] = useState<"lugares" | "contactos">("lugares");
  return (
    <>
      <div className="m-segmentado" role="tablist">
        <button role="tab" aria-selected={vista === "lugares"} className={vista === "lugares" ? "activo" : ""} onClick={() => setVista("lugares")}>
          Lugares
        </button>
        <button role="tab" aria-selected={vista === "contactos"} className={vista === "contactos" ? "activo" : ""} onClick={() => setVista("contactos")}>
          Contactos
        </button>
      </div>
      {vista === "lugares" ? <LugaresMovil /> : <ContactosMovil />}
    </>
  );
}

/** Quién puede editar una ficha: todos, o solo quien la cargó. */
function usePuedeEditar(cat: CatalogoRecursos | null) {
  const { yo } = useSesion();
  return (x: { creado_por?: string | null }) =>
    !!cat && (cat.puede.modificar === "todos" || (cat.puede.modificar === "propios" && x.creado_por === yo.id));
}

function ContactosMovil() {
  const cat = useCatalogoRecursos();
  const puedeEditar = usePuedeEditar(cat.datos);
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const lista = useDatos(() => api.get<Contacto[]>("/contactos", { q: filtroQ }), [filtroQ]);
  return (
    <>
      <form
        className="m-busqueda"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltroQ(q.trim());
        }}
      >
        <input type="search" enterKeyHint="search" placeholder="Nombre, institución, localidad o tema" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar contacto" />
        <button aria-label="Buscar">⌕</button>
      </form>
      {cat.datos?.puede.crear && (
        <a className="m-accion" href="#/m/contactos/nuevo">
          <span className="m-accion-icono" aria-hidden>
            ＋
          </span>
          Agregar contacto
        </a>
      )}
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <p className="m-tenue">No hay contactos con esa búsqueda.</p>
      ) : (
        lista.datos.map((c) => (
          <div key={c.id} className="m-tarjeta">
            <strong className="m-nombre">{c.nombre}</strong>
            <span className="m-detalle">{[c.cargo, c.institucion].filter(Boolean).join(" · ")}</span>
            {(c.localidad || c.departamento) && <span className="m-detalle">{[c.localidad, c.departamento].filter(Boolean).join(", ")}</span>}
            {c.temas && <span className="m-detalle">Temas: {c.temas}</span>}
            <div className="m-recurso-acciones">
              {c.telefono && (
                <a className="m-llamar" href={`tel:${telefonoLimpio(c.telefono)}`}>
                  ✆ {c.telefono}
                </a>
              )}
              {c.whatsapp && (
                <a className="m-accion" href={enlaceWhatsapp(c.whatsapp)} target="_blank" rel="noreferrer">
                  <span className="m-accion-icono" aria-hidden>
                    ✉
                  </span>
                  WhatsApp
                </a>
              )}
              {puedeEditar(c) && (
                <a className="m-accion" href={`#/m/contactos/${c.id}/editar`}>
                  <span className="m-accion-icono" aria-hidden>
                    ✎
                  </span>
                  Editar
                </a>
              )}
            </div>
          </div>
        ))
      )}
    </>
  );
}

function LugaresMovil() {
  const cat = useCatalogoRecursos();
  const [tipo, setTipo] = useState("");
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const [verMapa, setVerMapa] = useState(false);
  const [elegido, setElegido] = useState<string | null>(null);
  const puedeEditar = usePuedeEditar(cat.datos);
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
      {c.puede.crear && (
        <a className="m-accion" href="#/m/recursos/nuevo">
          <span className="m-accion-icono" aria-hidden>
            ＋
          </span>
          Agregar un lugar (centro, residencia, cuidador…)
        </a>
      )}
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
              {puedeEditar(r) && (
                <a className="m-accion" href={`#/m/recursos/${r.id}/editar`}>
                  <span className="m-accion-icono" aria-hidden>
                    ✎
                  </span>
                  Editar
                </a>
              )}
            </div>
          </div>
        ))
      )}
    </>
  );
}

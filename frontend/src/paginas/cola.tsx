// Cola de impresión: las carátulas nuevas quedan pendientes hasta imprimirlas,
// para cargar varios casos y mandarlos todos juntos a la impresora.
import { useEffect, useState } from "react";
import { api, type Caso } from "../api";
import { Aviso, Cargando, Enlace, Vacio, fecha, nombre, useDatos, useSesion } from "../comun";

type De = "mias" | "area" | "todas";

export function PaginaColaImpresion() {
  const { yo } = useSesion();
  const [de, setDe] = useState<De>("mias");
  const [elegidos, setElegidos] = useState<Set<string> | null>(null);
  const [formato, setFormato] = useState<"carpetas" | "caratulas">("carpetas");
  const { datos, error, recargar } = useDatos(() => api.get<Caso[]>("/caratulas/pendientes", { de }), [de]);

  // Al volver de la pestaña de impresión se actualiza la lista.
  useEffect(() => {
    const f = () => document.visibilityState === "visible" && recargar();
    document.addEventListener("visibilitychange", f);
    return () => document.removeEventListener("visibilitychange", f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => setElegidos(null), [datos]);

  const lista = datos ?? [];
  const sel = elegidos ?? new Set(lista.map((c) => c.id)); // por defecto, todas
  const alternar = (id: string) => {
    const n = new Set(sel);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setElegidos(n);
  };
  const ids = lista.filter((c) => sel.has(c.id)).map((c) => c.id);

  return (
    <>
      <h1>Imprimir carátulas</h1>
      <p className="tenue">
        Cada caso nuevo queda acá hasta que se imprime su carátula. Cargue los casos y después imprímalos todos juntos: cada
        carátula sale en su propia hoja, en orden de actuación.
      </p>
      <div className="filtros">
        <div className="segmentado" role="group" aria-label="Qué carátulas mostrar">
          <button className={de === "mias" ? "activo" : ""} onClick={() => setDe("mias")}>
            Las que creé yo
          </button>
          {yo.area && (
            <button className={de === "area" ? "activo" : ""} onClick={() => setDe("area")}>
              Mi área
            </button>
          )}
          <button className={de === "todas" ? "activo" : ""} onClick={() => setDe("todas")}>
            Todas
          </button>
        </div>
        <select value={formato} onChange={(e) => setFormato(e.target.value as typeof formato)} aria-label="Formato">
          <option value="carpetas">Carátula para carpeta</option>
          <option value="caratulas">Formato oficial</option>
        </select>
        <a
          className={`boton boton-primario ${ids.length === 0 ? "deshabilitado" : ""}`}
          href={ids.length ? `#/imprimir/${formato}?ids=${ids.join(",")}` : undefined}
          target="_blank"
          rel="noreferrer"
          aria-disabled={ids.length === 0}
        >
          Imprimir {ids.length} {ids.length === 1 ? "carátula" : "carátulas"}
        </a>
      </div>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : lista.length === 0 ? (
        <Vacio>No hay carátulas pendientes de impresión.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label="Elegir todas"
                  checked={ids.length === lista.length}
                  onChange={(e) => setElegidos(new Set(e.target.checked ? lista.map((c) => c.id) : []))}
                />
              </th>
              <th>Actuación</th>
              <th>Persona</th>
              <th>Área</th>
              <th>Creado</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id} onClick={() => alternar(c.id)} className="fila-elegible">
                <td>
                  <input type="checkbox" checked={sel.has(c.id)} onChange={() => alternar(c.id)} onClick={(e) => e.stopPropagation()} aria-label={`Elegir ${c.numero}`} />
                </td>
                <td>
                  <Enlace a={`/casos/${c.id}`}>
                    {c.caratula.numero_actuacion}/{c.caratula.anio_actuacion}
                  </Enlace>
                </td>
                <td>{c.persona && nombre(c.persona)}</td>
                <td>{c.area?.nombre ?? "—"}</td>
                <td>{fecha(c.abierto_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

/** Después de imprimir: confirmar para sacarlas de la cola. */
export function ConfirmarImpresion({ ids }: { ids: string[] }) {
  const [estado, setEstado] = useState<"pregunta" | "listo" | "error">("pregunta");
  const [impreso, setImpreso] = useState(false);
  useEffect(() => {
    const f = () => setImpreso(true);
    window.addEventListener("afterprint", f);
    return () => window.removeEventListener("afterprint", f);
  }, []);
  if (!impreso || ids.length === 0) return null;
  if (estado === "listo")
    return <div className="aviso aviso-exito no-imprimir confirmar-impresion">Listo: {ids.length === 1 ? "la carátula salió" : "las carátulas salieron"} de la cola de impresión.</div>;
  const marcar = () =>
    api
      .post("/caratulas/impresas", { caso_ids: ids })
      .then(() => setEstado("listo"))
      .catch(() => setEstado("error"));
  return (
    <div className="aviso aviso-info no-imprimir confirmar-impresion">
      <strong>¿Se {ids.length === 1 ? "imprimió bien la carátula" : `imprimieron bien las ${ids.length} carátulas`}?</strong>
      <div className="fila-botones">
        <button className="boton" onClick={() => setImpreso(false)}>
          No, la vuelvo a imprimir
        </button>
        <button className="boton boton-primario" onClick={marcar}>
          Sí, sacar de la cola
        </button>
      </div>
      {estado === "error" && <span>No se pudo registrar. Reintente.</span>}
    </div>
  );
}

// Equipo a cargo de un caso: varios técnicos, todos responsables por igual.
import { useMemo, useState, type FormEvent } from "react";
import { EtiquetaHoy, useHoy } from "./miasistencia";
import { api, type Caso } from "../api";
import { Aviso, useEnvio, useSesion } from "../comun";

type Usuario = { id: string; nombre_completo: string; area: string | null };

function areaCorta(a: string | null) {
  return (a ?? "Sin área").replace(/^(Departamento|División)\s+/, "");
}

/** Lista de casillas para elegir a los técnicos a cargo. Muestra primero el área del caso. */
export function SelectorEquipo({
  elegidos,
  alCambiar,
  areaPreferida,
}: {
  elegidos: string[];
  alCambiar: (ids: string[]) => void;
  areaPreferida?: string | null;
}) {
  const { catalogos, yo } = useSesion();
  const [filtro, setFiltro] = useState("");
  const usuarios = catalogos.usuarios_asignables;
  const hoy = useHoy().datos;
  const grupos = useMemo(() => {
    const preferida = areaPreferida ?? yo.area?.nombre ?? null;
    const porArea = new Map<string, Usuario[]>();
    for (const u of usuarios) {
      const k = u.area ?? "";
      if (!porArea.has(k)) porArea.set(k, []);
      porArea.get(k)!.push(u);
    }
    return Array.from(porArea.entries()).sort(([a], [b]) => (a === preferida ? -1 : b === preferida ? 1 : a.localeCompare(b)));
  }, [usuarios, areaPreferida, yo.area]);
  const elegidosSet = new Set(elegidos);
  const alternar = (id: string) => alCambiar(elegidosSet.has(id) ? elegidos.filter((x) => x !== id) : [...elegidos, id]);
  const q = filtro.trim().toLowerCase();
  const nombres = usuarios.filter((u) => elegidosSet.has(u.id)).map((u) => u.nombre_completo);
  return (
    <div className="selector-equipo">
      <p className="selector-equipo-resumen" aria-live="polite">
        {nombres.length === 0 ? "Sin técnicos a cargo todavía." : `A cargo (${nombres.length}): ${nombres.join(", ")}`}
      </p>
      {usuarios.length > 8 && (
        <input type="search" placeholder="Buscar por nombre" aria-label="Buscar técnico" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
      )}
      <div className="selector-equipo-lista">
        {grupos.map(([area, lista]) => {
          const visibles = lista.filter((u) => !q || u.nombre_completo.toLowerCase().includes(q) || elegidosSet.has(u.id));
          if (visibles.length === 0) return null;
          return (
            <fieldset key={area}>
              <legend>{areaCorta(area || null)}</legend>
              {visibles.map((u) => (
                <label key={u.id} className={`casilla ${elegidosSet.has(u.id) ? "elegido" : ""}`}>
                  <input type="checkbox" checked={elegidosSet.has(u.id)} onChange={() => alternar(u.id)} />
                  {u.nombre_completo}
                  <EtiquetaHoy hoy={hoy} usuarioId={u.id} />
                </label>
              ))}
            </fieldset>
          );
        })}
      </div>
    </div>
  );
}

/** Formulario para cambiar el equipo a cargo de un caso. */
export function FormEquipo({ caso, alGuardar }: { caso: Caso; alGuardar: () => void }) {
  const [elegidos, setElegidos] = useState(caso.responsables.map((r) => r.id));
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const actuales = new Set(caso.responsables.map((r) => r.id));
  const suman = elegidos.filter((id) => !actuales.has(id)).length;
  const salen = caso.responsables.filter((r) => !elegidos.includes(r.id)).length;
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.put(`/casos/${caso.id}/equipo`, { usuarios_ids: elegidos, motivo: motivo || null }));
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <p className="tenue">Marque a todos los técnicos que trabajan el caso. Todos quedan como responsables y lo ven en «Mis casos».</p>
      <SelectorEquipo elegidos={elegidos} alCambiar={setElegidos} areaPreferida={caso.area?.nombre} />
      <label className="campo">
        <span className="campo-etiqueta">Motivo del cambio</span>
        <input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Opcional (p. ej., se suma por la visita conjunta)" />
      </label>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando || (suman === 0 && salen === 0)}>
          {suman === 0 && salen === 0
            ? "Sin cambios"
            : [suman ? `Sumar ${suman}` : "", salen ? `quitar ${salen}` : ""].filter(Boolean).join(" y ").replace(/^q/, "Q")}
        </button>
      </div>
    </form>
  );
}

// Antecedentes: lo puede usar cualquier persona del equipo para saber si alguien ya tiene legajo.
// Muestra solo nombre, documento, fecha de carátula y responsable. Cada consulta queda auditada.

import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Seccion, Vacio, fecha, useEnvio } from "../comun";

interface Antecedente {
  nombre: string;
  documento: string | null;
  casos: { fecha_caratula: string; responsables: string[] }[];
}

export function PaginaAntecedentes() {
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<Antecedente[] | null>(null);
  const envio = useEnvio();
  const buscar = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 3) return;
    const r = await envio.ejecutar(() => api.get<Antecedente[]>("/antecedentes", { q: q.trim() }));
    if (r) setLista(r);
  };
  return (
    <div>
      <h1>Antecedentes</h1>
      <Seccion titulo="¿Ya tiene legajo?">
        <p className="tenue">Busque por apellido y nombre o por documento. Solo se muestra el nombre, el documento, la fecha de la carátula y quién tiene el caso. Cada búsqueda queda registrada.</p>
        <form onSubmit={buscar} className="fila-botones">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Apellido y nombre, o documento" aria-label="Buscar antecedentes" minLength={3} maxLength={100} style={{ flex: 1 }} autoFocus />
          <button className="boton boton-primario" disabled={envio.enviando || q.trim().length < 3}>
            Buscar
          </button>
        </form>
        {envio.error ? <Aviso error={envio.error} /> : null}
        {lista && lista.length === 0 && <Vacio>No hay antecedentes con ese nombre o documento.</Vacio>}
        {lista && lista.length > 0 && (
          <table className="tabla">
            <thead>
              <tr>
                <th>Persona</th>
                <th>Documento</th>
                <th>Fecha de carátula</th>
                <th>Responsable</th>
              </tr>
            </thead>
            <tbody>
              {lista.flatMap((p) =>
                (p.casos.length ? p.casos : [null]).map((c, i) => (
                  <tr key={p.nombre + (p.documento ?? "") + i}>
                    <td>{i === 0 ? p.nombre : ""}</td>
                    <td>{i === 0 ? (p.documento ?? "Sin documento") : ""}</td>
                    <td>{c ? fecha(c.fecha_caratula) : <span className="tenue">Tiene legajo, sin caso</span>}</td>
                    <td>{c ? (c.responsables.length ? c.responsables.join(", ") : <span className="tenue">Sin responsable</span>) : ""}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </Seccion>
    </div>
  );
}

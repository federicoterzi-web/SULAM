import { useState } from "react";
import { api, type Expediente } from "../api";
import { Aviso, Cargando, Enlace, Vacio, fecha, nombre, useDatos } from "../comun";

export function PaginaExpedientes() {
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState("");
  const { datos, error } = useDatos(() => api.get<Expediente[]>("/expedientes", { q: filtro, limite: 100 }), [filtro]);
  return (
    <>
      <h1>Expedientes</h1>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltro(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Número de expediente" aria-label="Número de expediente" />
        <button className="boton">Buscar</button>
      </form>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : datos.length === 0 ? (
        <Vacio>No se encontraron expedientes.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Número</th>
              <th>Tipo</th>
              <th>Persona</th>
              <th>Organismo</th>
              <th>Registrado</th>
            </tr>
          </thead>
          <tbody>
            {datos.map((x) => (
              <tr key={x.id}>
                <td>
                  <strong>{x.numero}</strong>
                  {x.contenido_restringido ? <div className="tenue">Carátula reservada</div> : x.caratula && <div className="tenue">{x.caratula}</div>}
                </td>
                <td>{x.tipo === "judicial" ? "Judicial" : "Administrativo"}</td>
                <td>{x.persona && <Enlace a={`/legajos/${x.persona.id}`}>{nombre(x.persona)}</Enlace>}</td>
                <td>{x.organismo ?? "—"}</td>
                <td>{fecha(x.creado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="tenue">Los expedientes se vinculan desde el legajo de la persona.</p>
    </>
  );
}

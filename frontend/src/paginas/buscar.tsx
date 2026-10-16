import { api, type Caso, type Expediente, type Ingreso, type PersonaResumen } from "../api";
import { Aviso, Cargando, Enlace, Seccion, Vacio, fecha, nombre, useDatos } from "../comun";
import { TablaCasos } from "./legajo";
import { ListaPersonas } from "./legajos";

interface Resultado {
  personas: PersonaResumen[];
  casos: Caso[];
  expedientes: Expediente[];
  ingresos: Ingreso[];
}

export function PaginaBuscar({ q }: { q: string }) {
  const { datos, error } = useDatos(() => api.get<Resultado>("/buscar", { q }), [q]);
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  const total = datos.personas.length + datos.casos.length + datos.expedientes.length + datos.ingresos.length;
  return (
    <>
      <h1>Resultados para «{q}»</h1>
      {total === 0 && <Vacio>No se encontraron coincidencias.</Vacio>}
      {datos.personas.length > 0 && (
        <Seccion titulo={`Legajos (${datos.personas.length})`}>
          <ListaPersonas personas={datos.personas} />
        </Seccion>
      )}
      {datos.casos.length > 0 && (
        <Seccion titulo={`Casos (${datos.casos.length})`}>
          <TablaCasos casos={datos.casos} conPersona />
        </Seccion>
      )}
      {datos.expedientes.length > 0 && (
        <Seccion titulo={`Expedientes (${datos.expedientes.length})`}>
          <ul className="lista-simple">
            {datos.expedientes.map((x) => (
              <li key={x.id}>
                <strong>{x.numero}</strong> ({x.tipo}) —{" "}
                {x.persona && <Enlace a={`/legajos/${x.persona.id}`}>{nombre(x.persona)}</Enlace>}
              </li>
            ))}
          </ul>
        </Seccion>
      )}
      {datos.ingresos.length > 0 && (
        <Seccion titulo={`Ingresos de Mesa de Entrada (${datos.ingresos.length})`}>
          <ul className="lista-simple">
            {datos.ingresos.map((i) => (
              <li key={i.id}>
                <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace> · {fecha(i.fecha_ingreso)} · {i.asunto}
              </li>
            ))}
          </ul>
        </Seccion>
      )}
    </>
  );
}

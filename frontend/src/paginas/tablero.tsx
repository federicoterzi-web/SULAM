import { api, type Caso } from "../api";
import { Aviso, Cargando, ESTADOS, Enlace, Estado, Reservado, Seccion, Vacio, fecha, nombre, useDatos, useSesion } from "../comun";

interface Tablero {
  mis_casos: Caso[];
  sin_actividad: Caso[];
  dias_sin_actividad: number;
  ingresos_pendientes: number | null;
  resumen_estados: Record<string, number>;
}

export function PaginaTablero() {
  const { yo, puede } = useSesion();
  const { datos, error } = useDatos(() => api.get<Tablero>("/tablero"), []);

  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;

  const sinActividad = new Set(datos.sin_actividad.map((c) => c.id));

  return (
    <>
      <h1>Hola, {yo.nombre_completo.split(" ")[0]}</h1>
      <div className="indicadores">
        <div className="indicador">
          <span className="indicador-valor">{datos.mis_casos.length}</span>
          <span className="indicador-texto">casos activos asignados a usted</span>
        </div>
        <div className={`indicador ${datos.sin_actividad.length ? "indicador-alerta" : ""}`}>
          <span className="indicador-valor">{datos.sin_actividad.length}</span>
          <span className="indicador-texto">sin movimientos hace más de {datos.dias_sin_actividad} días</span>
        </div>
        {datos.ingresos_pendientes !== null && (
          <Enlace a="/mesa" className={`indicador ${datos.ingresos_pendientes ? "indicador-alerta" : ""}`}>
            <span className="indicador-valor">{datos.ingresos_pendientes}</span>
            <span className="indicador-texto">ingresos de Mesa de Entrada sin legajo</span>
          </Enlace>
        )}
      </div>

      <Seccion
        titulo="Mis casos"
        acciones={puede("personas", "consultar") && <Enlace a="/legajos" className="boton">Buscar legajo</Enlace>}
      >
        {datos.mis_casos.length === 0 ? (
          <Vacio>No tiene casos activos asignados.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Caso</th>
                <th>Persona</th>
                <th>Estado</th>
                <th>Área</th>
                <th>Último movimiento</th>
              </tr>
            </thead>
            <tbody>
              {datos.mis_casos.map((c) => (
                <tr key={c.id} className={sinActividad.has(c.id) ? "fila-alerta" : ""}>
                  <td>
                    <Enlace a={`/casos/${c.id}`}>{c.numero}</Enlace> {c.reservado && <Reservado />}
                  </td>
                  <td>{c.persona && <Enlace a={`/legajos/${c.persona.id}`}>{nombre(c.persona)}</Enlace>}</td>
                  <td>
                    <Estado estado={c.estado} />
                  </td>
                  <td>{c.area?.nombre ?? "—"}</td>
                  <td>
                    {fecha(c.ultima_actividad)}
                    {sinActividad.has(c.id) && <span className="texto-alerta"> · sin actividad</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>

      {Object.keys(datos.resumen_estados).length > 0 && (
        <Seccion titulo="Casos a su alcance, por estado">
          <div className="indicadores">
            {Object.entries(ESTADOS).map(([k, t]) => (
              <Enlace key={k} a={`/casos?estado=${k}`} className="indicador indicador-chico">
                <span className="indicador-valor">{datos.resumen_estados[k] ?? 0}</span>
                <span className="indicador-texto">{t}</span>
              </Enlace>
            ))}
          </div>
        </Seccion>
      )}
    </>
  );
}

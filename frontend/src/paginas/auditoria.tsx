import { useState } from "react";
import { api, type EventoAuditoria } from "../api";
import { Aviso, Cargando, Enlace, Vacio, fechaHora, useDatos } from "../comun";

const ACCIONES = [
  "login", "login_fallido", "logout", "crear", "modificar", "consultar_legajo", "consultar_caso", "consultar_ingreso",
  "busqueda", "cargar", "descargar", "eliminar", "vincular", "asignar", "finalizar_asignacion", "cambiar_estado",
  "reabrir", "unificar", "modificar_permisos", "restablecer_password", "cambio_password", "consultar_auditoria",
];

export function PaginaAuditoria() {
  const [accion, setAccion] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const { datos, error } = useDatos(
    () =>
      api.get<EventoAuditoria[]>("/auditoria", {
        accion,
        desde: desde ? desde + "T00:00:00" : undefined,
        hasta: hasta ? hasta + "T23:59:59" : undefined,
        limite: 500,
      }),
    [accion, desde, hasta],
  );

  return (
    <>
      <h1>Auditoría</h1>
      <p className="tenue">
        Registro inalterable de operaciones y consultas. Las filas no pueden modificarse ni borrarse.
      </p>
      <div className="filtros">
        <select value={accion} onChange={(e) => setAccion(e.target.value)} aria-label="Acción">
          <option value="">Todas las acciones</option>
          {ACCIONES.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <label>
          Desde <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label>
          Hasta <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </label>
      </div>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : datos.length === 0 ? (
        <Vacio>Sin registros.</Vacio>
      ) : (
        <table className="tabla tabla-compacta">
          <thead>
            <tr>
              <th>Fecha y hora</th>
              <th>Usuario</th>
              <th>Acción</th>
              <th>Entidad</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {datos.map((a) => (
              <tr key={a.id}>
                <td>{fechaHora(a.en)}</td>
                <td>{a.usuario}</td>
                <td>
                  <code>{a.accion}</code>
                </td>
                <td>
                  {a.entidad}
                  {a.persona_id && (
                    <>
                      {" · "}
                      <Enlace a={`/legajos/${a.persona_id}`}>legajo</Enlace>
                    </>
                  )}
                </td>
                <td>
                  {a.detalle ? (
                    abierto === a.id ? (
                      <pre className="detalle-json" onClick={() => setAbierto(null)}>
                        {JSON.stringify(a.detalle, null, 2)}
                      </pre>
                    ) : (
                      <button className="boton boton-chico" onClick={() => setAbierto(a.id)}>
                        Ver
                      </button>
                    )
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

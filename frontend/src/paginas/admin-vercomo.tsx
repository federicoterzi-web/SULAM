// Administración › Ver como: modo debug para ver SULAM con los permisos de otro rol (solo lectura).
import { useState } from "react";
import { api, fijarVerComo } from "../api";
import { Aviso, Cargando, Seccion, useDatos } from "../comun";

interface Opciones {
  roles: { id: number; nombre: string }[];
  areas: { id: number; nombre: string }[];
}

export function VerComoAdmin() {
  const { datos, error } = useDatos(() => api.get<Opciones>("/admin/ver-como"), []);
  const [rol, setRol] = useState("");
  const [area, setArea] = useState("");
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  const entrar = () => {
    const r = datos.roles.find((x) => String(x.id) === rol);
    if (!r) return;
    fijarVerComo({ rol: r.id, area: area ? Number(area) : undefined, nombre: r.nombre });
    window.location.hash = "#/";
    window.location.reload();
  };
  return (
    <Seccion titulo="Ver SULAM como otro rol">
      <p>
        Modo de prueba: la aplicación se ve con los permisos, el menú y el tablero del rol que elijas. Es de <strong>solo lectura</strong>:
        no se puede guardar nada. Se cierra al salir del modo o al cerrar la pestaña.
      </p>
      <div className="fila-form">
        <label>
          Rol
          <select value={rol} onChange={(e) => setRol(e.target.value)}>
            <option value="">Elegir…</option>
            {datos.roles.map((r) => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        </label>
        <label>
          Área (para roles con alcance «área»)
          <select value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">La mía / sin área</option>
            {datos.areas.map((a) => (
              <option key={a.id} value={a.id}>{a.nombre}</option>
            ))}
          </select>
        </label>
      </div>
      <button className="boton boton-primario" disabled={!rol} onClick={entrar}>
        Ver como este rol
      </button>
    </Seccion>
  );
}

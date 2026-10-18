import { useState } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Seccion, fechaHora, useDatos, useEnvio, useSesion } from "../comun";

// ---------------------------------------------------------------- historial de pases de carpetas

interface PaseAdmin {
  id: number;
  tipo: "pedido" | "envio";
  objeto: { texto: string; persona_id: string };
  desde: { area: string | null; usuario: { nombre_completo: string } | null };
  hacia: { area: string; usuario: { nombre_completo: string } | null };
  motivo: string | null;
  estado: string;
  iniciado_por: { nombre_completo: string } | null;
  iniciado_en: string;
  resuelto_por: { nombre_completo: string } | null;
  resuelto_en: string | null;
  respuesta: string | null;
}

const ESTADOS: Record<string, string> = { pendiente: "Pendiente", hecho: "Hecho", rechazado: "Rechazado", cancelado: "Cancelado" };

export function HistorialPases() {
  const { catalogos } = useSesion();
  const [estado, setEstado] = useState("");
  const [tipo, setTipo] = useState("");
  const [area, setArea] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [pagina, setPagina] = useState(1);
  const filtros = { estado: estado || undefined, tipo: tipo || undefined, area_id: area || undefined, desde: desde || undefined, hasta: hasta || undefined };
  const { datos, error } = useDatos(
    () => api.get<{ total: number; pases: PaseAdmin[] }>("/admin/pases", { ...filtros, pagina, limite: 50 }),
    [estado, tipo, area, desde, hasta, pagina],
  );
  const consulta = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v) as [string, string][]).toString();
  const nuevo = (f: (v: string) => void) => (e: { target: { value: string } }) => {
    f(e.target.value);
    setPagina(1);
  };
  return (
    <Seccion titulo="Historial de pases de carpetas">
      <p className="tenue">Todos los pedidos y envíos de carpetas en papel, con quién los inició y quién los resolvió.</p>
      <div className="grilla">
        <Campo etiqueta="Estado">
          <select value={estado} onChange={nuevo(setEstado)}>
            <option value="">Todos</option>
            {Object.entries(ESTADOS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Clase">
          <select value={tipo} onChange={nuevo(setTipo)}>
            <option value="">Pedidos y envíos</option>
            <option value="pedido">Pedidos</option>
            <option value="envio">Envíos</option>
          </select>
        </Campo>
        <Campo etiqueta="Área (origen o destino)">
          <select value={area} onChange={nuevo(setArea)}>
            <option value="">Todas</option>
            {catalogos.areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Desde">
          <input type="date" value={desde} onChange={nuevo(setDesde)} />
        </Campo>
        <Campo etiqueta="Hasta">
          <input type="date" value={hasta} onChange={nuevo(setHasta)} />
        </Campo>
      </div>
      <p>
        <a className="boton boton-chico" href={`/api/admin/pases/exportar${consulta ? `?${consulta}` : ""}`}>
          Exportar a planilla (CSV)
        </a>
      </p>
      <Aviso error={error} />
      {!datos && !error && <Cargando />}
      {datos && (
        <>
          <p>
            <strong>{datos.total}</strong> {datos.total === 1 ? "pase" : "pases"}
          </p>
          <div className="tabla-scroll">
            <table className="tabla">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Carpeta</th>
                  <th>Clase</th>
                  <th>De</th>
                  <th>Hacia</th>
                  <th>Estado</th>
                  <th>Resolvió</th>
                </tr>
              </thead>
              <tbody>
                {datos.pases.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {fechaHora(p.iniciado_en)}
                      <br />
                      <small className="tenue">{p.iniciado_por?.nombre_completo}</small>
                    </td>
                    <td>
                      <a href={`#/legajos/${p.objeto.persona_id}`}>{p.objeto.texto}</a>
                      {p.motivo && <div className="tenue">{p.motivo}</div>}
                    </td>
                    <td>{p.tipo === "pedido" ? "Pedido" : "Envío"}</td>
                    <td>
                      {p.desde.area ?? "—"}
                      {p.desde.usuario && <div className="tenue">{p.desde.usuario.nombre_completo}</div>}
                    </td>
                    <td>
                      {p.hacia.area}
                      {p.hacia.usuario && <div className="tenue">{p.hacia.usuario.nombre_completo}</div>}
                    </td>
                    <td>{ESTADOS[p.estado] ?? p.estado}</td>
                    <td>
                      {p.resuelto_por?.nombre_completo ?? "—"}
                      {p.resuelto_en && <div className="tenue">{fechaHora(p.resuelto_en)}</div>}
                      {p.respuesta && <div className="tenue">{p.respuesta}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="band-grupos">
            <button className="boton boton-chico" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
              ◀ Anterior
            </button>
            <span>Página {pagina}</span>
            <button className="boton boton-chico" disabled={pagina * 50 >= datos.total} onClick={() => setPagina(pagina + 1)}>
              Siguiente ▶
            </button>
          </p>
        </>
      )}
    </Seccion>
  );
}

// ---------------------------------------------------------------- calibración del reconocimiento

interface Calibracion {
  activo: boolean;
  fragmentos: boolean;
  lector_disponible: boolean;
  total: number;
  por_campo: Record<string, Record<string, number>>;
}

const CAMPOS: Record<string, string> = {
  persona: "Legajo",
  tipo: "Tipo de documento",
  fecha_emision: "Fecha de emisión",
  vence: "Vencimiento",
  numero: "Número",
  hojas: "Agrupación de hojas",
  lectura: "Lectura del texto",
};

export function Calibracion() {
  const { datos, error, recargar } = useDatos(() => api.get<Calibracion>("/admin/calibracion"), []);
  const { enviando, error: errorEnvio, ejecutar } = useEnvio();
  const cambiar = async (activo: boolean, fragmentos: boolean) => {
    await ejecutar(() => api.put("/admin/calibracion", { activo, fragmentos }));
    recargar();
  };
  const vaciar = async () => {
    if (!window.confirm("¿Borrar todos los casos registrados? No se puede deshacer.")) return;
    await ejecutar(() => api.delete("/admin/calibracion"));
    recargar();
  };
  return (
    <Seccion titulo="Calibración del reconocimiento automático">
      <p className="tenue">
        Para mejorar la lectura de documentos. Cuando está activada, cada vez que se clasifican hojas desde la bandeja se compara lo que sugirió
        el sistema con lo que se confirmó. Se guardan solo las diferencias, <strong>sin nombres, números ni imágenes</strong>. El informe se
        exporta para ajustar las reglas.
      </p>
      <Aviso error={error || errorEnvio} />
      {!datos && !error && <Cargando />}
      {datos && (
        <>
          {!datos.lector_disponible && <p className="aviso aviso-error">El lector de texto no está instalado en este servidor: no hay nada para calibrar.</p>}
          <label className="campo campo-casilla">
            <input type="checkbox" checked={datos.activo} disabled={enviando} onChange={(e) => cambiar(e.target.checked, e.target.checked && datos.fragmentos)} />
            Registrar casos mientras se clasifican documentos
          </label>
          <label className="campo campo-casilla">
            <input type="checkbox" checked={datos.fragmentos} disabled={enviando || !datos.activo} onChange={(e) => cambiar(datos.activo, e.target.checked)} />
            Guardar también un fragmento del texto cuando falla un dato (con números y palabras en mayúscula tapados)
          </label>
          <p>
            <strong>{datos.total}</strong> casos registrados.
          </p>
          {datos.total > 0 && (
            <table className="tabla">
              <thead>
                <tr>
                  <th>Dato</th>
                  <th>Acertó</th>
                  <th>Corregido</th>
                  <th>No lo sugirió</th>
                  <th>Sugirió de más</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(datos.por_campo).map(([campo, r]) => (
                  <tr key={campo}>
                    <td>{CAMPOS[campo] ?? campo}</td>
                    <td>{r.acierto ?? 0}</td>
                    <td>{r.corregido ?? 0}</td>
                    <td>{r.faltante ?? 0}</td>
                    <td>{r.sobrante ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="band-grupos">
            <a className="boton boton-primario" href="/api/admin/calibracion/exportar" download>
              Exportar informe
            </a>
            <button className="boton boton-peligro" disabled={enviando || datos.total === 0} onClick={vaciar}>
              Borrar los casos registrados
            </button>
          </p>
        </>
      )}
    </Seccion>
  );
}

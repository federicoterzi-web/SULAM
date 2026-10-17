import { useState, type FormEvent } from "react";
import { api, type Caso } from "../api";
import { Aviso, Cargando, nombre, useDatos, useEnvio, useSesion } from "../comun";
import { hoy } from "../paginas/formularios";
import { avisar } from "./movil";

export function EvolucionMovil({ casoId }: { casoId: string }) {
  const { yo, catalogos } = useSesion();
  const { datos: caso, error: errorCaso } = useDatos(() => api.get<Caso>(`/casos/${casoId}`), [casoId]);
  const [texto, setTexto] = useState("");
  const [fechaEv, setFechaEv] = useState(hoy());
  const [autor, setAutor] = useState(yo.id);
  const [autorNombre, setAutorNombre] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  if (errorCaso) return <Aviso error={errorCaso} />;
  if (!caso) return <Cargando />;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() =>
      api.post(`/casos/${casoId}/evolucion`, {
        texto,
        fecha: fechaEv,
        autor_id: autor !== "__otro" ? autor : null,
        autor_nombre: autor === "__otro" ? autorNombre : null,
      }),
    );
    if (r) {
      avisar("Evolución guardada");
      history.back();
    }
  };

  const conocido = catalogos.usuarios_asignables.some((u) => u.id === yo.id);
  return (
    <form className="m-formulario" onSubmit={enviar}>
      <p className="m-contexto">
        {caso.persona && nombre(caso.persona)} · Actuación {caso.caratula.numero_actuacion}/{caso.caratula.anio_actuacion}
      </p>
      <label className="m-campo">
        <span>¿Qué se hizo?</span>
        <textarea
          rows={7}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          required
          minLength={2}
          autoFocus
          enterKeyHint="enter"
          placeholder="Intervención, novedades, próximos pasos…"
        />
        <small>Puede dictar con el micrófono del teclado.</small>
      </label>
      <div className="m-dos">
        <label className="m-campo">
          <span>Fecha</span>
          <input type="date" value={fechaEv} max={hoy()} onChange={(e) => setFechaEv(e.target.value)} required />
        </label>
        <label className="m-campo">
          <span>Realizada por</span>
          <select value={autor} onChange={(e) => setAutor(e.target.value)}>
            {!conocido && <option value={yo.id}>{yo.nombre_completo}</option>}
            {catalogos.usuarios_asignables.map((u) => (
              <option key={u.id} value={u.id}>
                {u.nombre_completo}
              </option>
            ))}
            <option value="__otro">Otra persona</option>
          </select>
        </label>
      </div>
      {autor === "__otro" && (
        <label className="m-campo">
          <span>Nombre de quien la realizó</span>
          <input value={autorNombre} onChange={(e) => setAutorNombre(e.target.value)} required autoCapitalize="words" />
        </label>
      )}
      <Aviso error={error} />
      <div className="m-pie-fijo">
        <button className="m-boton m-boton-primario" disabled={enviando}>
          {enviando ? "Guardando…" : "Guardar evolución"}
        </button>
      </div>
    </form>
  );
}

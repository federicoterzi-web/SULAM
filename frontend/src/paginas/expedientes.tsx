import { useState, type FormEvent } from "react";
import { BarraFiltros, parametroF, useFiltrosUrl } from "./filtros";
import { api, type Documento, type Expediente, type Ingreso } from "../api";
import { Aviso, Cargando, Enlace, Vacio, fecha, fechaHora, nombre, useDatos, useEnvio, useSesion } from "../comun";
import { CarpetaFisica } from "./archivo";
import { TablaDocumentos } from "./documentos";
import { DatosExpedienteMinisterio, type ExpedienteMinisterio } from "./ministerio";

export function PaginaExpedientes() {
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState("");
  const [filtros, setFiltros] = useFiltrosUrl();
  const [total, setTotal] = useState<number | null>(null);
  const { datos, error } = useDatos(async () => {
    const r = await api.get<{ total: number; items: Expediente[] }>("/expedientes", { q: filtro, limite: 300, con_total: true, f: parametroF(filtros) });
    setTotal(r.total);
    return r.items;
  }, [filtro, JSON.stringify(filtros)]);
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
      <BarraFiltros lista="expedientes" filtros={filtros} alCambiar={setFiltros} total={total} mostrados={datos?.length} sustantivo={["expediente", "expedientes"]} />
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
                  <strong>
                    <Enlace a={`/expedientes/${x.id}`}>{x.numero}</Enlace>
                  </strong>
                  {x.caratula && <div className="tenue">{x.caratula}</div>}
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

interface FichaExpediente extends Expediente {
  ministerio: (ExpedienteMinisterio & { movimientos?: ExpedienteMinisterio["movimientos"] }) | null;
  documentos: Documento[];
  ingresos: Ingreso[];
}

/** Ficha de un expediente: qué dice el Ministerio, dónde está la carpeta en papel y sus documentos digitales. */
export function PaginaExpediente({ id }: { id: string }) {
  const { datos: x, error, recargar } = useDatos(() => api.get<FichaExpediente>(`/expedientes/${id}`), [id]);
  if (error) return <Aviso error={error} />;
  if (!x) return <Cargando />;
  return (
    <>
      <p className="migas">
        <Enlace a="/expedientes">Expedientes</Enlace> › {x.numero}
      </p>
      <h1>Expediente {x.numero}</h1>
      <dl className="datos">
        <dt>Persona</dt>
        <dd>{x.persona && <Enlace a={`/legajos/${x.persona.id}`}>{nombre(x.persona)}</Enlace>}</dd>
        <dt>Tipo</dt>
        <dd>
          {x.tipo === "judicial" ? "Judicial" : "Administrativo"}
          {x.organismo && <> · {x.organismo}</>}
        </dd>
        {x.caratula && (
          <>
            <dt>Carátula</dt>
            <dd className="texto-largo">{x.caratula}</dd>
          </>
        )}
        {x.caso_id && (
          <>
            <dt>Caso</dt>
            <dd>
              <Enlace a={`/casos/${x.caso_id}`}>Ver el caso</Enlace>
            </dd>
          </>
        )}
        <dt>Registrado</dt>
        <dd>{fecha(x.creado_en)}</dd>
      </dl>

      <h2>Dónde está la carpeta en papel</h2>
      <CarpetaFisica expedienteId={x.id} />

      <h2>Documentos digitales</h2>
      <p className="tenue">
        Los documentos viven en SULAM. El Sistema de Expedientes del Ministerio solo registra por dónde pasa el papel.
      </p>
      <TablaDocumentos documentos={x.documentos} alCambiar={recargar} />
      <p className="tenue">Para agregar uno, digitalícelo desde el legajo y elija este expediente.</p>

      {x.ingresos.length > 0 && (
        <>
          <h2>Ingresos de Mesa de Entrada</h2>
          <ul>
            {x.ingresos.map((i) => (
              <li key={i.id}>
                <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace> · {fecha(i.fecha_ingreso)}
              </li>
            ))}
          </ul>
        </>
      )}

      {x.ministerio && <PasesMinisterio expedienteMinisterioId={x.ministerio.id} />}

      <h2>En el Sistema de Expedientes del Ministerio</h2>
      {x.ministerio ? (
        <DatosExpedienteMinisterio e={x.ministerio} />
      ) : (
        <Vacio>Este expediente no está vinculado al del Ministerio.</Vacio>
      )}
    </>
  );
}

interface PaseMinisterioPreparado {
  id: string;
  oficina_destino: string;
  fojas: number | null;
  nota: string | null;
  estado: "preparado" | "hecho" | "cancelado";
  creado_por: string | null;
  creado_en: string;
  resuelto_en: string | null;
  resuelto_detalle: string | null;
}

const ESTADO_PASE: Record<PaseMinisterioPreparado["estado"], string> = {
  preparado: "Preparado, falta darlo en el Ministerio",
  hecho: "Hecho en el Ministerio",
  cancelado: "Cancelado",
};

/** Prepara el pase del Ministerio: la extensión de Chrome lo precarga y la persona lo confirma allá. */
function PasesMinisterio({ expedienteMinisterioId }: { expedienteMinisterioId: string }) {
  const { puede } = useSesion();
  const { datos: pases, error, recargar } = useDatos(
    () => api.get<PaseMinisterioPreparado[]>(`/ministerio/expedientes/${expedienteMinisterioId}/pases`),
    [expedienteMinisterioId],
  );
  const { datos: oficinas } = useDatos(() => api.get<string[]>("/ministerio/oficinas"), []);
  const envio = useEnvio();
  const [destino, setDestino] = useState("");
  const [fojas, setFojas] = useState("");
  const [nota, setNota] = useState("");
  const pendiente = pases?.find((p) => p.estado === "preparado");

  const preparar = async (ev: FormEvent) => {
    ev.preventDefault();
    const r = await envio.ejecutar(() =>
      api.post(`/ministerio/expedientes/${expedienteMinisterioId}/pases`, {
        oficina_destino: destino,
        fojas: fojas === "" ? null : Number(fojas),
        nota: nota || null,
      }),
    );
    if (r) {
      setDestino("");
      setFojas("");
      setNota("");
      recargar();
    }
  };
  const cancelar = async (p: PaseMinisterioPreparado) => {
    if (!confirm("¿Cancelar el pase preparado?")) return;
    await envio.ejecutar(() => api.delete(`/ministerio/pases/${p.id}`));
    recargar();
  };

  return (
    <>
      <h2>Pase en el Sistema de Expedientes del Ministerio</h2>
      <p className="tenue">
        SULAM deja el pase preparado. Al abrir el expediente en el Ministerio, la extensión ofrece «Abrir el pase
        precargado» y completa el formulario; <strong>usted revisa y toca «Pasar» en el Ministerio</strong>. SULAM nunca lo
        da por usted. Cuando el Ministerio muestra el movimiento, el pase queda como hecho.
      </p>
      <Aviso error={error ?? envio.error} />
      {puede("expedientes", "modificar") &&
        (pendiente ? (
          <p>
            Ya hay un pase preparado. Cancélelo para preparar otro.
          </p>
        ) : (
          <form className="formulario" onSubmit={preparar}>
            <label>
              Oficina destino
              <input list="oficinas-ministerio" value={destino} onChange={(e) => setDestino(e.target.value)} required />
              <datalist id="oficinas-ministerio">
                {(oficinas ?? []).map((o) => (
                  <option key={o} value={o} />
                ))}
              </datalist>
              {oficinas && oficinas.length === 0 && (
                <span className="tenue">
                  Todavía no hay lista de oficinas: se completa sola la primera vez que se abre un pase en el Ministerio con la
                  extensión. Mientras tanto, escriba el nombre tal como figura allá.
                </span>
              )}
            </label>
            <label>
              Fojas
              <input type="number" min={0} value={fojas} onChange={(e) => setFojas(e.target.value)} />
            </label>
            <label>
              Nota de ingreso
              <textarea value={nota} onChange={(e) => setNota(e.target.value)} maxLength={2000} />
            </label>
            <button className="boton" disabled={envio.enviando}>
              Preparar el pase
            </button>
          </form>
        ))}
      {pases && pases.length > 0 && (
        <table className="tabla">
          <thead>
            <tr>
              <th>Destino</th>
              <th>Fojas</th>
              <th>Nota</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pases.map((p) => (
              <tr key={p.id}>
                <td>{p.oficina_destino}</td>
                <td>{p.fojas ?? "—"}</td>
                <td>{p.nota ?? "—"}</td>
                <td>
                  {ESTADO_PASE[p.estado]}
                  <div className="tenue">
                    Preparado por {p.creado_por ?? "—"} el {fechaHora(p.creado_en)}
                    {p.resuelto_detalle && <> · {p.resuelto_detalle}</>}
                  </div>
                </td>
                <td>
                  {p.estado === "preparado" && puede("expedientes", "modificar") && (
                    <button className="boton boton-chico" onClick={() => cancelar(p)}>
                      Cancelar
                    </button>
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

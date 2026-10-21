import { useState } from "react";
import { BarraFiltros, parametroF, useFiltrosUrl } from "./filtros";
import { api, type Documento, type Expediente, type Ingreso } from "../api";
import { Aviso, Cargando, Enlace, Vacio, fecha, nombre, useDatos } from "../comun";
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

      <h2>En el Sistema de Expedientes del Ministerio</h2>
      {x.ministerio ? (
        <DatosExpedienteMinisterio e={x.ministerio} />
      ) : (
        <Vacio>Este expediente no está vinculado al del Ministerio.</Vacio>
      )}
    </>
  );
}

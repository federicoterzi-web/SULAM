// Expedientes del Ministerio: lo que la extensión de Chrome trajo del Sistema de
// Expedientes del Ministerio de Desarrollo Social, y las claves para conectarla.
import { useState, type FormEvent } from "react";
import { api, type PersonaResumen } from "../api";
import {
  Aviso,
  Cargando,
  Enlace,
  Modal,
  Seccion,
  Vacio,
  fecha,
  fechaHora,
  nombre,
  useDatos,
  useEnvio,
  useSesion,
} from "../comun";

export interface MarcaMinisterio {
  fecha: string | null;
  usuario: string | null;
  texto: string | null;
}

export interface MovimientoMinisterio {
  ingreso: MarcaMinisterio | null;
  fojas_ingreso: number | null;
  oficina_origen: string | null;
  nota: string | null;
  oficina: string | null;
  recepcion: MarcaMinisterio | null;
  comentarios: string | null;
  egreso: MarcaMinisterio | null;
  estado: string | null;
  dias_sin_recepcion: number | null;
  dias_pendiente: number | null;
}

export interface ExpedienteMinisterio {
  id: string;
  clave: string;
  url: string | null;
  formato: string | null;
  nomenclador: string | null;
  asunto: string | null;
  causante: string | null;
  beneficiario: string | null;
  documento_beneficiario: string | null;
  prioridad: string | null;
  oficina_origen: string | null;
  fecha_ingreso_ministerio: string | null;
  asignado_a: string | null;
  fecha_asignacion: string | null;
  estado: string | null;
  oficina_actual: string | null;
  en_bandeja: boolean;
  ultima_sincronizacion_en: string;
  ingresos?: { id: string; numero: string; fecha_ingreso: string; vinculado: boolean }[];
  persona?: PersonaResumen | null;
  persona_sugerida?: PersonaResumen | null;
  movimientos?: MovimientoMinisterio[];
}

interface TokenIntegracion {
  id: string;
  nombre: string;
  prefijo: string;
  creado_en: string;
  ultimo_uso_en: string | null;
  revocado_en: string | null;
  token?: string;
}

export function PaginaMinisterio() {
  const { puede } = useSesion();
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState("");
  const [soloBandeja, setSoloBandeja] = useState(true);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [conectar, setConectar] = useState(false);
  const { datos, error } = useDatos(
    () => api.get<ExpedienteMinisterio[]>("/ministerio/expedientes", { q: filtro, en_bandeja: soloBandeja || undefined }),
    [filtro, soloBandeja],
  );

  return (
    <>
      <div className="titulo-pagina">
        <h1>Expedientes del Ministerio</h1>
        {puede("mesa_entrada", "crear") && (
          <button className="boton" onClick={() => setConectar(true)}>
            Conectar la extensión de Chrome
          </button>
        )}
      </div>
      <p className="tenue">
        Lo que la extensión «SULAM · Expedientes del Ministerio» leyó de la Bandeja de Entrada de la Dirección en el
        Sistema de Expedientes. Cada pase que llega a la Dirección se registra una sola vez como ingreso de Mesa de Entrada.
      </p>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltro(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="N° de expediente, asunto, beneficiario o DNI" aria-label="Buscar expediente del Ministerio" />
        <label className="casilla">
          <input type="checkbox" checked={soloBandeja} onChange={(e) => setSoloBandeja(e.target.checked)} />
          Solo los que están hoy en la Dirección
        </label>
        <button className="boton">Buscar</button>
      </form>
      <Aviso error={error} />
      {!datos ? (
        <Cargando />
      ) : datos.length === 0 ? (
        <Vacio>
          Todavía no hay expedientes sincronizados. Abra la Bandeja de Entrada del Sistema de Expedientes con la extensión
          instalada y use «Sincronizar con SULAM».
        </Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Expediente</th>
              <th>Nomenclador</th>
              <th>Asunto</th>
              <th>Beneficiario</th>
              <th>Ingreso SULAM</th>
              <th>Legajo</th>
            </tr>
          </thead>
          <tbody>
            {datos.map((e) => (
              <tr key={e.id}>
                <td>
                  <button type="button" className="boton-enlace" onClick={() => setAbierto(e.id)}>
                    {e.clave}
                  </button>
                  <div className="tenue">
                    {e.estado ?? "—"}
                    {e.asignado_a && <> · {e.asignado_a}</>}
                  </div>
                </td>
                <td>{e.nomenclador ?? "—"}</td>
                <td>{e.asunto ?? "—"}</td>
                <td>
                  {e.beneficiario ?? "—"}
                  {e.documento_beneficiario && <div className="tenue">DNI {e.documento_beneficiario}</div>}
                </td>
                <td>
                  {e.ingresos && e.ingresos.length > 0
                    ? e.ingresos.map((i) => (
                        <div key={i.id}>
                          <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace>
                        </div>
                      ))
                    : "—"}
                </td>
                <td>
                  <Legajo e={e} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {abierto && (
        <Modal titulo="Expediente del Ministerio" alCerrar={() => setAbierto(null)} ancho>
          <DetalleExpediente id={abierto} />
        </Modal>
      )}
      {conectar && (
        <Modal titulo="Conectar la extensión de Chrome" alCerrar={() => setConectar(false)} ancho>
          <ClavesIntegracion />
        </Modal>
      )}
    </>
  );
}

function Legajo({ e }: { e: ExpedienteMinisterio }) {
  if (e.persona) return <Enlace a={`/legajos/${e.persona.id}`}>{e.persona.numero_legajo}</Enlace>;
  if (e.persona_sugerida)
    return (
      <span>
        <span className="insignia pendiente">Sin vincular</span>
        <div className="tenue">
          Sugerido: <Enlace a={`/legajos/${e.persona_sugerida.id}`}>{nombre(e.persona_sugerida)}</Enlace>
        </div>
      </span>
    );
  return <span className="tenue">{e.ingresos && e.ingresos.length ? "Sin vincular" : "—"}</span>;
}

function DetalleExpediente({ id }: { id: string }) {
  const { datos: e, error } = useDatos(() => api.get<ExpedienteMinisterio>(`/ministerio/expedientes/${id}`), [id]);
  if (error) return <Aviso error={error} />;
  if (!e) return <Cargando />;
  return <DatosExpedienteMinisterio e={e} />;
}

export function DatosExpedienteMinisterio({ e }: { e: ExpedienteMinisterio }) {
  return (
    <>
      <dl className="datos">
        <dt>Expediente</dt>
        <dd>
          {e.clave}
          {e.url && (
            <>
              {" "}
              · <a href={e.url} target="_blank" rel="noreferrer">abrir en el Sistema de Expedientes</a>
            </>
          )}
        </dd>
        <dt>Nomenclador</dt>
        <dd>{e.nomenclador ?? "—"}</dd>
        <dt>Asunto</dt>
        <dd className="texto-largo">{e.asunto ?? "—"}</dd>
        <dt>Beneficiario</dt>
        <dd>
          {e.beneficiario ?? "—"}
          {e.documento_beneficiario && <> · DNI {e.documento_beneficiario}</>}
        </dd>
        <dt>Causante</dt>
        <dd>{e.causante ?? "—"}</dd>
        <dt>Prioridad</dt>
        <dd>{e.prioridad ?? "—"}</dd>
        <dt>Ingresó al Ministerio</dt>
        <dd>
          {fechaHora(e.fecha_ingreso_ministerio)}
          {e.oficina_origen && <> · {e.oficina_origen}</>}
        </dd>
        <dt>Dónde está</dt>
        <dd>
          {e.oficina_actual ?? "—"} · {e.estado ?? "—"}
          {e.asignado_a && <> · asignado a {e.asignado_a} el {fecha(e.fecha_asignacion)}</>}
        </dd>
        <dt>Leído por última vez</dt>
        <dd>{fechaHora(e.ultima_sincronizacion_en)}</dd>
      </dl>
      {e.movimientos && e.movimientos.length > 0 && (
        <>
          <h3>Pases</h3>
          <div className="tabla-desplazable">
            <table className="tabla">
              <thead>
                <tr>
                  <th>Ingreso</th>
                  <th>De</th>
                  <th>A</th>
                  <th>Nota</th>
                  <th>Recepción</th>
                  <th>Egreso</th>
                  <th>Fojas</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {e.movimientos.map((m, n) => (
                  <tr key={n}>
                    <td>{marca(m.ingreso)}</td>
                    <td>{m.oficina_origen ?? "—"}</td>
                    <td>{m.oficina ?? "—"}</td>
                    <td>
                      {m.nota ?? "—"}
                      {m.comentarios && <div className="tenue">{m.comentarios}</div>}
                    </td>
                    <td>{marca(m.recepcion)}</td>
                    <td>{marca(m.egreso)}</td>
                    <td>{m.fojas_ingreso ?? "—"}</td>
                    <td>{m.estado ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function marca(m: MarcaMinisterio | null): string {
  if (!m) return "—";
  return `${m.fecha ? fechaHora(m.fecha) : m.texto ?? ""}${m.usuario ? " · " + m.usuario : ""}`;
}

function ClavesIntegracion() {
  const { datos, error, recargar } = useDatos(() => api.get<TokenIntegracion[]>("/integracion/tokens"), []);
  const [nombreClave, setNombreClave] = useState("Chrome de la oficina");
  const [nueva, setNueva] = useState<TokenIntegracion | null>(null);
  const envio = useEnvio();
  const direccion = window.location.origin;

  const crear = async (ev: FormEvent) => {
    ev.preventDefault();
    const t = await envio.ejecutar(() => api.post<TokenIntegracion>("/integracion/tokens", { nombre: nombreClave }));
    if (t) {
      setNueva(t);
      recargar();
    }
  };
  const revocar = async (t: TokenIntegracion) => {
    if (!confirm(`¿Revocar la clave «${t.nombre}»? La extensión que la use deja de funcionar.`)) return;
    await envio.ejecutar(() => api.delete(`/integracion/tokens/${t.id}`));
    recargar();
  };

  return (
    <>
      <ol>
        <li>
          Instalar la extensión: en Chrome, <code>chrome://extensions</code> → activar «Modo de desarrollador» → «Cargar
          extensión sin empaquetar» → elegir la carpeta <code>extension-expedientes</code> del repositorio de SULAM.
        </li>
        <li>Generar acá una clave y copiarla (se muestra una sola vez).</li>
        <li>
          En las opciones de la extensión, pegar la dirección de SULAM (<code>{direccion}</code>) y la clave, y tocar
          «Probar conexión».
        </li>
        <li>Abrir la Bandeja de Entrada del Sistema de Expedientes y tocar «Sincronizar con SULAM».</li>
      </ol>
      <p className="tenue">
        La clave tiene los mismos permisos que usted. La extensión solo lee lo que usted ya puede ver en el Sistema de
        Expedientes; no recepciona ni da pases.
      </p>
      <form onSubmit={crear} className="filtros">
        <input value={nombreClave} onChange={(e) => setNombreClave(e.target.value)} aria-label="Nombre de la clave" maxLength={100} />
        <button className="boton boton-primario" disabled={envio.enviando}>
          Generar clave
        </button>
      </form>
      {nueva?.token && (
        <div className="aviso aviso-exito" role="status">
          Clave nueva (cópiela ahora, no se vuelve a mostrar):
          <div>
            <code style={{ userSelect: "all", wordBreak: "break-all" }}>{nueva.token}</code>
          </div>
          <button type="button" className="boton" onClick={() => navigator.clipboard?.writeText(nueva.token ?? "")}>
            Copiar
          </button>
        </div>
      )}
      <Aviso error={error || envio.error} />
      <Seccion titulo="Mis claves">
        {!datos ? (
          <Cargando />
        ) : datos.length === 0 ? (
          <Vacio>Todavía no generó ninguna clave.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Empieza con</th>
                <th>Creada</th>
                <th>Último uso</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {datos.map((t) => (
                <tr key={t.id}>
                  <td>{t.nombre}</td>
                  <td>
                    <code>{t.prefijo}…</code>
                  </td>
                  <td>{fechaHora(t.creado_en)}</td>
                  <td>{t.ultimo_uso_en ? fechaHora(t.ultimo_uso_en) : "—"}</td>
                  <td>
                    {t.revocado_en ? (
                      <span className="tenue">Revocada el {fechaHora(t.revocado_en)}</span>
                    ) : (
                      <button type="button" className="boton" onClick={() => revocar(t)}>
                        Revocar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>
    </>
  );
}

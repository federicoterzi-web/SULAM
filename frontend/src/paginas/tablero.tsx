// Página de inicio: cada rol ve lo que necesita para su trabajo (sulam/routers/inicio.py).
import { useState, type ReactNode } from "react";
import { FormEquipo } from "./equipo";
import { rutaInforme } from "./informes";
import { api, type Caso, type Documento, type Expediente, type Ingreso, type PersonaResumen } from "../api";
import { Aviso, Cargando, ESTADOS, Enlace, Estado, Modal, Seccion, Vacio, fecha, fechaHora, nombre, useDatos, useSesion } from "../comun";
import { TablaCasos } from "./legajo";
import { textoDe } from "./formularios";

interface Respuesta<T = any> {
  perfil: string | null;
  perfiles: { codigo: string; nombre: string }[];
  datos?: T;
}

function leerPreferido(): string | null {
  try {
    return localStorage.getItem("sulam.inicio");
  } catch {
    return null;
  }
}

function guardarPreferido(p: string) {
  try {
    localStorage.setItem("sulam.inicio", p);
  } catch {
    /* sin almacenamiento: se usa el inicio por defecto */
  }
}

export function PaginaTablero() {
  const { yo } = useSesion();
  const [perfil, setPerfil] = useState<string | null>(leerPreferido());
  const { datos, error } = useDatos(
    () =>
      api.get<Respuesta>("/inicio", { perfil: perfil ?? undefined }).catch((e) => {
        // Un inicio recordado que ya no corresponde a sus roles: se vuelve al suyo.
        if (perfil && e?.status === 403) {
          setPerfil(null);
          return api.get<Respuesta>("/inicio");
        }
        throw e;
      }),
    [perfil],
  );

  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;

  const saludo = (
    <div className="inicio-cabecera">
      <h1>Hola, {yo.nombre_completo.split(" ")[0]}</h1>
      {datos.perfiles.length > 1 && (
        <div className="segmentado" role="group" aria-label="Inicio">
          {datos.perfiles.map((p) => (
            <button
              key={p.codigo}
              className={p.codigo === datos.perfil ? "activo" : ""}
              onClick={() => {
                guardarPreferido(p.codigo);
                setPerfil(p.codigo);
              }}
            >
              {p.nombre}
            </button>
          ))}
        </div>
      )}
    </div>
  );

  const d = datos.datos;
  return (
    <>
      {saludo}
      {datos.perfil === "tecnico" ? (
        <InicioTecnico d={d} />
      ) : datos.perfil === "jefatura" ? (
        <InicioJefatura d={d} />
      ) : datos.perfil === "direccion" ? (
        <InicioDireccion d={d} />
      ) : datos.perfil === "mesa" ? (
        <InicioMesa d={d} />
      ) : datos.perfil === "carga" ? (
        <InicioCarga d={d} />
      ) : datos.perfil === "administrativo_area" ? (
        <InicioAdministrativo d={d} />
      ) : (
        <InicioGeneral />
      )}
    </>
  );
}

// ---------------------------------------------------------------- piezas

function Indicador({ valor, texto, a, alerta }: { valor: number | string; texto: string; a?: string; alerta?: boolean }) {
  const contenido = (
    <>
      <span className="indicador-valor">{valor}</span>
      <span className="indicador-texto">{texto}</span>
    </>
  );
  const clase = `indicador ${alerta ? "indicador-alerta" : ""}`;
  return a ? (
    <Enlace a={a} className={clase}>
      {contenido}
    </Enlace>
  ) : (
    <div className={clase}>{contenido}</div>
  );
}

function Actuacion({ c }: { c: Caso }) {
  return (
    <>
      <Enlace a={`/casos/${c.id}`}>
        {c.caratula?.numero_actuacion ? `Actuación ${c.caratula.numero_actuacion}/${c.caratula.anio_actuacion}` : c.numero}
      </Enlace>
    </>
  );
}

function Accesos({ children }: { children: ReactNode }) {
  return <div className="inicio-accesos">{children}</div>;
}

/** Lista corta de casos para el inicio: actuación, persona, motivo y apertura (sin repetir el área). */
function CasosCompactos({ casos, accion }: { casos: Caso[]; accion?: (c: Caso) => ReactNode }) {
  return (
    <table className="tabla tabla-compacta">
      <thead>
        <tr>
          <th>Actuación</th>
          <th>Persona</th>
          <th>Motivo</th>
          <th>Abierto</th>
          {accion && <th />}
        </tr>
      </thead>
      <tbody>
        {casos.map((c) => (
          <tr key={c.id}>
            <td>
              <Actuacion c={c} />
            </td>
            <td>{c.persona ? nombre(c.persona) : "—"}</td>
            <td className="celda-motivo">{c.motivo ?? ""}</td>
            <td>{fecha(c.abierto_en)}</td>
            {accion && <td className="celda-acciones">{accion(c)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function VerTodos({ a, cantidad, mostrados }: { a: string; cantidad: number; mostrados: number }) {
  if (cantidad <= mostrados) return null;
  return (
    <p className="ver-todos">
      <Enlace a={a}>Ver los {cantidad} →</Enlace>
    </p>
  );
}

// ---------------------------------------------------------------- técnico

interface CasoTecnico extends Caso {
  ultima_evolucion: { fecha: string; texto: string; autor: string | null } | null;
  alertas: { maltrato: boolean; sin_actividad: boolean; reiteracion_reciente: boolean; nuevo: boolean; sin_registro: boolean };
}

interface Borrador {
  id: string;
  titulo: string;
  version: number;
  actualizado_en: string;
  persona: PersonaResumen;
  actuacion: string | null;
}

function InicioTecnico({ d }: { d: { casos: CasoTecnico[]; borradores: Borrador[]; dias_sin_actividad: number } }) {
  const n = (k: keyof CasoTecnico["alertas"]) => d.casos.filter((c) => c.alertas[k]).length;
  return (
    <>
      <div className="indicadores">
        <Indicador valor={d.casos.length} texto="casos activos asignados a usted" />
        <Indicador valor={n("maltrato")} texto="con indicadores de maltrato" alerta={n("maltrato") > 0} />
        <Indicador valor={n("reiteracion_reciente")} texto="volvieron a consultar este mes" alerta={n("reiteracion_reciente") > 0} />
        <Indicador valor={n("sin_actividad")} texto={`sin movimiento hace más de ${d.dias_sin_actividad} días`} alerta={n("sin_actividad") > 0} />
      </div>
      {(d.borradores.length > 0 || n("sin_registro") > 0) && (
        <Seccion titulo="Para terminar">
          <ul className="lista-pendientes">
            {d.borradores.map((b) => (
              <li key={b.id}>
                <span className="pendiente-tipo">Informe en borrador</span>
                <Enlace a={rutaInforme(b.id)}>
                  {b.titulo}
                  {b.version > 1 ? ` (versión ${b.version})` : ""}
                </Enlace>{" "}
                · {nombre(b.persona)}
                {b.actuacion && ` · Actuación ${b.actuacion}`}
                <span className="tenue"> · editado {fechaHora(b.actualizado_en)}</span>
              </li>
            ))}
            {d.casos
              .filter((c) => c.alertas.sin_registro)
              .map((c) => (
                <li key={c.id}>
                  <span className="pendiente-tipo">Falta el registro de demanda</span>
                  <Actuacion c={c} /> · {c.persona && nombre(c.persona)}
                </li>
              ))}
          </ul>
        </Seccion>
      )}
      <Seccion titulo="Mis casos, por urgencia" acciones={<Enlace a="/legajos" className="boton">Buscar legajo</Enlace>}>
        {d.casos.length === 0 ? (
          <Vacio>No tiene casos activos asignados.</Vacio>
        ) : (
          <ul className="lista-casos-inicio">
            {d.casos.map((c) => (
              <li key={c.id} className={c.alertas.maltrato ? "caso-grave" : ""}>
                <div className="caso-inicio-titulo">
                  <span>
                    <Actuacion c={c} /> · <strong>{c.persona && nombre(c.persona)}</strong>
                  </span>
                  <Estado estado={c.estado} />
                </div>
                <div className="caso-inicio-marcas">
                  {c.alertas.maltrato && <span className="marca marca-grave">▲ Maltrato</span>}
                  {c.alertas.reiteracion_reciente && <span className="marca marca-alerta">↻ Volvió a consultar</span>}
                  {c.alertas.sin_actividad && <span className="marca marca-alerta">Sin movimiento desde {fecha(c.ultima_actividad)}</span>}
                  {c.alertas.nuevo && <span className="marca marca-info">Asignado esta semana</span>}
                </div>
                <p className="caso-inicio-evolucion">
                  {c.ultima_evolucion ? (
                    <>
                      <span className="tenue">
                        Última evolución, {fecha(c.ultima_evolucion.fecha)}
                        {c.ultima_evolucion.autor && ` (${c.ultima_evolucion.autor})`}:
                      </span>{" "}
                      {c.ultima_evolucion.texto}
                    </>
                  ) : (
                    <span className="tenue">Todavía sin evolución. {c.motivo && `Motivo: ${c.motivo}`}</span>
                  )}
                </p>
                <Enlace a={`/casos/${c.id}`} className="boton boton-chico">
                  Abrir y agregar evolución
                </Enlace>
              </li>
            ))}
          </ul>
        )}
      </Seccion>
    </>
  );
}

// ---------------------------------------------------------------- jefatura

interface Jefatura {
  sin_area?: boolean;
  area: { id: number; nombre: string };
  sin_responsable: Caso[];
  sin_responsable_cantidad: number;
  sin_actividad: Caso[];
  sin_actividad_cantidad: number;
  equipo: { id: string; nombre_completo: string; casos_activos: number; sin_actividad: number }[];
  mes: { desde: string; nuevas: number; reiteraciones: number; cerrados: number };
  activos: number;
  pendientes_impresion: number;
  dias_sin_actividad: number;
}

function InicioJefatura({ d: inicial }: { d: Jefatura }) {
  const [d, setD] = useState(inicial);
  const [equipoDe, setEquipoDe] = useState<Caso | null>(null);
  const recargar = async () => {
    const r = await api.get<Respuesta<Jefatura>>("/inicio", { perfil: "jefatura" });
    if (r.datos) setD(r.datos);
  };
  if (d.sin_area) return <Aviso error="Su usuario no tiene un área asignada. Pida a quien administra SULAM que la cargue." tipo="info" />;
  const maximo = Math.max(1, ...d.equipo.map((e) => e.casos_activos));
  return (
    <>
      <p className="inicio-area">{d.area.nombre}</p>
      <div className="indicadores">
        <Indicador
          valor={d.sin_responsable_cantidad}
          texto="casos sin técnico a cargo"
          alerta={d.sin_responsable_cantidad > 0}
          a={`/casos?sin_responsable=1&activos=1&area=${d.area.id}`}
        />
        <Indicador valor={d.activos} texto="casos activos del departamento" a="/casos" />
        <Indicador valor={d.mes.nuevas} texto="actuaciones nuevas este mes" />
        <Indicador valor={d.mes.reiteraciones} texto="reiteraciones este mes" />
        <Indicador valor={d.pendientes_impresion} texto="carátulas por imprimir" a="/imprimir-caratulas" alerta={d.pendientes_impresion > 0} />
      </div>

      <Seccion titulo="Equipo">
        {d.equipo.length === 0 ? (
          <Vacio>No hay otras personas cargadas en el área.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Persona</th>
                <th>Casos activos</th>
                <th>Sin movimiento</th>
              </tr>
            </thead>
            <tbody>
              {d.equipo.map((e) => (
                <tr key={e.id}>
                  <td>{e.nombre_completo}</td>
                  <td>
                    <span className="barra-carga" aria-hidden>
                      <span style={{ width: `${(e.casos_activos / maximo) * 100}%` }} />
                    </span>{" "}
                    {e.casos_activos}
                  </td>
                  <td>{e.sin_actividad ? <span className="texto-alerta">{e.sin_actividad}</span> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>

      <Seccion titulo="Para asignar">
        {d.sin_responsable.length === 0 ? (
          <Vacio>Todos los casos activos tienen técnico a cargo.</Vacio>
        ) : (
          <>
            <CasosCompactos
              casos={d.sin_responsable}
              accion={(c) => (
                <button className="boton boton-chico boton-primario" onClick={() => setEquipoDe(c)}>
                  Asignar equipo
                </button>
              )}
            />
            <VerTodos a={`/casos?sin_responsable=1&activos=1&area=${d.area.id}`} cantidad={d.sin_responsable_cantidad} mostrados={d.sin_responsable.length} />
          </>
        )}
      </Seccion>

      <Seccion titulo={`Sin movimiento hace más de ${d.dias_sin_actividad} días`}>
        {d.sin_actividad.length === 0 ? (
          <Vacio>Ninguno.</Vacio>
        ) : (
          <>
            <CasosCompactos casos={d.sin_actividad} />
            {d.sin_actividad_cantidad > d.sin_actividad.length && (
              <p className="tenue">Se muestran los {d.sin_actividad.length} más antiguos de {d.sin_actividad_cantidad}.</p>
            )}
          </>
        )}
      </Seccion>

      {equipoDe && (
        <Modal titulo={`Equipo a cargo · ${equipoDe.persona ? nombre(equipoDe.persona) : equipoDe.numero}`} alCerrar={() => setEquipoDe(null)} ancho>
          <FormEquipo
            caso={equipoDe}
            alGuardar={() => {
              setEquipoDe(null);
              recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

// ---------------------------------------------------------------- dirección

interface Direccion {
  anio: number;
  mes: string;
  por_area: { area: string; area_id: number | null; nuevas: number; reiteraciones: number; activos: number; cerrados: number; sin_responsable: number }[];
  totales: { nuevas: number; reiteraciones: number; activos: number; cerrados: number };
  maltrato_mes: { casos: number; por_tipo: Record<string, number> };
  sin_responsable: { cantidad: number };
  sin_actividad: number;
  informes_mes: number;
  recientes: Caso[];
  dias_sin_actividad: number;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function InicioDireccion({ d }: { d: Direccion }) {
  const { formularios: f } = useSesion();
  const mes = MESES[Number(d.mes.slice(5, 7)) - 1];
  const tipos = Object.entries(d.maltrato_mes.por_tipo).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <h2 className="inicio-subtitulo">Año {d.anio}</h2>
      <div className="indicadores">
        <Indicador valor={d.totales.nuevas} texto="actuaciones nuevas" />
        <Indicador valor={d.totales.reiteraciones} texto="reiteraciones" />
        <Indicador valor={d.totales.activos} texto="casos activos hoy" a="/casos" />
        <Indicador valor={d.totales.cerrados} texto="casos cerrados" a="/casos?estado=cerrado" />
      </div>

      <div className="inicio-columnas">
        <Seccion titulo="Por departamento">
          <table className="tabla tabla-areas">
            <thead>
              <tr>
                <th>Área</th>
                <th>Nuevas</th>
                <th>Reiteraciones</th>
                <th>Activos</th>
                <th>Cerrados</th>
                <th>Sin técnico</th>
              </tr>
            </thead>
            <tbody>
              {d.por_area.map((a) => (
                <tr key={a.area}>
                  <td>{a.area.replace(/^(Departamento|División) /, "")}</td>
                  <td>{a.nuevas}</td>
                  <td>{a.reiteraciones}</td>
                  <td>{a.activos}</td>
                  <td>{a.cerrados}</td>
                  <td>
                    {a.sin_responsable > 0 && a.area_id !== null ? (
                      <Enlace a={`/casos?sin_responsable=1&activos=1&area=${a.area_id}`} className="texto-alerta">
                        {a.sin_responsable}
                      </Enlace>
                    ) : (
                      a.sin_responsable || "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Seccion>

        <Seccion titulo={`Maltrato · ${mes}`}>
          <p className="inicio-numero">
            <strong>{d.maltrato_mes.casos}</strong> {d.maltrato_mes.casos === 1 ? "caso ingresó" : "casos ingresaron"} con indicadores de
            maltrato.
          </p>
          {tipos.length > 0 && (
            <ul className="lista-simple">
              {tipos.map(([k, n]) => (
                <li key={k}>
                  {textoDe(f.indicadores, k)}: <strong>{n}</strong>
                </li>
              ))}
            </ul>
          )}
        </Seccion>
      </div>

      <Seccion titulo="Para seguir">
        <div className="indicadores">
          <Indicador
            valor={d.sin_responsable.cantidad}
            texto="casos activos sin técnico a cargo"
            alerta={d.sin_responsable.cantidad > 0}
            a="/casos?sin_responsable=1&activos=1"
          />
          <Indicador valor={d.sin_actividad} texto={`sin movimiento hace más de ${d.dias_sin_actividad} días`} alerta={d.sin_actividad > 0} />
          <Indicador valor={d.informes_mes} texto={`informes firmados en ${mes}`} />
        </div>
      </Seccion>

      <Seccion titulo="Actividad reciente">
        <CasosCompactos casos={d.recientes} />
      </Seccion>
    </>
  );
}

// ---------------------------------------------------------------- mesa de entrada

function ListaIngresos({ ingresos }: { ingresos: Ingreso[] }) {
  if (ingresos.length === 0) return <Vacio>Ninguno.</Vacio>;
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Ingreso</th>
          <th>Fecha</th>
          <th>Asunto</th>
          <th>Persona</th>
        </tr>
      </thead>
      <tbody>
        {ingresos.map((i) => (
          <tr key={i.id}>
            <td>
              <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace>
            </td>
            <td>{fecha(i.fecha_ingreso)}</td>
            <td>{i.asunto}</td>
            <td>{i.persona ? nombre(i.persona) : <span className="texto-alerta">{i.persona_mencionada ?? "Sin vincular"}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function InicioMesa({ d }: { d: { hoy: number; sin_vincular_cantidad: number; sin_vincular: Ingreso[]; mios: Ingreso[] } }) {
  return (
    <>
      <div className="indicadores">
        <Indicador valor={d.hoy} texto="ingresos registrados hoy" />
        <Indicador valor={d.sin_vincular_cantidad} texto="ingresos sin vincular a un legajo" alerta={d.sin_vincular_cantidad > 0} a="/mesa" />
      </div>
      <Accesos>
        <Enlace a="/mesa" className="boton boton-primario">
          Registrar un ingreso
        </Enlace>
        <Enlace a="/legajos" className="boton">
          Buscar legajo
        </Enlace>
      </Accesos>
      <Seccion titulo="Para vincular">
        <ListaIngresos ingresos={d.sin_vincular} />
      </Seccion>
      <Seccion titulo="Mis últimos ingresos">
        <ListaIngresos ingresos={d.mios} />
      </Seccion>
    </>
  );
}

// ---------------------------------------------------------------- carga de datos

interface Carga {
  sin_registro_cantidad: number;
  sin_registro: Caso[];
  sin_escaneo_cantidad: number;
  sin_escaneo: { id: string; fecha: string; caso: { id: string; numero: string; actuacion: string }; persona: PersonaResumen }[];
  pendientes_impresion: number;
  hoy: { casos: number; evoluciones: number; registros: number };
}

function InicioCarga({ d }: { d: Carga }) {
  return (
    <>
      <div className="indicadores">
        <Indicador valor={d.sin_registro_cantidad} texto="casos sin registro de demanda cargado" alerta={d.sin_registro_cantidad > 0} />
        <Indicador valor={d.sin_escaneo_cantidad} texto="registros sin el escaneo del original" alerta={d.sin_escaneo_cantidad > 0} />
        <Indicador valor={d.pendientes_impresion} texto="carátulas por imprimir" a="/imprimir-caratulas" alerta={d.pendientes_impresion > 0} />
      </div>
      <p className="tenue">
        Hoy cargó {d.hoy.casos} {d.hoy.casos === 1 ? "caso" : "casos"}, {d.hoy.registros} {d.hoy.registros === 1 ? "registro" : "registros"} de
        demanda y {d.hoy.evoluciones} {d.hoy.evoluciones === 1 ? "evolución" : "evoluciones"}.
      </p>
      <Accesos>
        <Enlace a="/legajos" className="boton boton-primario">
          Buscar o crear legajo
        </Enlace>
        <Enlace a="/fichas" className="boton">
          Fichas en papel
        </Enlace>
      </Accesos>
      <Seccion titulo="Falta cargar el registro de demanda">
        {d.sin_registro.length === 0 ? (
          <Vacio>Todos los casos activos tienen su registro.</Vacio>
        ) : (
          <>
            <p className="tenue">Primero los que ya tienen técnico a cargo.</p>
            <TablaCasos casos={d.sin_registro} conPersona />
            {d.sin_registro_cantidad > d.sin_registro.length && (
              <p className="tenue">Se muestran {d.sin_registro.length} de {d.sin_registro_cantidad}.</p>
            )}
          </>
        )}
      </Seccion>
      <Seccion titulo="Falta adjuntar el escaneo del original">
        {d.sin_escaneo.length === 0 ? (
          <Vacio>Todos los registros cargados desde papel tienen su escaneo.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Registro</th>
                <th>Actuación</th>
                <th>Persona</th>
              </tr>
            </thead>
            <tbody>
              {d.sin_escaneo.map((r) => (
                <tr key={r.id}>
                  <td>{fecha(r.fecha)}</td>
                  <td>
                    <Enlace a={`/casos/${r.caso.id}`}>{r.caso.actuacion}</Enlace>
                  </td>
                  <td>{nombre(r.persona)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Seccion>
    </>
  );
}

// ---------------------------------------------------------------- administrativo de área

function InicioAdministrativo({ d }: { d: { area: string | null; casos: Caso[]; expedientes: (Expediente & { persona: PersonaResumen })[]; documentos: Documento[]; pendientes_impresion: number } }) {
  return (
    <>
      {d.area && <p className="inicio-area">{d.area}</p>}
      <div className="indicadores">
        <Indicador valor={d.casos.length} texto="casos activos con movimiento reciente" />
        <Indicador valor={d.pendientes_impresion} texto="carátulas por imprimir" a="/imprimir-caratulas" alerta={d.pendientes_impresion > 0} />
      </div>
      <Seccion titulo="Casos del área">
        {d.casos.length === 0 ? <Vacio>No hay casos activos.</Vacio> : <TablaCasos casos={d.casos} conPersona />}
      </Seccion>
      <Seccion titulo="Expedientes recientes">
        {d.expedientes.length === 0 ? (
          <Vacio>Ninguno.</Vacio>
        ) : (
          <ul className="lista-simple">
            {d.expedientes.map((e) => (
              <li key={e.id}>
                <strong>{e.numero}</strong> ({e.tipo}) · <Enlace a={`/legajos/${e.persona.id}`}>{nombre(e.persona)}</Enlace> · {fecha(e.creado_en)}
              </li>
            ))}
          </ul>
        )}
      </Seccion>
      <Seccion titulo="Documentos que cargué">
        {d.documentos.length === 0 ? (
          <Vacio>Ninguno.</Vacio>
        ) : (
          <ul className="lista-simple">
            {d.documentos.map((x) => (
              <li key={x.id}>
                {x.titulo ?? x.tipo_documental.nombre} · {x.tipo_documental.nombre} · {fecha(x.cargado_en)}
              </li>
            ))}
          </ul>
        )}
      </Seccion>
    </>
  );
}

// ---------------------------------------------------------------- general (roles sin inicio propio)

interface Tablero {
  mis_casos: Caso[];
  sin_actividad: Caso[];
  dias_sin_actividad: number;
  ingresos_pendientes: number | null;
  resumen_estados: Record<string, number>;
}

function InicioGeneral() {
  const { datos, error } = useDatos(() => api.get<Tablero>("/tablero"), []);
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  return (
    <>
      <div className="indicadores">
        <Indicador valor={datos.mis_casos.length} texto="casos activos asignados a usted" />
        <Indicador valor={datos.sin_actividad.length} texto={`sin movimientos hace más de ${datos.dias_sin_actividad} días`} alerta={datos.sin_actividad.length > 0} />
        {datos.ingresos_pendientes !== null && (
          <Indicador valor={datos.ingresos_pendientes} texto="ingresos de Mesa de Entrada sin legajo" a="/mesa" alerta={datos.ingresos_pendientes > 0} />
        )}
      </div>
      <Seccion titulo="Mis casos">
        {datos.mis_casos.length === 0 ? <Vacio>No tiene casos activos asignados.</Vacio> : <TablaCasos casos={datos.mis_casos} conPersona />}
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

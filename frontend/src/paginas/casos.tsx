import { useState, type FormEvent } from "react";
import { api, type Caso, type Demanda, type Documento, type Evolucion, type Expediente, type Ingreso, type PersonaDetalle } from "../api";
import {
  Aviso,
  Campo,
  Cargando,
  ESTADOS,
  Enlace,
  Estado,
  Modal,
  Reservado,
  Seccion,
  Vacio,
  documento,
  fecha,
  fechaHora,
  nombre,
  useDatos,
  useEnvio,
  useSesion,
} from "../comun";
import { FormDocumento, TablaDocumentos } from "./documentos";
import { TablaCasos, TablaExpedientes } from "./legajo";
import { FormCaratula, FormDemanda, FormReiteracion, ResumenCaratula, SeccionEvolucion, textoDe, type ReiteracionDato } from "./formularios";

function parametro(nombre: string): string {
  const q = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(q).get(nombre) ?? "";
}

export function PaginaCasos() {
  const [estado, setEstado] = useState(parametro("estado"));
  const [mios, setMios] = useState(false);
  const [q, setQ] = useState("");
  const [filtroQ, setFiltroQ] = useState("");
  const { datos, error } = useDatos(
    () => api.get<Caso[]>("/casos", { estado, asignados_a_mi: mios || undefined, q: filtroQ, limite: 100 }),
    [estado, mios, filtroQ],
  );

  return (
    <>
      <h1>Casos</h1>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          setFiltroQ(q);
        }}
      >
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="N° de caso o apellido" aria-label="Buscar caso" />
        <select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos los estados</option>
          {Object.entries(ESTADOS).map(([k, t]) => (
            <option key={k} value={k}>
              {t}
            </option>
          ))}
        </select>
        <label className="casilla">
          <input type="checkbox" checked={mios} onChange={(e) => setMios(e.target.checked)} />
          Solo asignados a mí
        </label>
        <button className="boton">Filtrar</button>
      </form>
      <Aviso error={error} />
      {!datos ? <Cargando /> : <TablaCasos casos={datos} conPersona />}
      <p className="tenue">Para abrir un caso nuevo, ingrese al legajo de la persona.</p>
    </>
  );
}

interface CasoDetalle extends Omit<Caso, "persona"> {
  persona: PersonaDetalle;
  reiteraciones: ReiteracionDato[];
  demandas: Demanda[];
  evoluciones: Evolucion[];
  antecedentes_sistema: { tiene: boolean; fecha_ultimo_ingreso: string | null };
  expedientes: Expediente[];
  documentos: Documento[];
  ingresos: Ingreso[];
  permisos: { modificar: boolean; derivar: boolean };
}

type Dialogo = null | "estado" | "asignar" | "documento" | "editar" | "caratula" | "demanda" | "escaneo-caratula" | "reiteracion";

export function PaginaCaso({ id }: { id: string }) {
  const { datos: c, error, recargar } = useDatos(() => api.get<CasoDetalle>(`/casos/${id}`), [id]);
  const { catalogos, formularios } = useSesion();
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [demandaEditada, setDemandaEditada] = useState<Demanda | null>(null);
  const [escaneoDemanda, setEscaneoDemanda] = useState<Demanda | null>(null);
  const finalizar = useEnvio();

  if (error) return <Aviso error={error} />;
  if (!c) return <Cargando />;
  const listo = () => {
    setDialogo(null);
    recargar();
  };
  const restringido = c.contenido_restringido;
  const escaneosCaratula = c.documentos.filter((d) => !d.contenido_restringido && d.tipo_documental.nombre === "Carátula");

  return (
    <>
      <div className="ficha">
        <div>
          <span className="ficha-legajo">
            Caso {c.numero} {c.reservado && <Reservado />}
          </span>
          <h1>{c.persona && <Enlace a={`/legajos/${c.persona.id}`}>{nombre(c.persona)}</Enlace>}</h1>
          <p className="ficha-datos">
            {c.persona && <>{c.persona.numero_legajo} · {documento(c.persona)} · </>}
            <Estado estado={c.estado} /> · {c.area?.nombre ?? "Sin área"} · abierto el {fecha(c.abierto_en)}
          </p>
        </div>
        <div className="fila-botones">
          {c.permisos.modificar && !restringido && (
            <>
              <button className="boton boton-primario" onClick={() => setDialogo("estado")}>
                Cambiar estado
              </button>
              <button className="boton" onClick={() => setDialogo("editar")}>
                Editar
              </button>
            </>
          )}
          {c.permisos.derivar && (
            <button className="boton" onClick={() => setDialogo("asignar")}>
              Asignar / derivar
            </button>
          )}
        </div>
      </div>

      {restringido && (
        <div className="aviso aviso-info">
          Caso reservado: puede ver su existencia y estado, pero no su contenido. Solicite acceso a la Dirección si
          necesita intervenir.
        </div>
      )}

      <Seccion
        titulo="Carátula de legajo"
        acciones={
          <>
            {c.permisos.modificar && !restringido && (
              <button className="boton" onClick={() => setDialogo("caratula")}>
                Editar carátula
              </button>
            )}
            {c.permisos.modificar && !restringido && (
              <button className="boton" onClick={() => setDialogo("escaneo-caratula")}>
                Adjuntar escaneo
              </button>
            )}
            <a className="boton boton-primario" href={`#/imprimir/carpeta/${c.id}`} target="_blank" rel="noreferrer">
              Carátula para carpeta
            </a>
            <a className="boton" href={`#/imprimir/caratula/${c.id}`} target="_blank" rel="noreferrer">
              Formato oficial
            </a>
          </>
        }
      >
        <ResumenCaratula caso={c as unknown as Caso} />
        {escaneosCaratula.length > 0 && (
          <p>
            Original escaneado:{" "}
            {escaneosCaratula.map((d, i) => (
              <a key={d.id} href={`/api/documentos/${d.id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
                {i > 0 && ", "}
                {d.titulo ?? "ver"}
              </a>
            ))}
          </p>
        )}
        <h3>Motivo de ingreso</h3>
        <p className="texto-largo">{restringido ? "Reservado" : c.motivo || "—"}</p>
        <h3>
          Reiteraciones ({c.reiteraciones.length})
          {c.permisos.modificar && !restringido && (
            <button className="boton boton-chico" style={{ marginLeft: "0.8rem" }} onClick={() => setDialogo("reiteracion")}>
              Registrar reiteración
            </button>
          )}
        </h3>
        {c.reiteraciones.length > 0 && (
          <ul className="lista-simple">
            {c.reiteraciones.map((x) => (
              <li key={x.id}>
                {fecha(x.fecha)}
                {x.tipo_ingreso && ` · ${textoDe(formularios.tipos_ingreso, x.tipo_ingreso)}`}
                {x.motivo && ` · ${x.motivo}`}
                {x.usuario && <span className="tenue"> — {x.usuario.nombre_completo}</span>}
              </li>
            ))}
          </ul>
        )}
        {c.antecedentes_sistema.tiene && c.caratula.antecedentes === false && (
          <div className="aviso aviso-advertencia">
            La carátula indica que no tiene antecedentes, pero SULAM registra un ingreso anterior
            {c.antecedentes_sistema.fecha_ultimo_ingreso && ` (${fecha(c.antecedentes_sistema.fecha_ultimo_ingreso)})`}.
          </div>
        )}
      </Seccion>

      <Seccion
        titulo="Registro de demanda"
        acciones={
          c.permisos.modificar &&
          !restringido && (
            <button className="boton boton-primario" onClick={() => setDialogo("demanda")}>
              {c.demandas.length ? "Nuevo registro" : "Cargar registro de demanda"}
            </button>
          )
        }
      >
        {c.demandas.length === 0 ? (
          <Vacio>Todavía no se cargó el registro de demanda. Se completa después de la primera verificación del caso.</Vacio>
        ) : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Solicitante</th>
                <th>Recibió</th>
                <th>Cargó</th>
                <th>Original</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {c.demandas.map((d) =>
                d.contenido_restringido ? (
                  <tr key={d.id} className="fila-restringida">
                    <td>{fecha(d.fecha)}</td>
                    <td colSpan={5}>
                      <Reservado texto="Contenido reservado" />
                    </td>
                  </tr>
                ) : (
                  <tr key={d.id}>
                    <td>{fecha(d.fecha)}</td>
                    <td>
                      {d.solicitante_nombre ?? "—"}
                      {d.solicitante_vinculo && <div className="tenue">{d.solicitante_vinculo}</div>}
                    </td>
                    <td>{d.receptor?.nombre_completo ?? <span className="texto-alerta">Sin indicar</span>}</td>
                    <td>
                      {d.cargado_por?.nombre_completo}
                      <div className="tenue">{fechaHora(d.creado_en)}</div>
                    </td>
                    <td>
                      {d.escaneos.length > 0 ? (
                        d.escaneos.map((id, i) => (
                          <a key={id} href={`/api/documentos/${id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
                            {i > 0 && ", "}Ver escaneo
                          </a>
                        ))
                      ) : d.cargado_desde_papel ? (
                        c.permisos.modificar ? (
                          <button className="boton boton-chico" onClick={() => setEscaneoDemanda(d)}>
                            Adjuntar escaneo
                          </button>
                        ) : (
                          <span className="texto-alerta">Falta escaneo</span>
                        )
                      ) : (
                        <span className="tenue">Cargado en el sistema</span>
                      )}
                    </td>
                    <td className="acciones-fila">
                      <a className="boton boton-chico" href={`#/imprimir/demanda/${d.id}`} target="_blank" rel="noreferrer">
                        Ver / imprimir
                      </a>
                      {c.permisos.modificar && (
                        <button className="boton boton-chico" onClick={() => setDemandaEditada(d)}>
                          Editar
                        </button>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        )}
      </Seccion>

      {!restringido && (
        <SeccionEvolucion casoId={c.id} evoluciones={c.evoluciones} puedeAgregar={c.permisos.modificar} alAgregar={recargar} />
      )}

      <Seccion titulo="Responsables">
        {c.asignaciones && c.asignaciones.length > 0 ? (
          <table className="tabla">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Desde</th>
                <th>Hasta</th>
                <th>Motivo</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {c.asignaciones.map((a) => (
                <tr key={a.id} className={a.hasta ? "fila-inactiva" : ""}>
                  <td>{a.usuario.nombre_completo}</td>
                  <td>{fechaHora(a.desde)}</td>
                  <td>{a.hasta ? fechaHora(a.hasta) : <strong>Vigente</strong>}</td>
                  <td>{a.motivo ?? "—"}</td>
                  <td>
                    {!a.hasta && c.permisos.derivar && (
                      <button
                        className="boton boton-chico"
                        disabled={finalizar.enviando}
                        onClick={async () => {
                          const r = await finalizar.ejecutar(() =>
                            api.post(`/casos/${c.id}/asignaciones/${a.id}/finalizar`, {}),
                          );
                          if (r) recargar();
                        }}
                      >
                        Finalizar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Vacio>El caso no tiene responsables asignados.</Vacio>
        )}
        <Aviso error={finalizar.error} />
      </Seccion>

      <Seccion
        titulo="Documentos del caso"
        acciones={
          !restringido && (
            <button className="boton" onClick={() => setDialogo("documento")}>
              Cargar documento
            </button>
          )
        }
      >
        {restringido ? <Vacio>Contenido reservado.</Vacio> : <TablaDocumentos documentos={c.documentos} alCambiar={recargar} />}
      </Seccion>

      <Seccion titulo="Expedientes del caso">
        <TablaExpedientes expedientes={c.expedientes} />
      </Seccion>

      {c.ingresos.length > 0 && (
        <Seccion titulo="Ingresos asociados">
          <ul className="lista-simple">
            {c.ingresos.map((i) => (
              <li key={i.id}>
                <Enlace a={`/mesa/${i.id}`}>{i.numero}</Enlace> · {fecha(i.fecha_ingreso)} · {i.asunto}
              </li>
            ))}
          </ul>
        </Seccion>
      )}

      <Seccion titulo="Historial de estados">
        <ol className="linea-tiempo">
          {c.historial_estados?.map((h, i) => (
            <li key={i}>
              <time>{fechaHora(h.en)}</time> <strong>{h.usuario?.nombre_completo ?? "Sistema"}</strong> —{" "}
              {h.estado_anterior ? `${ESTADOS[h.estado_anterior]} → ` : ""}
              {ESTADOS[h.estado_nuevo]}
              {h.motivo && <div className="tenue">Motivo: {h.motivo}</div>}
            </li>
          ))}
        </ol>
      </Seccion>

      {dialogo === "reiteracion" && (
        <Modal titulo={`Reiteración · ${c.numero}`} alCerrar={() => setDialogo(null)}>
          <FormReiteracion caso={c as unknown as Caso} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "escaneo-caratula" && (
        <Modal titulo="Escaneo de la carátula firmada" alCerrar={() => setDialogo(null)}>
          <FormDocumento personaId={c.persona.id} casoFijo={c.id} tipoInicial="Carátula" alGuardar={listo} />
        </Modal>
      )}
      {escaneoDemanda && (
        <Modal titulo="Escaneo del registro de demanda firmado" alCerrar={() => setEscaneoDemanda(null)}>
          <FormDocumento
            personaId={c.persona.id}
            casoFijo={c.id}
            registroDemandaId={escaneoDemanda.id}
            tipoInicial="Registro de demanda"
            alGuardar={() => {
              setEscaneoDemanda(null);
              listo();
            }}
          />
        </Modal>
      )}
      {dialogo === "caratula" && (
        <Modal titulo={`Carátula · ${c.numero}`} alCerrar={() => setDialogo(null)} ancho>
          <FormCaratula personaId={c.persona.id} caso={c as unknown as Caso} alGuardar={listo} />
        </Modal>
      )}
      {(dialogo === "demanda" || demandaEditada) && (
        <Modal
          titulo={`Registro de demanda · ${c.numero}`}
          alCerrar={() => {
            setDialogo(null);
            setDemandaEditada(null);
          }}
          ancho
        >
          <FormDemanda
            caso={c as unknown as Caso}
            persona={c.persona}
            demanda={demandaEditada ?? undefined}
            alGuardar={() => {
              setDemandaEditada(null);
              listo();
            }}
          />
        </Modal>
      )}
      {dialogo === "estado" && (
        <Modal titulo="Cambiar estado del caso" alCerrar={() => setDialogo(null)}>
          <FormEstado caso={c} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "asignar" && (
        <Modal titulo="Asignar responsable" alCerrar={() => setDialogo(null)}>
          <FormAsignar caso={c} usuarios={catalogos.usuarios_asignables} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "editar" && (
        <Modal titulo="Editar caso" alCerrar={() => setDialogo(null)}>
          <FormEditarCaso caso={c} alGuardar={listo} />
        </Modal>
      )}
      {dialogo === "documento" && c.persona && (
        <Modal titulo="Cargar documento al caso" alCerrar={() => setDialogo(null)}>
          <FormDocumento personaId={c.persona.id} casoFijo={c.id} expedientes={c.expedientes} alGuardar={listo} />
        </Modal>
      )}
    </>
  );
}

function FormEstado({ caso, alGuardar }: { caso: Caso; alGuardar: () => void }) {
  const opciones = Object.keys(ESTADOS).filter((e) => e !== caso.estado);
  const [estado, setEstado] = useState(opciones[0]);
  const [motivo, setMotivo] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const exigeMotivo = estado === "cerrado" || estado === "pausado" || caso.estado === "cerrado";
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/casos/${caso.id}/estado`, { estado, motivo: motivo || null }));
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <p>
        Estado actual: <Estado estado={caso.estado} />
      </p>
      <Campo etiqueta="Nuevo estado">
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          {opciones.map((o) => (
            <option key={o} value={o}>
              {caso.estado === "cerrado" ? `Reabrir como "${ESTADOS[o]}"` : ESTADOS[o]}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta={exigeMotivo ? "Motivo *" : "Motivo"}>
        <textarea rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} required={exigeMotivo} />
      </Campo>
      <p className="tenue">El historial anterior se conserva siempre.</p>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

function FormAsignar({
  caso,
  usuarios,
  alGuardar,
}: {
  caso: Caso;
  usuarios: { id: string; nombre_completo: string; area: string | null }[];
  alGuardar: () => void;
}) {
  const actuales = new Set(caso.responsables.map((r) => r.id));
  const [usuario, setUsuario] = useState("");
  const [motivo, setMotivo] = useState("");
  const [reemplazar, setReemplazar] = useState(caso.responsables.length > 0);
  const { enviando, error, ejecutar } = useEnvio();
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() =>
      api.post(`/casos/${caso.id}/asignaciones`, { usuario_id: usuario, motivo: motivo || null, reemplazar_actuales: reemplazar }),
    );
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <Campo etiqueta="Usuario *">
        <select value={usuario} onChange={(e) => setUsuario(e.target.value)} required>
          <option value="">Elegir…</option>
          {usuarios
            .filter((u) => !actuales.has(u.id))
            .map((u) => (
              <option key={u.id} value={u.id}>
                {u.nombre_completo}
                {u.area ? ` — ${u.area}` : ""}
              </option>
            ))}
        </select>
      </Campo>
      <Campo etiqueta="Motivo">
        <input value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      </Campo>
      {caso.responsables.length > 0 && (
        <label className="casilla">
          <input type="checkbox" checked={reemplazar} onChange={(e) => setReemplazar(e.target.checked)} />
          Reemplaza a los responsables actuales ({caso.responsables.map((r) => r.nombre_completo).join(", ")})
        </label>
      )}
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Asignar
        </button>
      </div>
    </form>
  );
}

function FormEditarCaso({ caso, alGuardar }: { caso: Caso; alGuardar: () => void }) {
  const { catalogos } = useSesion();
  const [areaId, setAreaId] = useState(String(caso.area?.id ?? ""));
  const [motivo, setMotivo] = useState(caso.motivo ?? "");
  const [reservado, setReservado] = useState(caso.reservado);
  const { enviando, error, ejecutar } = useEnvio();
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() =>
      api.patch(`/casos/${caso.id}`, { area_id: areaId ? Number(areaId) : null, motivo: motivo || null, reservado }),
    );
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <Campo etiqueta="Área">
        <select value={areaId} onChange={(e) => setAreaId(e.target.value)}>
          <option value="">Sin área</option>
          {catalogos.areas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <Campo etiqueta="Descripción">
        <textarea rows={4} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      </Campo>
      <label className="casilla">
        <input type="checkbox" checked={reservado} onChange={(e) => setReservado(e.target.checked)} />
        Caso reservado
      </label>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

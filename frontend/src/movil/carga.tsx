// Alta rápida de legajo, carátula por pasos y reiteración, para el celular.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, api, type Caso, type Coincidencia, type PersonaDetalle, type PersonaResumen } from "../api";
import { Aviso, Cargando, documento, edad, nombre, useEnvio, useSesion } from "../comun";
import { Marcas, TipoIngreso, Unica, Varias, hoy, textoDe, textoLista } from "../paginas/formularios";
import { Accion, Tarjeta, avisar } from "./movil";

/** Cambia de pantalla sin dejar la anterior en el historial (el botón «atrás» no vuelve al formulario). */
function reemplazar(ruta: string) {
  location.replace("#" + ruta);
}

// ---------------------------------------------------------------- nuevo legajo

export function NuevaPersonaMovil({ dni: dniInicial }: { dni: string }) {
  const [dni, setDni] = useState(dniInicial);
  const [sinDni, setSinDni] = useState(false);
  const [motivoSinDni, setMotivoSinDni] = useState("");
  const [apellidos, setApellidos] = useState("");
  const [nombres, setNombres] = useState("");
  const [nacimiento, setNacimiento] = useState("");
  const [telefono, setTelefono] = useState("");
  const [existente, setExistente] = useState<PersonaResumen | null>(null);
  const [parecidos, setParecidos] = useState<Coincidencia[] | null>(null);
  const [motivoConfirmacion, setMotivoConfirmacion] = useState("");
  const { enviando, error, setError, ejecutar } = useEnvio();

  // Al completar el DNI se busca enseguida si ya tiene legajo.
  const numero = dni.replace(/\D/g, "");
  useEffect(() => {
    setExistente(null);
    if (sinDni || numero.length < 7) return;
    const t = setTimeout(() => {
      api
        .get<{ personas: PersonaResumen[] }>("/buscar", { q: numero })
        .then((r) => setExistente(r.personas.find((p) => p.numero_documento === numero) ?? null))
        .catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [numero, sinDni]);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const confirmar = parecidos !== null;
    const r = await ejecutar(async () => {
      try {
        return await api.post<PersonaDetalle>("/personas", {
          apellidos,
          nombres,
          tipo_documento: sinDni ? null : "DNI",
          numero_documento: sinDni ? null : numero,
          sin_documento: sinDni,
          motivo_sin_documento: sinDni ? motivoSinDni || null : null,
          fecha_nacimiento: nacimiento || null,
          telefono: telefono || null,
          confirmar_posible_duplicado: confirmar,
          motivo_confirmacion: confirmar ? motivoConfirmacion : null,
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          const c: Coincidencia[] = err.detalle?.coincidencias ?? [];
          if (err.detalle?.bloqueante) setExistente(c[0]?.persona ?? null);
          else setParecidos(c);
          setError(null);
          setTimeout(() => document.querySelector(".m-alerta")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
          return undefined;
        }
        throw err;
      }
    });
    if (r) {
      avisar(`Legajo creado: N° ${r.numero_legajo}`);
      reemplazar(`/m/legajo/${r.id}/caratula`);
    }
  };

  return (
    <form className="m-formulario" onSubmit={enviar}>
      <h1 className="m-titulo">¿Quién es la persona mayor?</h1>
      {!sinDni && (
        <label className="m-campo">
          <span>DNI</span>
          <input
            inputMode="numeric"
            pattern="[0-9.]*"
            autoComplete="off"
            autoFocus={!dniInicial}
            value={dni}
            onChange={(e) => {
              setDni(e.target.value);
              setParecidos(null);
            }}
            required
            minLength={6}
          />
          <small>Es también el número de legajo.</small>
        </label>
      )}
      <label className="m-casilla">
        <input type="checkbox" checked={sinDni} onChange={(e) => setSinDni(e.target.checked)} />
        <span>No tiene DNI o no lo sabe (se asigna un número provisorio «SD-»)</span>
      </label>
      {sinDni && (
        <label className="m-campo">
          <span>Motivo</span>
          <input value={motivoSinDni} onChange={(e) => setMotivoSinDni(e.target.value)} placeholder="Ej.: en trámite, no lo recuerda" />
        </label>
      )}

      {existente ? (
        <YaExiste persona={existente} />
      ) : (
        <>
          <label className="m-campo">
            <span>Apellidos</span>
            <input value={apellidos} onChange={(e) => setApellidos(e.target.value)} required autoCapitalize="characters" autoComplete="off" />
          </label>
          <label className="m-campo">
            <span>Nombres</span>
            <input value={nombres} onChange={(e) => setNombres(e.target.value)} required autoCapitalize="words" autoComplete="off" />
          </label>
          <div className="m-dos">
            <label className="m-campo">
              <span>Fecha de nacimiento</span>
              <input type="date" min="1900-01-01" max={hoy()} value={nacimiento} onChange={(e) => setNacimiento(e.target.value)} />
            </label>
            <label className="m-campo">
              <span>Teléfono</span>
              <input type="tel" inputMode="tel" autoComplete="off" value={telefono} onChange={(e) => setTelefono(e.target.value)} />
            </label>
          </div>

          {parecidos && (
            <div className="m-alerta">
              <strong>Hay legajos parecidos. ¿Es alguna de estas personas?</strong>
              {parecidos.map((c) => (
                <Tarjeta key={c.persona.id} a={`/m/legajo/${c.persona.id}`}>
                  <strong className="m-nombre">{nombre(c.persona)}</strong>
                  <span className="m-detalle">
                    {documento(c.persona)}
                    {c.persona.fecha_nacimiento && ` · ${edad(c.persona.fecha_nacimiento)} años`} · {c.motivos.join(", ")}
                  </span>
                </Tarjeta>
              ))}
              <label className="m-campo">
                <span>Si es otra persona, explique por qué</span>
                <input value={motivoConfirmacion} onChange={(e) => setMotivoConfirmacion(e.target.value)} required placeholder="Ej.: distinta fecha de nacimiento" />
              </label>
            </div>
          )}
          <Aviso error={error} />
          <div className="m-pie-fijo">
            <button className="m-boton m-boton-primario" disabled={enviando}>
              {enviando ? "Guardando…" : parecidos ? "Es otra persona: crear legajo" : "Crear legajo y seguir con la carátula"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}

function YaExiste({ persona }: { persona: PersonaResumen }) {
  return (
    <div className="m-alerta">
      <strong>Esta persona ya tiene legajo.</strong>
      <Tarjeta a={`/m/legajo/${persona.id}`}>
        <strong className="m-nombre">{nombre(persona)}</strong>
        <span className="m-detalle">
          Legajo N° {persona.numero_legajo}
          {persona.fecha_nacimiento && ` · ${edad(persona.fecha_nacimiento)} años`}
          {persona.localidad && ` · ${persona.localidad}`}
        </span>
      </Tarjeta>
      <Accion a={`/m/legajo/${persona.id}`} icono="→" principal>
        Abrir el legajo
      </Accion>
    </div>
  );
}

// ---------------------------------------------------------------- carátula por pasos

interface Datos {
  fecha_ingreso: string;
  motivo: string;
  tipo_ingreso: string | null;
  tipo_ingreso_detalle: string | null;
  derivado_por: string | null;
  derivado_por_detalle: string | null;
  indicadores: string[];
  intervenciones: string[];
  intervencion_derivacion: string;
  intervencion_otro: string;
  genero: string | null;
  domicilio: string;
  localidad: string;
  departamento: string;
  telefono: string;
  cud: string | null;
  cobertura_salud: string[];
  obra_social: string;
}

const PASOS = ["Ingreso", "Persona", "Domicilio", "Indicadores", "Intervención", "Confirmar"];

function pasoDeRuta(): number {
  const n = Number(new URLSearchParams(location.hash.split("?")[1] ?? "").get("paso") ?? 0);
  return Number.isFinite(n) ? Math.max(0, Math.min(PASOS.length - 1, n)) : 0;
}

export function CaratulaMovil({ personaId }: { personaId: string }) {
  const { yo, catalogos, formularios: f, puede } = useSesion();
  const [persona, setPersona] = useState<(PersonaDetalle & { casos?: Caso[] }) | null>(null);
  const [d, setD] = useState<Datos | null>(null);
  const [areaId, setAreaId] = useState(String(yo.area?.id ?? ""));
  const [responsable, setResponsable] = useState("");
  const [reservado, setReservado] = useState(false);
  const [existente, setExistente] = useState<{ id: string; numero: string } | null>(null);
  const { enviando, error, setError, ejecutar } = useEnvio();
  const paso = pasoDeRuta();

  useEffect(() => {
    api
      .get<PersonaDetalle & { casos?: Caso[] }>(`/personas/${personaId}`)
      .then((p) => {
        setPersona(p);
        const anio = new Date().getFullYear();
        const delAnio = p.casos?.find((x) => x.caratula?.anio_actuacion === anio);
        if (delAnio) setExistente({ id: delAnio.id, numero: `${delAnio.caratula.numero_actuacion}/${anio}` });
        setD({
          fecha_ingreso: hoy(),
          motivo: "",
          tipo_ingreso: null,
          tipo_ingreso_detalle: null,
          derivado_por: null,
          derivado_por_detalle: null,
          indicadores: [],
          intervenciones: [],
          intervencion_derivacion: "",
          intervencion_otro: "",
          genero: p.genero,
          domicilio: p.domicilio ?? "",
          localidad: p.localidad ?? "",
          departamento: p.departamento ?? "",
          telefono: p.telefono ?? "",
          cud: p.cud,
          cobertura_salud: p.cobertura_salud ?? [],
          obra_social: p.obra_social ?? "",
        });
      })
      .catch(setError);
  }, [personaId, setError]);

  if (!persona || !d) return error ? <Aviso error={error} /> : <Cargando />;
  const set = (c: Partial<Datos>) => setD({ ...d, ...c });

  if (existente) {
    return (
      <div className="m-formulario">
        <div className="m-alerta">
          <strong>
            {nombre(persona)} ya tiene la actuación N° {existente.numero}.
          </strong>
          <p>En el mismo año no se arma otra carátula: el nuevo ingreso se registra como reiteración de ese caso.</p>
        </div>
        <Accion a={`/m/caso/${existente.id}/reiteracion`} icono="↻" principal>
          Registrar reiteración
        </Accion>
        <Accion a={`/m/caso/${existente.id}`} icono="→">
          Ver el caso
        </Accion>
      </div>
    );
  }

  const ir = (n: number) => location.assign(`#/m/legajo/${personaId}/caratula?paso=${n}`);

  const crear = async () => {
    const r = await ejecutar(async () => {
      try {
        return await api.post<Caso>("/casos", {
          persona_id: personaId,
          area_id: areaId ? Number(areaId) : null,
          reservado,
          responsable_id: responsable || null,
          fecha_ingreso: d.fecha_ingreso,
          motivo: d.motivo,
          tipo_ingreso: d.tipo_ingreso,
          tipo_ingreso_detalle: d.tipo_ingreso_detalle,
          derivado_por: d.derivado_por,
          derivado_por_detalle: d.derivado_por_detalle,
          indicadores: d.indicadores,
          intervenciones: d.intervenciones,
          intervencion_derivacion: d.intervenciones.includes("derivacion") ? d.intervencion_derivacion : null,
          intervencion_otro: d.intervenciones.includes("otro") ? d.intervencion_otro : null,
          persona: {
            genero: d.genero,
            domicilio: d.domicilio,
            localidad: d.localidad,
            departamento: d.departamento,
            telefono: d.telefono,
            cud: d.cud,
            cobertura_salud: d.cobertura_salud,
            obra_social: d.cobertura_salud.includes("obra_social") ? d.obra_social : persona.obra_social,
          },
        });
      } catch (err) {
        const c = err instanceof ApiError && err.status === 409 ? err.detalle?.caso_existente : null;
        if (c) {
          setExistente({ id: c.id, numero: c.numero ?? "del año" });
          return undefined;
        }
        throw err;
      }
    });
    if (r) {
      avisar(`Caso creado · Actuación N° ${r.caratula.numero_actuacion}/${r.caratula.anio_actuacion} · carátula en la cola de impresión`);
      reemplazar(`/m/caso/${r.id}`);
    }
  };

  const siguiente = (e: FormEvent) => {
    e.preventDefault();
    if (paso < PASOS.length - 1) ir(paso + 1);
    else crear();
  };

  const maltrato = d.indicadores.includes("maltrato");
  let contenido: ReactNode;
  switch (paso) {
    case 0:
      contenido = (
        <>
          <label className="m-campo">
            <span>Fecha de ingreso</span>
            <input type="date" value={d.fecha_ingreso} max={hoy()} onChange={(e) => set({ fecha_ingreso: e.target.value })} required />
          </label>
          <TipoIngreso d={d} set={set} conDerivadoPor={false} />
          <label className="m-campo">
            <span>Motivo de ingreso</span>
            <textarea rows={4} value={d.motivo} onChange={(e) => set({ motivo: e.target.value })} placeholder="Qué refiere la persona o quien consulta" />
          </label>
        </>
      );
      break;
    case 1:
      contenido = (
        <>
          <Unica etiqueta="Género" nombreCampo="genero" opciones={f.generos} valor={d.genero} alCambiar={(v) => set({ genero: v })} />
          <Varias etiqueta="Cobertura de salud" opciones={f.cobertura_salud} valor={d.cobertura_salud} alCambiar={(v) => set({ cobertura_salud: v })} />
          {d.cobertura_salud.includes("obra_social") && (
            <label className="m-campo">
              <span>Obra social</span>
              <input value={d.obra_social} onChange={(e) => set({ obra_social: e.target.value })} />
            </label>
          )}
          <Unica etiqueta="CUD" nombreCampo="cud" opciones={f.cud} valor={d.cud} alCambiar={(v) => set({ cud: v })} />
        </>
      );
      break;
    case 2:
      contenido = (
        <>
          <label className="m-campo">
            <span>Dirección</span>
            <input value={d.domicilio} onChange={(e) => set({ domicilio: e.target.value })} autoComplete="off" />
          </label>
          <label className="m-campo">
            <span>Localidad</span>
            <input value={d.localidad} onChange={(e) => set({ localidad: e.target.value })} autoComplete="off" />
          </label>
          <label className="m-campo">
            <span>Departamento</span>
            <select value={d.departamento} onChange={(e) => set({ departamento: e.target.value })}>
              <option value="">—</option>
              {d.departamento && !f.departamentos.includes(d.departamento) && <option value={d.departamento}>{d.departamento}</option>}
              {f.departamentos.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <label className="m-campo">
            <span>Teléfono</span>
            <input type="tel" inputMode="tel" value={d.telefono} onChange={(e) => set({ telefono: e.target.value })} autoComplete="off" />
          </label>
        </>
      );
      break;
    case 3:
      contenido = (
        <>
          <Marcas etiqueta="Indicadores" opciones={f.indicadores} valor={d.indicadores} alCambiar={(v) => set({ indicadores: v })} />
          {maltrato && <div className="m-alerta">Marcó maltrato: en el último paso considere registrar el caso como reservado.</div>}
        </>
      );
      break;
    case 4:
      contenido = (
        <Marcas
          etiqueta="Tipo de intervención"
          opciones={f.intervenciones}
          valor={d.intervenciones}
          alCambiar={(v) => set({ intervenciones: v })}
          extra={{
            derivacion: <input aria-label="Derivación a" placeholder="Derivación a…" value={d.intervencion_derivacion} onChange={(e) => set({ intervencion_derivacion: e.target.value })} />,
            otro: <input aria-label="Otra intervención" placeholder="Especificar…" value={d.intervencion_otro} onChange={(e) => set({ intervencion_otro: e.target.value })} />,
          }}
        />
      );
      break;
    default:
      contenido = (
        <>
          <dl className="m-resumen">
            <Fila t="Ingreso" ir={() => ir(0)}>
              {d.fecha_ingreso.split("-").reverse().join("/")} · {textoDe(f.tipos_ingreso, d.tipo_ingreso) || "tipo sin indicar"}
              {d.motivo && <div>{d.motivo}</div>}
            </Fila>
            <Fila t="Persona" ir={() => ir(1)}>
              {[textoDe(f.generos, d.genero), textoLista(f.cobertura_salud, d.cobertura_salud), d.cud && "CUD: " + textoDe(f.cud, d.cud)].filter(Boolean).join(" · ") || "—"}
            </Fila>
            <Fila t="Domicilio" ir={() => ir(2)}>
              {[d.domicilio, d.localidad, d.departamento].filter(Boolean).join(", ") || "—"}
              {d.telefono && <div>Tel. {d.telefono}</div>}
            </Fila>
            <Fila t="Indicadores" ir={() => ir(3)}>
              {textoLista(f.indicadores, d.indicadores) || "—"}
            </Fila>
            <Fila t="Intervención" ir={() => ir(4)}>
              {textoLista(f.intervenciones, d.intervenciones) || "—"}
            </Fila>
          </dl>
          <label className="m-campo">
            <span>Área</span>
            <select value={areaId} onChange={(e) => setAreaId(e.target.value)}>
              <option value="">Sin área</option>
              {catalogos.areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.nombre}
                </option>
              ))}
            </select>
          </label>
          {puede("casos", "derivar") && (
            <label className="m-campo">
              <span>Responsable</span>
              <select value={responsable} onChange={(e) => setResponsable(e.target.value)}>
                <option value="">Asignar más tarde</option>
                {catalogos.usuarios_asignables.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nombre_completo}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="m-casilla">
            <input type="checkbox" checked={reservado} onChange={(e) => setReservado(e.target.checked)} />
            <span>Caso reservado (solo lo ven sus responsables y quienes acceden a información reservada)</span>
          </label>
          {maltrato && !reservado && <div className="m-alerta">Se marcó un indicador de maltrato: considere registrar el caso como reservado.</div>}
          <p className="m-tenue">El número de actuación se asigna al crear el caso.</p>
        </>
      );
  }

  return (
    <form className="m-formulario" onSubmit={siguiente}>
      <p className="m-contexto">
        {nombre(persona)} · Legajo {persona.numero_legajo}
      </p>
      <div className="m-pasos" aria-label={`Paso ${paso + 1} de ${PASOS.length}: ${PASOS[paso]}`}>
        {PASOS.map((t, i) => (
          <span key={t} className={i < paso ? "hecho" : i === paso ? "actual" : ""} />
        ))}
      </div>
      <h1 className="m-titulo">
        {paso + 1}. {PASOS[paso]}
      </h1>
      {contenido}
      <Aviso error={error} />
      <div className="m-pie-fijo m-pie-doble">
        {paso > 0 && (
          <button type="button" className="m-boton" onClick={() => history.back()}>
            Atrás
          </button>
        )}
        <button className="m-boton m-boton-primario" disabled={enviando}>
          {paso < PASOS.length - 1 ? "Siguiente" : enviando ? "Creando…" : "Crear caso"}
        </button>
      </div>
    </form>
  );
}

function Fila({ t, ir, children }: { t: string; ir: () => void; children: ReactNode }) {
  return (
    <div className="m-resumen-fila">
      <dt>
        {t}
        <button type="button" className="m-boton-texto" onClick={ir}>
          cambiar
        </button>
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

// ---------------------------------------------------------------- reiteración

export function ReiteracionMovil({ casoId }: { casoId: string }) {
  const [caso, setCaso] = useState<Caso | null>(null);
  const [d, setD] = useState({
    fecha: hoy(),
    motivo: "",
    tipo_ingreso: null as string | null,
    tipo_ingreso_detalle: null as string | null,
    derivado_por: null as string | null,
    derivado_por_detalle: null as string | null,
  });
  const { enviando, error, setError, ejecutar } = useEnvio();
  useEffect(() => {
    api.get<Caso>(`/casos/${casoId}`).then(setCaso).catch(setError);
  }, [casoId, setError]);
  if (!caso) return error ? <Aviso error={error} /> : <Cargando />;
  const set = (c: Partial<typeof d>) => setD({ ...d, ...c });
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/casos/${casoId}/reiteraciones`, { ...d, motivo: d.motivo || null }));
    if (r) {
      avisar(caso.estado === "cerrado" ? "Reiteración registrada · el caso se reabrió" : "Reiteración registrada");
      reemplazar(`/m/caso/${casoId}`);
    }
  };
  return (
    <form className="m-formulario" onSubmit={enviar}>
      <p className="m-contexto">
        {caso.persona && nombre(caso.persona)} · Actuación {caso.caratula.numero_actuacion}/{caso.caratula.anio_actuacion}
      </p>
      <p className="m-tenue">
        Nuevo ingreso de la persona en el año{caso.estado === "cerrado" ? ": el caso se reabre" : ""}.
      </p>
      <label className="m-campo">
        <span>Fecha</span>
        <input type="date" value={d.fecha} max={hoy()} onChange={(e) => set({ fecha: e.target.value })} required />
      </label>
      <TipoIngreso d={d} set={set} conDerivadoPor={false} />
      <label className="m-campo">
        <span>Motivo</span>
        <textarea rows={4} value={d.motivo} onChange={(e) => set({ motivo: e.target.value })} />
      </label>
      <Aviso error={error} />
      <div className="m-pie-fijo">
        <button className="m-boton m-boton-primario" disabled={enviando}>
          {enviando ? "Guardando…" : "Registrar reiteración"}
        </button>
      </div>
    </form>
  );
}

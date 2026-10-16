// Carátula de legajo, registro de demanda y evolución del caso.
// Las opciones vienen del servidor (/api/formularios) con los textos de los modelos institucionales.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, type Caso, type Demanda, type Evolucion, type Opcion, type PersonaDetalle } from "../api";
import { Aviso, Campo, Cargando, Seccion, Vacio, documento, edad, fecha, fechaHora, nombre, useEnvio, useSesion } from "../comun";

// ---------------------------------------------------------------- textos

export function textoDe(opciones: Opcion[], codigo: string | null | undefined): string {
  if (!codigo) return "";
  for (const o of opciones) {
    if (o.codigo === codigo) return o.texto;
    for (const s of o.subopciones ?? []) if (s.codigo === codigo) return s.texto;
  }
  return codigo;
}

/** "Maltrato (Físico, Económico/Patrimonial); Situación de calle" */
export function textoLista(opciones: Opcion[], lista: string[] | null | undefined): string {
  if (!lista || lista.length === 0) return "";
  return opciones
    .filter((o) => lista.includes(o.codigo))
    .map((o) => {
      const subs = (o.subopciones ?? []).filter((s) => lista.includes(s.codigo)).map((s) => s.texto);
      return subs.length ? `${o.texto} (${subs.join(", ")})` : o.texto;
    })
    .join("; ");
}

// ---------------------------------------------------------------- controles

/** Casillas con subopciones: marcar una subopción marca el grupo; desmarcar el grupo borra sus subopciones. */
export function Marcas({
  opciones,
  valor,
  alCambiar,
  etiqueta,
  extra,
}: {
  opciones: Opcion[];
  valor: string[];
  alCambiar: (v: string[]) => void;
  etiqueta: string;
  extra?: Record<string, ReactNode>;
}) {
  const alternar = (codigo: string, marcado: boolean) => {
    const grupo = codigo.split(".")[0];
    let nuevo = valor.filter((v) => v !== codigo);
    if (marcado) {
      nuevo.push(codigo);
      if (grupo !== codigo && !nuevo.includes(grupo)) nuevo.push(grupo);
    } else if (grupo === codigo) {
      nuevo = nuevo.filter((v) => !v.startsWith(grupo + "."));
    }
    alCambiar(nuevo);
  };
  return (
    <fieldset className="opciones">
      <legend>{etiqueta}</legend>
      {opciones.map((o) => (
        <div key={o.codigo} className="opcion-grupo">
          <label className="casilla">
            <input type="checkbox" checked={valor.includes(o.codigo)} onChange={(e) => alternar(o.codigo, e.target.checked)} />
            <span>{o.texto}</span>
          </label>
          {(o.subopciones?.length ?? 0) > 0 && (
            <div className="subopciones">
              {o.subopciones!.map((s) => (
                <label key={s.codigo} className="casilla">
                  <input type="checkbox" checked={valor.includes(s.codigo)} onChange={(e) => alternar(s.codigo, e.target.checked)} />
                  <span>{s.texto}</span>
                </label>
              ))}
            </div>
          )}
          {extra?.[o.codigo] && valor.includes(o.codigo) && <div className="subopciones">{extra[o.codigo]}</div>}
        </div>
      ))}
    </fieldset>
  );
}

/** Una sola opción (botones de radio), con posibilidad de dejar sin dato. */
export function Unica({
  opciones,
  valor,
  alCambiar,
  etiqueta,
  nombreCampo,
}: {
  opciones: Opcion[];
  valor: string | null;
  alCambiar: (v: string | null) => void;
  etiqueta: string;
  nombreCampo: string;
}) {
  return (
    <fieldset className="opciones opciones-linea">
      <legend>{etiqueta}</legend>
      {opciones.map((o) => (
        <label key={o.codigo} className="casilla">
          <input type="radio" name={nombreCampo} checked={valor === o.codigo} onChange={() => alCambiar(o.codigo)} />
          <span>{o.texto}</span>
        </label>
      ))}
      {valor && (
        <button type="button" className="boton-enlace" onClick={() => alCambiar(null)}>
          quitar
        </button>
      )}
    </fieldset>
  );
}

/** Varias opciones simples (sin subopciones). */
export function Varias({
  opciones,
  valor,
  alCambiar,
  etiqueta,
}: {
  opciones: Opcion[];
  valor: string[];
  alCambiar: (v: string[]) => void;
  etiqueta: string;
}) {
  return (
    <fieldset className="opciones opciones-linea">
      <legend>{etiqueta}</legend>
      {opciones.map((o) => (
        <label key={o.codigo} className="casilla">
          <input
            type="checkbox"
            checked={valor.includes(o.codigo)}
            onChange={(e) => alCambiar(e.target.checked ? [...valor, o.codigo] : valor.filter((v) => v !== o.codigo))}
          />
          <span>{o.texto}</span>
        </label>
      ))}
    </fieldset>
  );
}

const SI_NO: Opcion[] = [
  { codigo: "si", texto: "Sí" },
  { codigo: "no", texto: "No" },
];

export function SiNo({
  valor,
  alCambiar,
  etiqueta,
  nombreCampo,
}: {
  valor: boolean | null;
  alCambiar: (v: boolean | null) => void;
  etiqueta: string;
  nombreCampo: string;
}) {
  return (
    <Unica
      opciones={SI_NO}
      valor={valor === null || valor === undefined ? null : valor ? "si" : "no"}
      alCambiar={(v) => alCambiar(v === null ? null : v === "si")}
      etiqueta={etiqueta}
      nombreCampo={nombreCampo}
    />
  );
}

/** Tipo de ingreso con su detalle (Presencial / No presencial / Amparo) y derivación. */
function TipoIngreso({
  d,
  set,
  conDerivadoPor,
}: {
  d: { tipo_ingreso: string | null; tipo_ingreso_detalle: string | null; derivado_por: string | null; derivado_por_detalle: string | null };
  set: (c: Partial<typeof d>) => void;
  conDerivadoPor: boolean;
}) {
  const { formularios: f } = useSesion();
  const tipo = f.tipos_ingreso.find((t) => t.codigo === d.tipo_ingreso);
  const detalles = (tipo?.subopciones ?? []).map((s) => ({ ...s, codigo: s.codigo.split(".")[1] }));
  return (
    <>
      <Unica
        etiqueta="Tipo de ingreso"
        nombreCampo="tipo_ingreso"
        opciones={f.tipos_ingreso}
        valor={d.tipo_ingreso}
        alCambiar={(v) => set({ tipo_ingreso: v, tipo_ingreso_detalle: null })}
      />
      {detalles.length > 0 && (
        <Unica
          etiqueta={tipo!.texto}
          nombreCampo="tipo_ingreso_detalle"
          opciones={detalles}
          valor={d.tipo_ingreso_detalle}
          alCambiar={(v) => set({ tipo_ingreso_detalle: v })}
        />
      )}
      {(conDerivadoPor || d.tipo_ingreso === "derivada") && (
        <div className="grilla">
          <Campo etiqueta="Derivado por">
            <select value={d.derivado_por ?? ""} onChange={(e) => set({ derivado_por: e.target.value || null })}>
              <option value="">—</option>
              {f.derivado_por.map((o) => (
                <option key={o.codigo} value={o.codigo}>
                  {o.texto}
                </option>
              ))}
            </select>
          </Campo>
          <Campo etiqueta="Detalle de la derivación">
            <input value={d.derivado_por_detalle ?? ""} onChange={(e) => set({ derivado_por_detalle: e.target.value })} />
          </Campo>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- carátula

interface DatosCaratula {
  numero_actuacion: string;
  anio_actuacion: string;
  fecha_ingreso: string;
  antecedentes: boolean | null;
  fecha_ultimo_ingreso: string;
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

function hoy(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function FormCaratula({
  personaId,
  caso,
  ingresoId,
  alGuardar,
}: {
  personaId: string;
  caso?: Caso;
  ingresoId?: string;
  alGuardar: (c: Caso) => void;
}) {
  const { yo, catalogos, formularios: f, puede } = useSesion();
  const [persona, setPersona] = useState<PersonaDetalle | null>(null);
  const [d, setD] = useState<DatosCaratula | null>(null);
  const [areaId, setAreaId] = useState(String(yo.area?.id ?? ""));
  const [reservado, setReservado] = useState(false);
  const [responsable, setResponsable] = useState("");
  const { enviando, error, setError, ejecutar } = useEnvio();

  useEffect(() => {
    api
      .get<PersonaDetalle>(`/personas/${personaId}`)
      .then((p) => {
        setPersona(p);
        const c = caso?.caratula;
        setD({
          numero_actuacion: c?.numero_actuacion ? String(c.numero_actuacion) : "",
          anio_actuacion: c?.anio_actuacion ? String(c.anio_actuacion) : "",
          fecha_ingreso: c?.fecha_ingreso ?? hoy(),
          antecedentes: c ? c.antecedentes : null,
          fecha_ultimo_ingreso: c?.fecha_ultimo_ingreso ?? "",
          motivo: caso?.motivo ?? "",
          tipo_ingreso: c?.tipo_ingreso ?? (ingresoId ? "mesa_entrada" : null),
          tipo_ingreso_detalle: c?.tipo_ingreso_detalle ?? null,
          derivado_por: c?.derivado_por ?? null,
          derivado_por_detalle: c?.derivado_por_detalle ?? null,
          indicadores: c?.indicadores ?? [],
          intervenciones: c?.intervenciones ?? [],
          intervencion_derivacion: c?.intervencion_derivacion ?? "",
          intervencion_otro: c?.intervencion_otro ?? "",
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
  }, [personaId, caso, ingresoId, setError]);

  if (!d || !persona) return error ? <Aviso error={error} /> : <Cargando />;
  const set = (c: Partial<DatosCaratula>) => setD({ ...d, ...c });
  const maltrato = d.indicadores.includes("maltrato");

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const caratula: Record<string, unknown> = {
      fecha_ingreso: d.fecha_ingreso || null,
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
    };
    if (!caso && d.numero_actuacion) {
      caratula.numero_actuacion = Number(d.numero_actuacion);
      caratula.anio_actuacion = d.anio_actuacion ? Number(d.anio_actuacion) : Number(d.fecha_ingreso.slice(0, 4));
    }
    if (d.antecedentes !== null) {
      caratula.antecedentes = d.antecedentes;
      caratula.fecha_ultimo_ingreso = d.antecedentes ? d.fecha_ultimo_ingreso || null : null;
    }
    const r = await ejecutar(() =>
      caso
        ? api.patch<Caso>(`/casos/${caso.id}/caratula`, caratula)
        : api.post<Caso>("/casos", {
            ...caratula,
            persona_id: personaId,
            area_id: areaId ? Number(areaId) : null,
            reservado,
            responsable_id: responsable || null,
            ingreso_id: ingresoId ?? null,
          }),
    );
    if (r) alGuardar(r);
  };

  return (
    <form onSubmit={enviar} className="formulario formulario-carga">
      <section>
        <h3>Legajo y actuación</h3>
        <div className="grilla">
          <Campo etiqueta="Legajo N°">
            <input value={persona.numero_legajo} readOnly />
          </Campo>
          {caso ? (
            <Campo etiqueta="Actuación N° / año">
              <input value={`${d.numero_actuacion} / ${d.anio_actuacion}`} readOnly />
            </Campo>
          ) : (
            <>
              <Campo etiqueta="Actuación N°" ayuda="Se asigna sola. Complételo solo al cargar una carátula anterior con su número original.">
                <input type="number" min={1} placeholder="Automático" value={d.numero_actuacion} onChange={(e) => set({ numero_actuacion: e.target.value })} />
              </Campo>
              {d.numero_actuacion && (
                <Campo etiqueta="Año de la actuación">
                  <input type="number" min={1990} max={2100} placeholder={d.fecha_ingreso.slice(0, 4)} value={d.anio_actuacion} onChange={(e) => set({ anio_actuacion: e.target.value })} />
                </Campo>
              )}
            </>
          )}
        </div>
      </section>

      <section>
        <h3>Datos de la persona mayor</h3>
        <p className="tenue">
          {nombre(persona)} · {documento(persona)}
          {persona.fecha_nacimiento && ` · nac. ${fecha(persona.fecha_nacimiento)} (${edad(persona.fecha_nacimiento)} años)`}. Estos
          datos se actualizan también en el legajo.
        </p>
        <Unica etiqueta="Género" nombreCampo="genero" opciones={f.generos} valor={d.genero} alCambiar={(v) => set({ genero: v })} />
        <Varias etiqueta="Cobertura de salud" opciones={f.cobertura_salud} valor={d.cobertura_salud} alCambiar={(v) => set({ cobertura_salud: v })} />
        <div className="grilla">
          {d.cobertura_salud.includes("obra_social") && (
            <Campo etiqueta="Obra social">
              <input value={d.obra_social} onChange={(e) => set({ obra_social: e.target.value })} />
            </Campo>
          )}
        </div>
        <Unica etiqueta="CUD" nombreCampo="cud" opciones={f.cud} valor={d.cud} alCambiar={(v) => set({ cud: v })} />
      </section>

      <section>
        <h3>Domicilio</h3>
        <div className="grilla">
          <Campo etiqueta="Dirección" ancho="completo">
            <input value={d.domicilio} onChange={(e) => set({ domicilio: e.target.value })} />
          </Campo>
          <Campo etiqueta="Localidad">
            <input value={d.localidad} onChange={(e) => set({ localidad: e.target.value })} />
          </Campo>
          <Campo etiqueta="Departamento">
            <input list="departamentos" value={d.departamento} onChange={(e) => set({ departamento: e.target.value })} />
          </Campo>
          <Campo etiqueta="Teléfono">
            <input value={d.telefono} onChange={(e) => set({ telefono: e.target.value })} />
          </Campo>
        </div>
        <datalist id="departamentos">
          {f.departamentos.map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
      </section>

      <section>
        <h3>Información administrativa</h3>
        <div className="grilla">
          <Campo etiqueta="Fecha de ingreso *">
            <input type="date" value={d.fecha_ingreso} onChange={(e) => set({ fecha_ingreso: e.target.value })} required />
          </Campo>
        </div>
        <SiNo
          etiqueta={d.antecedentes === null ? "¿Tiene antecedentes? (si lo deja vacío, se completa con los ingresos registrados en SULAM)" : "¿Tiene antecedentes?"}
          nombreCampo="antecedentes"
          valor={d.antecedentes}
          alCambiar={(v) => set({ antecedentes: v })}
        />
        {d.antecedentes && (
          <div className="grilla">
            <Campo etiqueta="Fecha del último ingreso">
              <input type="date" value={d.fecha_ultimo_ingreso} onChange={(e) => set({ fecha_ultimo_ingreso: e.target.value })} />
            </Campo>
          </div>
        )}
        <Campo etiqueta="Motivo de ingreso">
          <textarea rows={3} value={d.motivo} onChange={(e) => set({ motivo: e.target.value })} />
        </Campo>
        <TipoIngreso d={d} set={set} conDerivadoPor={false} />
        <Marcas etiqueta="Indicadores" opciones={f.indicadores} valor={d.indicadores} alCambiar={(v) => set({ indicadores: v })} />
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
      </section>

      {!caso && (
        <section>
          <h3>Gestión del caso</h3>
          <div className="grilla">
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
            {puede("casos", "derivar") && (
              <Campo etiqueta="Responsable">
                <select value={responsable} onChange={(e) => setResponsable(e.target.value)}>
                  <option value="">Asignar más tarde</option>
                  {catalogos.usuarios_asignables.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.nombre_completo}
                      {u.area ? ` — ${u.area}` : ""}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
          </div>
          <label className="casilla">
            <input type="checkbox" checked={reservado} onChange={(e) => setReservado(e.target.checked)} />
            Caso reservado: su contenido solo lo ven los responsables asignados y quienes tienen acceso a información reservada
          </label>
          {maltrato && !reservado && (
            <div className="aviso aviso-advertencia">Se marcó un indicador de maltrato: considere registrar el caso como reservado.</div>
          )}
        </section>
      )}

      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          {caso ? "Guardar carátula" : "Crear caso con esta carátula"}
        </button>
      </div>
    </form>
  );
}

export function ResumenCaratula({ caso }: { caso: Caso }) {
  const { formularios: f } = useSesion();
  const c = caso.caratula;
  const ingreso = [
    textoDe(f.tipos_ingreso, c.tipo_ingreso),
    c.tipo_ingreso_detalle ? textoDe(f.tipos_ingreso, `${c.tipo_ingreso}.${c.tipo_ingreso_detalle}`) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const intervenciones = [
    textoLista(f.intervenciones, c.intervenciones),
    c.intervencion_derivacion ? `Derivación: ${c.intervencion_derivacion}` : "",
    c.intervencion_otro ? `Otro: ${c.intervencion_otro}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <dl className="datos">
      <dt>Actuación</dt>
      <dd>{c.numero_actuacion ? `N° ${c.numero_actuacion} / ${c.anio_actuacion ?? ""}` : "—"}</dd>
      <dt>Fecha de ingreso</dt>
      <dd>{fecha(c.fecha_ingreso)}</dd>
      <dt>Antecedentes</dt>
      <dd>
        {c.antecedentes === null ? "—" : c.antecedentes ? "Sí" : "No"}
        {c.fecha_ultimo_ingreso && ` · último ingreso ${fecha(c.fecha_ultimo_ingreso)}`}
      </dd>
      <dt>Tipo de ingreso</dt>
      <dd>
        {ingreso || "—"}
        {c.derivado_por && ` · derivado por ${textoDe(f.derivado_por, c.derivado_por)}`}
        {c.derivado_por_detalle && ` (${c.derivado_por_detalle})`}
      </dd>
      <dt>Indicadores</dt>
      <dd>{caso.contenido_restringido ? "Reservado" : textoLista(f.indicadores, c.indicadores) || "—"}</dd>
      <dt>Tipo de intervención</dt>
      <dd>{caso.contenido_restringido ? "Reservado" : intervenciones || "—"}</dd>
    </dl>
  );
}

// ---------------------------------------------------------------- registro de demanda

const CAMPOS_TEXTO = [
  "solicitante_nombre", "solicitante_vinculo", "solicitante_telefono", "solicitud_expresa", "intervencion_otro",
  "obra_social", "domicilio", "barrio", "localidad", "departamento", "vivienda_institucional", "convive_con",
  "referente_nombre", "referente_vinculo", "referente_telefono", "diagnosticos", "derivado_por_detalle",
  "observaciones", "lugar", "telefono",
] as const;

export function FormDemanda({
  caso,
  persona,
  demanda,
  alGuardar,
}: {
  caso: Caso;
  persona: PersonaDetalle;
  demanda?: Demanda;
  alGuardar: (d: Demanda) => void;
}) {
  const { formularios: f, catalogos } = useSesion();
  const [d, setD] = useState<Record<string, any> | null>(null);
  const [actualizarLegajo, setActualizarLegajo] = useState(true);
  const { enviando, error, setError, ejecutar } = useEnvio();

  useEffect(() => {
    if (demanda) {
      setD({ ...demanda, agente_id: demanda.agente?.id ?? null, genero: persona.genero, telefono: persona.telefono });
      return;
    }
    api
      .get<Record<string, any>>(`/casos/${caso.id}/demanda-sugerida`)
      .then((s) => setD({ ...s, telefono: persona.telefono }))
      .catch(setError);
  }, [caso.id, demanda, persona, setError]);

  if (!d) return error ? <Aviso error={error} /> : <Cargando />;
  const set = (c: Record<string, any>) => setD({ ...d, ...c });
  const txt = (k: string) => ({ value: d[k] ?? "", onChange: (e: { target: { value: string } }) => set({ [k]: e.target.value }) });

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo: Record<string, any> = {};
    for (const k of CAMPOS_TEXTO) cuerpo[k] = d[k] ?? null;
    for (const k of ["indicadores", "intervenciones", "cobertura_previsional", "cobertura_salud", "discapacidades"]) cuerpo[k] = d[k] ?? [];
    for (const k of [
      "trabajo_informal", "cud", "tipo_vivienda", "estado_civil", "tiene_hijos", "vinculo_con_hijos", "tiene_autonomia",
      "estado_funcional", "tipo_ingreso", "tipo_ingreso_detalle", "derivado_por", "agente_id", "genero",
    ])
      cuerpo[k] = d[k] ?? null;
    cuerpo.cantidad_hijos = d.tiene_hijos && d.cantidad_hijos !== "" && d.cantidad_hijos !== null ? Number(d.cantidad_hijos) : null;
    cuerpo.fecha = d.fecha || null;
    cuerpo.actualizar_legajo = actualizarLegajo;
    const r = await ejecutar(() =>
      demanda ? api.patch<Demanda>(`/demandas/${demanda.id}`, cuerpo) : api.post<Demanda>(`/casos/${caso.id}/demandas`, cuerpo),
    );
    if (r) alGuardar(r);
  };

  return (
    <form onSubmit={enviar} className="formulario formulario-carga">
      <p className="tenue">
        Precargado con la carátula del caso {caso.numero} y los datos del legajo. Revise y complete.
      </p>

      <section>
        <h3>1. Datos del solicitante</h3>
        <div className="grilla">
          <Campo etiqueta="Solicitante">
            <input {...txt("solicitante_nombre")} />
          </Campo>
          <Campo etiqueta="Vínculo con la persona mayor">
            <input {...txt("solicitante_vinculo")} />
          </Campo>
          <Campo etiqueta="Teléfono">
            <input {...txt("solicitante_telefono")} />
          </Campo>
        </div>
      </section>

      <section>
        <h3>2. Datos de la persona mayor</h3>
        <p>
          <strong>{nombre(persona)}</strong> · {documento(persona)}
          {persona.fecha_nacimiento && ` · nac. ${fecha(persona.fecha_nacimiento)} · ${edad(persona.fecha_nacimiento)} años`}
        </p>
        <Unica etiqueta="Género" nombreCampo="d_genero" opciones={f.generos} valor={d.genero ?? null} alCambiar={(v) => set({ genero: v })} />
        <div className="grilla">
          <Campo etiqueta="Teléfono">
            <input {...txt("telefono")} />
          </Campo>
        </div>
      </section>

      <section>
        <h3>3. Motivo de consulta</h3>
        <Campo etiqueta="Solicitud expresa">
          <textarea rows={3} {...txt("solicitud_expresa")} />
        </Campo>
        <Marcas etiqueta="Indicadores" opciones={f.indicadores} valor={d.indicadores ?? []} alCambiar={(v) => set({ indicadores: v })} />
        <Marcas
          etiqueta="Tipo de intervención solicitada"
          opciones={f.intervenciones.filter((o) => o.codigo !== "derivacion")}
          valor={d.intervenciones ?? []}
          alCambiar={(v) => set({ intervenciones: v })}
          extra={{ otro: <input aria-label="Otra intervención" placeholder="Especificar…" {...txt("intervencion_otro")} /> }}
        />
      </section>

      <section>
        <h3>4. Cobertura social y previsional</h3>
        <Varias etiqueta="Cobertura previsional" opciones={f.cobertura_previsional} valor={d.cobertura_previsional ?? []} alCambiar={(v) => set({ cobertura_previsional: v })} />
        <label className="casilla">
          <input type="checkbox" checked={!!d.trabajo_informal} onChange={(e) => set({ trabajo_informal: e.target.checked })} />
          Trabajo informal
        </label>
        <Varias etiqueta="Cobertura de salud" opciones={f.cobertura_salud} valor={d.cobertura_salud ?? []} alCambiar={(v) => set({ cobertura_salud: v })} />
        {(d.cobertura_salud ?? []).includes("obra_social") && (
          <div className="grilla">
            <Campo etiqueta="Obra social">
              <input {...txt("obra_social")} />
            </Campo>
          </div>
        )}
        <Unica etiqueta="CUD" nombreCampo="d_cud" opciones={f.cud} valor={d.cud ?? null} alCambiar={(v) => set({ cud: v })} />
        <Varias etiqueta="Discapacidad" opciones={f.discapacidad} valor={d.discapacidades ?? []} alCambiar={(v) => set({ discapacidades: v })} />
      </section>

      <section>
        <h3>5. Situación habitacional</h3>
        <div className="grilla">
          <Campo etiqueta="Domicilio" ancho="completo">
            <input {...txt("domicilio")} />
          </Campo>
          <Campo etiqueta="Barrio">
            <input {...txt("barrio")} />
          </Campo>
          <Campo etiqueta="Localidad">
            <input {...txt("localidad")} />
          </Campo>
          <Campo etiqueta="Departamento">
            <input list="departamentos-d" {...txt("departamento")} />
          </Campo>
        </div>
        <datalist id="departamentos-d">
          {f.departamentos.map((x) => (
            <option key={x} value={x} />
          ))}
        </datalist>
        <Unica etiqueta="Tipo de vivienda" nombreCampo="tipo_vivienda" opciones={f.tipo_vivienda} valor={d.tipo_vivienda ?? null} alCambiar={(v) => set({ tipo_vivienda: v })} />
        {d.tipo_vivienda === "institucional" && (
          <Campo etiqueta="Institución">
            <input {...txt("vivienda_institucional")} />
          </Campo>
        )}
      </section>

      <section>
        <h3>6. Situación familiar</h3>
        <Unica etiqueta="Estado civil" nombreCampo="estado_civil" opciones={f.estado_civil} valor={d.estado_civil ?? null} alCambiar={(v) => set({ estado_civil: v })} />
        <SiNo etiqueta="Tiene hijos" nombreCampo="tiene_hijos" valor={d.tiene_hijos ?? null} alCambiar={(v) => set({ tiene_hijos: v })} />
        {d.tiene_hijos && (
          <>
            <div className="grilla">
              <Campo etiqueta="Cantidad">
                <input type="number" min={0} max={50} value={d.cantidad_hijos ?? ""} onChange={(e) => set({ cantidad_hijos: e.target.value })} />
              </Campo>
            </div>
            <SiNo etiqueta="Tiene vínculo con ellos" nombreCampo="vinculo_hijos" valor={d.vinculo_con_hijos ?? null} alCambiar={(v) => set({ vinculo_con_hijos: v })} />
          </>
        )}
        <div className="grilla">
          <Campo etiqueta="Con quién convive">
            <input {...txt("convive_con")} />
          </Campo>
          <Campo etiqueta="Referente">
            <input {...txt("referente_nombre")} />
          </Campo>
          <Campo etiqueta="Vínculo">
            <input {...txt("referente_vinculo")} />
          </Campo>
          <Campo etiqueta="Teléfono del referente">
            <input {...txt("referente_telefono")} />
          </Campo>
        </div>
      </section>

      <section>
        <h3>7. Situación de salud</h3>
        <Campo etiqueta="Diagnósticos relevantes">
          <textarea rows={2} {...txt("diagnosticos")} />
        </Campo>
        <SiNo etiqueta="Tiene autonomía" nombreCampo="autonomia" valor={d.tiene_autonomia ?? null} alCambiar={(v) => set({ tiene_autonomia: v })} />
        <Unica etiqueta="Estado funcional" nombreCampo="estado_funcional" opciones={f.estado_funcional} valor={d.estado_funcional ?? null} alCambiar={(v) => set({ estado_funcional: v })} />
      </section>

      <section>
        <h3>8. Ingreso al sistema</h3>
        <TipoIngreso d={d as any} set={set} conDerivadoPor />
        <div className="grilla">
          <Campo etiqueta="Agente a cargo">
            <select value={d.agente_id ?? ""} onChange={(e) => set({ agente_id: e.target.value || null })}>
              <option value="">—</option>
              {catalogos.usuarios_asignables.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nombre_completo}
                </option>
              ))}
            </select>
          </Campo>
        </div>
      </section>

      <section>
        <h3>Observaciones / datos relevantes</h3>
        <textarea rows={4} aria-label="Observaciones" {...txt("observaciones")} />
        <div className="grilla">
          <Campo etiqueta="Lugar">
            <input {...txt("lugar")} />
          </Campo>
          <Campo etiqueta="Fecha">
            <input type="date" value={d.fecha ?? ""} onChange={(e) => set({ fecha: e.target.value })} />
          </Campo>
        </div>
      </section>

      <label className="casilla">
        <input type="checkbox" checked={actualizarLegajo} onChange={(e) => setActualizarLegajo(e.target.checked)} />
        Actualizar el legajo con estos datos (género, teléfono, domicilio, coberturas, CUD y discapacidad)
      </label>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          {demanda ? "Guardar cambios" : "Guardar registro de demanda"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- evolución

export function SeccionEvolucion({
  casoId,
  evoluciones,
  puedeAgregar,
  alAgregar,
}: {
  casoId: string;
  evoluciones: Evolucion[];
  puedeAgregar: boolean;
  alAgregar: () => void;
}) {
  const [texto, setTexto] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/casos/${casoId}/evolucion`, { texto }));
    if (r) {
      setTexto("");
      alAgregar();
    }
  };
  return (
    <Seccion titulo="Evolución del caso">
      {evoluciones.length === 0 ? (
        <Vacio>Todavía no hay registros de evolución.</Vacio>
      ) : (
        <ol className="linea-tiempo">
          {evoluciones.map((x) => (
            <li key={x.id}>
              <time>{fechaHora(x.en)}</time> <strong>{x.usuario?.nombre_completo}</strong>
              <div className="texto-largo">{x.texto}</div>
            </li>
          ))}
        </ol>
      )}
      {puedeAgregar && (
        <form onSubmit={enviar} className="formulario evolucion-nueva">
          <Campo etiqueta="Nueva entrada">
            <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} required minLength={2} placeholder="Intervención realizada, novedades, próximos pasos…" />
          </Campo>
          <Aviso error={error} />
          <div className="fila-botones">
            <button className="boton" disabled={enviando}>
              Agregar a la evolución
            </button>
          </div>
        </form>
      )}
    </Seccion>
  );
}

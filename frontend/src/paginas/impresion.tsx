// Vistas imprimibles con la estructura de los modelos institucionales.
import { type ReactNode } from "react";
import { api, type Caso, type Demanda, type Evolucion, type Opcion, type PersonaDetalle } from "../api";
import { Aviso, Cargando, fecha, fechaHora, useDatos, useSesion } from "../comun";

interface CasoImpresion extends Omit<Caso, "persona"> {
  persona: PersonaDetalle;
  evoluciones: Evolucion[];
}

export function Impresion({ ruta }: { ruta: string }) {
  const [, , tipo, id] = ruta.split("?")[0].split("/");
  return (
    <div className="impresion">
      <div className="barra-impresion no-imprimir">
        <button className="boton boton-primario" onClick={() => window.print()}>
          Imprimir
        </button>
        <button className="boton" onClick={() => window.close()}>
          Cerrar
        </button>
      </div>
      {tipo === "caratula" ? (
        <ImprimirCaratula casoId={id} />
      ) : tipo === "carpeta" ? (
        <CaratulaCarpeta casoId={id} />
      ) : tipo === "demanda" ? (
        <ImprimirDemanda demandaId={id} />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- piezas

function Casilla({ marcada, children }: { marcada: boolean; children: ReactNode }) {
  return (
    <span className="casilla-imp">
      {marcada ? "☒" : "☐"} {children}
    </span>
  );
}

function Grupo({ opciones, valor, extra }: { opciones: Opcion[]; valor: string[]; extra?: Record<string, string | null | undefined> }) {
  return (
    <span className="grupo-imp">
      {opciones.map((o) => (
        <span key={o.codigo} className="grupo-imp-item">
          <Casilla marcada={valor.includes(o.codigo)}>{o.texto}</Casilla>
          {(o.subopciones?.length ?? 0) > 0 && (
            <>
              {" ("}
              {o.subopciones!.map((s, i) => (
                <span key={s.codigo}>
                  {i > 0 && " | "}
                  <Casilla marcada={valor.includes(s.codigo)}>{s.texto}</Casilla>
                </span>
              ))}
              {")"}
            </>
          )}
          {extra?.[o.codigo] && <span className="dato-imp">: {extra[o.codigo]}</span>}
        </span>
      ))}
    </span>
  );
}

function Plano({ opciones, valor }: { opciones: Opcion[]; valor: string | string[] | null | undefined }) {
  const lista = Array.isArray(valor) ? valor : valor ? [valor] : [];
  return (
    <span className="grupo-imp">
      {opciones.map((o) => (
        <Casilla key={o.codigo} marcada={lista.includes(o.codigo)}>
          {o.texto}
        </Casilla>
      ))}
    </span>
  );
}

function SiNoImp({ valor }: { valor: boolean | null | undefined }) {
  return (
    <span className="grupo-imp">
      <Casilla marcada={valor === true}>Sí</Casilla>
      <Casilla marcada={valor === false}>No</Casilla>
    </span>
  );
}

function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <span className="linea-imp">
      <span className="etiqueta-imp">{etiqueta}:</span> <span className="dato-imp">{children || "………………"}</span>
    </span>
  );
}

function Encabezado({ titulo }: { titulo: string }) {
  return (
    <header className="encabezado-imp">
      <div>Dirección de Adultos Mayores · Provincia de Tucumán</div>
      <h1>{titulo}</h1>
    </header>
  );
}

function TipoIngresoImp({ f, c }: { f: ReturnType<typeof useSesion>["formularios"]; c: Record<string, any> }) {
  return (
    <span className="grupo-imp">
      {f.tipos_ingreso.map((t) => (
        <span key={t.codigo} className="grupo-imp-item">
          <Casilla marcada={c.tipo_ingreso === t.codigo}>{t.texto}</Casilla>
          {(t.subopciones?.length ?? 0) > 0 && (
            <>
              {" ("}
              {t.subopciones!.map((s, i) => (
                <span key={s.codigo}>
                  {i > 0 && " / "}
                  <Casilla marcada={c.tipo_ingreso === t.codigo && `${t.codigo}.${c.tipo_ingreso_detalle}` === s.codigo}>{s.texto}</Casilla>
                </span>
              ))}
              {")"}
            </>
          )}
        </span>
      ))}
    </span>
  );
}

// ---------------------------------------------------------------- carátula

function ImprimirCaratula({ casoId }: { casoId: string }) {
  const { formularios: f } = useSesion();
  const { datos: c, error } = useDatos(() => api.get<CasoImpresion>(`/casos/${casoId}`), [casoId]);
  if (error) return <Aviso error={error} />;
  if (!c) return <Cargando />;
  const p = c.persona;
  const k = c.caratula;
  const edadIngreso = p.fecha_nacimiento ? edadAl(p.fecha_nacimiento, k.fecha_ingreso) : null;
  return (
    <article className="hoja">
      <Encabezado titulo="Carátula de legajo" />
      <p className="fila-imp">
        <Dato etiqueta="LEGAJO N°">{p.numero_legajo}</Dato>
        <Dato etiqueta="ACTUACIÓN N°">
          {k.numero_actuacion ? `${k.numero_actuacion} / AÑO ${k.anio_actuacion ?? ""}` : ""}
        </Dato>
        <Dato etiqueta="Caso SULAM">{c.numero}</Dato>
      </p>

      <h2>Datos de la persona mayor</h2>
      <p className="fila-imp">
        <Dato etiqueta="Apellido y Nombre">{`${p.apellidos.toUpperCase()}, ${p.nombres}`}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta={p.tipo_documento ?? "DNI"}>{p.numero_documento ?? (p.sin_documento ? "Sin documento" : "")}</Dato>
        <Dato etiqueta="Fecha de nacimiento">{p.fecha_nacimiento ? fecha(p.fecha_nacimiento) : ""}</Dato>
        <Dato etiqueta="Edad">{edadIngreso !== null ? String(edadIngreso) : ""}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Obra Social">
          {[f.cobertura_salud.filter((o) => p.cobertura_salud.includes(o.codigo) && o.codigo !== "obra_social").map((o) => o.texto).join(", "), p.obra_social]
            .filter(Boolean)
            .join(" · ")}
        </Dato>
        <span className="linea-imp">
          <span className="etiqueta-imp">CUD:</span> <Plano opciones={f.cud} valor={p.cud} />
        </span>
      </p>
      <p className="fila-imp">
        <span className="linea-imp">
          <span className="etiqueta-imp">Género:</span> <Plano opciones={f.generos} valor={p.genero} />
        </span>
      </p>

      <h2>Domicilio</h2>
      <p className="fila-imp">
        <Dato etiqueta="Dirección">{p.domicilio}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Localidad">{p.localidad}</Dato>
        <Dato etiqueta="Departamento">{p.departamento}</Dato>
        <Dato etiqueta="Teléfono">{p.telefono}</Dato>
      </p>

      <h2>Información administrativa</h2>
      <p className="fila-imp">
        <Dato etiqueta="Fecha de ingreso">{fecha(k.fecha_ingreso)}</Dato>
        <span className="linea-imp">
          <span className="etiqueta-imp">¿Tiene antecedentes?</span> <SiNoImp valor={k.antecedentes} />
        </span>
        <Dato etiqueta="Fecha del último ingreso">{k.fecha_ultimo_ingreso ? fecha(k.fecha_ultimo_ingreso) : ""}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Motivo de ingreso">{c.motivo}</Dato>
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Tipo de ingreso:</span> <TipoIngresoImp f={f} c={k} />
        {(k.derivado_por || k.derivado_por_detalle) && (
          <span className="dato-imp">
            {" "}
            — {f.derivado_por.find((o) => o.codigo === k.derivado_por)?.texto}
            {k.derivado_por_detalle && ` ${k.derivado_por_detalle}`}
          </span>
        )}
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Indicadores:</span> <Grupo opciones={f.indicadores} valor={k.indicadores} />
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Tipo de intervención:</span>{" "}
        <Grupo opciones={f.intervenciones} valor={k.intervenciones} extra={{ derivacion: k.intervencion_derivacion, otro: k.intervencion_otro }} />
      </p>
      <footer className="pie-imp">Generado por SULAM el {fechaHora(new Date().toISOString())}</footer>
    </article>
  );
}

function edadAl(nacimiento: string, referencia: string): number {
  const n = new Date(nacimiento + "T12:00:00");
  const r = new Date(referencia + "T12:00:00");
  let e = r.getFullYear() - n.getFullYear();
  if (r.getMonth() < n.getMonth() || (r.getMonth() === n.getMonth() && r.getDate() < n.getDate())) e--;
  return e;
}

// ---------------------------------------------------------------- registro de demanda

function ImprimirDemanda({ demandaId }: { demandaId: string }) {
  const { formularios: f } = useSesion();
  const { datos, error } = useDatos(async () => {
    const d = await api.get<Demanda>(`/demandas/${demandaId}`);
    const c = await api.get<CasoImpresion>(`/casos/${d.caso_id}`);
    return { d, c };
  }, [demandaId]);
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  const { d, c } = datos;
  const p = d.datos_persona ?? {};
  const edadReg = p.fecha_nacimiento ? edadAl(p.fecha_nacimiento, d.fecha) : null;

  return (
    <article className="hoja">
      <Encabezado titulo="Registro de demanda" />
      <p className="fila-imp">
        <Dato etiqueta="Legajo N°">{p.numero_legajo}</Dato>
        <Dato etiqueta="Caso">{c.numero}</Dato>
      </p>

      <h2>1. Datos del solicitante</h2>
      <p className="fila-imp">
        <Dato etiqueta="Solicitante">{d.solicitante_nombre}</Dato>
        <Dato etiqueta="Vínculo con la persona mayor">{d.solicitante_vinculo}</Dato>
        <Dato etiqueta="Teléfono">{d.solicitante_telefono}</Dato>
      </p>

      <h2>2. Datos de la persona mayor</h2>
      <p className="fila-imp">
        <Dato etiqueta="Apellido y Nombre">{p.apellidos ? `${String(p.apellidos).toUpperCase()}, ${p.nombres}` : ""}</Dato>
        <Dato etiqueta={p.tipo_documento ?? "DNI"}>{p.numero_documento}</Dato>
      </p>
      <p className="fila-imp">
        <span className="linea-imp">
          <span className="etiqueta-imp">Género:</span> <Plano opciones={f.generos} valor={p.genero} />
        </span>
        <Dato etiqueta="Fecha de nacimiento">{p.fecha_nacimiento ? fecha(p.fecha_nacimiento) : ""}</Dato>
        <Dato etiqueta="Edad">{edadReg !== null ? String(edadReg) : ""}</Dato>
        <Dato etiqueta="Teléfono">{p.telefono}</Dato>
      </p>

      <h2>3. Motivo de consulta</h2>
      <p className="fila-imp">
        <Dato etiqueta="Solicitud expresa">{d.solicitud_expresa}</Dato>
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Indicadores:</span> <Grupo opciones={f.indicadores} valor={d.indicadores ?? []} />
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Tipo de intervención solicitada:</span>{" "}
        <Grupo opciones={f.intervenciones.filter((o) => o.codigo !== "derivacion")} valor={d.intervenciones ?? []} extra={{ otro: d.intervencion_otro }} />
      </p>

      <h2>4. Cobertura social y previsional</h2>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Cobertura previsional:</span> <Plano opciones={f.cobertura_previsional} valor={d.cobertura_previsional} />{" "}
        <Casilla marcada={!!d.trabajo_informal}>Trabajo informal</Casilla>
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Cobertura de salud:</span> <Plano opciones={f.cobertura_salud} valor={d.cobertura_salud} />
        {d.obra_social && <span className="dato-imp">: {d.obra_social}</span>}
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">CUD:</span> <Plano opciones={f.cud} valor={d.cud} />
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Discapacidad:</span> <Plano opciones={f.discapacidad} valor={d.discapacidades} />
      </p>

      <h2>5. Situación habitacional</h2>
      <p className="fila-imp">
        <Dato etiqueta="Domicilio">{d.domicilio}</Dato>
        <Dato etiqueta="Barrio">{d.barrio}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Localidad">{d.localidad}</Dato>
        <Dato etiqueta="Departamento">{d.departamento}</Dato>
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Tipo de vivienda:</span> <Plano opciones={f.tipo_vivienda} valor={d.tipo_vivienda} />
        {d.vivienda_institucional && <span className="dato-imp">: {d.vivienda_institucional}</span>}
      </p>

      <h2>6. Situación familiar</h2>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Estado civil:</span> <Plano opciones={f.estado_civil} valor={d.estado_civil} />
      </p>
      <p className="fila-imp">
        <span className="linea-imp">
          <span className="etiqueta-imp">Tiene hijos:</span> <SiNoImp valor={d.tiene_hijos} />
        </span>
        <Dato etiqueta="Cantidad">{d.cantidad_hijos != null ? String(d.cantidad_hijos) : ""}</Dato>
        <span className="linea-imp">
          <span className="etiqueta-imp">Tiene vínculo con ellos:</span> <SiNoImp valor={d.vinculo_con_hijos} />
        </span>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Con quién convive">{d.convive_con}</Dato>
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Referente">{d.referente_nombre}</Dato>
        <Dato etiqueta="Vínculo">{d.referente_vinculo}</Dato>
        <Dato etiqueta="Teléfono">{d.referente_telefono}</Dato>
      </p>

      <h2>7. Situación de salud</h2>
      <p className="fila-imp">
        <Dato etiqueta="Diagnósticos relevantes">{d.diagnosticos}</Dato>
      </p>
      <p className="fila-imp">
        <span className="linea-imp">
          <span className="etiqueta-imp">Tiene autonomía:</span> <SiNoImp valor={d.tiene_autonomia} />
        </span>
        <span className="linea-imp">
          <span className="etiqueta-imp">Estado funcional:</span> <Plano opciones={f.estado_funcional} valor={d.estado_funcional} />
        </span>
      </p>

      <h2>8. Ingreso al sistema</h2>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Tipo de ingreso:</span> <TipoIngresoImp f={f} c={d} />
      </p>
      <p className="bloque-imp">
        <span className="etiqueta-imp">Derivado por:</span> <Plano opciones={f.derivado_por} valor={d.derivado_por} />
        {d.derivado_por_detalle && <span className="dato-imp">: {d.derivado_por_detalle}</span>}
      </p>
      <p className="fila-imp">
        <Dato etiqueta="Agente a cargo">{d.agente?.nombre_completo}</Dato>
      </p>

      <h2>Observaciones / datos relevantes</h2>
      <p className="texto-largo bloque-imp">{d.observaciones || "………………"}</p>
      <p className="fila-imp">
        <Dato etiqueta="Lugar y fecha">{`${d.lugar ?? ""}, ${fecha(d.fecha)}`}</Dato>
      </p>
      <div className="firma-imp">
        <div className="linea-firma" />
        Firma del receptor · {d.receptor?.nombre_completo ?? ""}
      </div>

      <h2>Evolución del caso</h2>
      {c.evoluciones.length === 0 ? (
        <p className="bloque-imp">………………</p>
      ) : (
        <ol className="evolucion-imp">
          {c.evoluciones.map((e) => (
            <li key={e.id}>
              <strong>{fecha(e.fecha)} · {e.autor?.nombre_completo ?? ""}:</strong> <span className="texto-largo">{e.texto}</span>
            </li>
          ))}
        </ol>
      )}
      <footer className="pie-imp">
        {d.cargado_desde_papel ? "Transcripción del original en papel. " : ""}
        Cargado en SULAM por {d.cargado_por?.nombre_completo} el {fechaHora(d.creado_en)} · impreso el {fechaHora(new Date().toISOString())}
      </footer>
    </article>
  );
}


// ---------------------------------------------------------------- carátula de carpeta (lectura rápida)

const GRAVES = ["maltrato", "situacion_calle", "negligencia"];

function Chip({ children, tono }: { children: ReactNode; tono: "grave" | "alerta" | "info" | "neutro" | "reservado" }) {
  const simbolo = tono === "grave" ? "▲ " : tono === "reservado" ? "" : tono === "alerta" ? "● " : "";
  return (
    <span className={`chip-imp chip-${tono}`}>
      {simbolo}
      {children}
    </span>
  );
}

function Tarjeta({ titulo, children, ancho }: { titulo: string; children: ReactNode; ancho?: boolean }) {
  return (
    <section className={`tarjeta-imp ${ancho ? "tarjeta-ancha" : ""}`}>
      <h3>{titulo}</h3>
      {children}
    </section>
  );
}

function Fila({ etiqueta, valor }: { etiqueta: string; valor: ReactNode }) {
  if (valor === null || valor === undefined || valor === "" || valor === false) return null;
  return (
    <div className="fila-dato">
      <span>{etiqueta}</span>
      <strong>{valor}</strong>
    </div>
  );
}

interface CasoCarpeta extends CasoImpresion {
  reiteraciones?: { id: number; fecha: string }[];
}

function CaratulaCarpeta({ casoId }: { casoId: string }) {
  const { formularios: f } = useSesion();
  const { datos: c, error } = useDatos(() => api.get<CasoCarpeta>(`/casos/${casoId}`), [casoId]);
  if (error) return <Aviso error={error} />;
  if (!c) return <Cargando />;
  const p = c.persona;
  const k = c.caratula;
  const restringido = c.contenido_restringido;
  const edadHoy = p.fecha_nacimiento ? edadAl(p.fecha_nacimiento, new Date().toISOString().slice(0, 10)) : null;
  const texto = (lista: Opcion[], cod: string | null | undefined) => {
    for (const o of lista) {
      if (o.codigo === cod) return o.texto;
      for (const s of o.subopciones ?? []) if (s.codigo === cod) return s.texto;
    }
    return cod ?? "";
  };
  const grupos = (lista: Opcion[], valores: string[]) =>
    lista
      .filter((o) => valores.includes(o.codigo))
      .map((o) => ({
        codigo: o.codigo,
        texto: o.texto,
        subs: (o.subopciones ?? []).filter((s) => valores.includes(s.codigo)).map((s) => s.texto),
      }));
  const indicadores = restringido ? [] : grupos(f.indicadores, k.indicadores);
  const intervenciones = restringido ? [] : grupos(f.intervenciones, k.intervenciones);
  const reiteraciones = c.reiteraciones?.length ?? 0;
  const ingreso = [texto(f.tipos_ingreso, k.tipo_ingreso), k.tipo_ingreso_detalle ? texto(f.tipos_ingreso, `${k.tipo_ingreso}.${k.tipo_ingreso_detalle}`) : ""]
    .filter(Boolean)
    .join(" · ");
  const coberturas = [
    ...f.cobertura_salud.filter((o) => p.cobertura_salud.includes(o.codigo) && o.codigo !== "obra_social").map((o) => o.texto),
    p.obra_social,
  ].filter(Boolean);

  return (
    <article className="hoja hoja-carpeta">
      <header className="banda-carpeta">
        <div>
          <div className="banda-org">Dirección de Adultos Mayores · Tucumán</div>
          <div className="banda-titulo">Carátula de legajo</div>
        </div>
        <div className="banda-actuacion">
          <span>Actuación</span>
          <strong>
            {k.numero_actuacion ?? "—"}/{k.anio_actuacion ?? ""}
          </strong>
        </div>
        <img className="banda-qr" src={`/api/casos/${c.id}/qr.svg`} alt="QR del caso" />
      </header>

      <div className="persona-carpeta">
        <div className="persona-nombre">
          {p.apellidos.toUpperCase()}, {p.nombres}
        </div>
        <div className="persona-ids">
          <span className="legajo-grande">
            Legajo <strong>{/^\d+$/.test(p.numero_legajo) ? Number(p.numero_legajo).toLocaleString("es-AR") : p.numero_legajo}</strong>
          </span>
          {edadHoy !== null && (
            <span>
              {edadHoy} años <small>(nac. {fecha(p.fecha_nacimiento)})</small>
            </span>
          )}
          {p.genero && <span>{texto(f.generos, p.genero)}</span>}
          {p.telefono && <span>Tel. {p.telefono}</span>}
        </div>
      </div>

      <div className="chips-carpeta">
        {c.reservado && <Chip tono="reservado">RESERVADO</Chip>}
        {indicadores.map((g) => (
          <Chip key={g.codigo} tono={GRAVES.includes(g.codigo) ? "grave" : g.codigo === "no_califica" ? "neutro" : "alerta"}>
            {g.texto}
            {g.subs.length > 0 && `: ${g.subs.join(", ")}`}
          </Chip>
        ))}
        {k.antecedentes && (
          <Chip tono="info">Con antecedentes{k.fecha_ultimo_ingreso ? ` · último ingreso ${fecha(k.fecha_ultimo_ingreso)}` : ""}</Chip>
        )}
        {reiteraciones > 0 && <Chip tono="info">Reiteraciones: {reiteraciones}</Chip>}
        {p.cud === "si" && <Chip tono="neutro">Con CUD</Chip>}
      </div>

      {restringido ? (
        <p className="aviso-imp">Contenido reservado: solo puede imprimirlo quien tiene acceso al caso.</p>
      ) : (
        <>
          {c.motivo && (
            <Tarjeta titulo="Motivo de ingreso" ancho>
              <p className="motivo-carpeta">{c.motivo}</p>
            </Tarjeta>
          )}
          <div className="grilla-carpeta">
            <Tarjeta titulo="Ingreso">
              <Fila etiqueta="Fecha" valor={fecha(k.fecha_ingreso)} />
              <Fila etiqueta="Tipo" valor={ingreso} />
              <Fila
                etiqueta="Derivado por"
                valor={[texto(f.derivado_por, k.derivado_por), k.derivado_por_detalle].filter(Boolean).join(" · ")}
              />
              <Fila etiqueta="Área" valor={c.area?.nombre} />
            </Tarjeta>
            <Tarjeta titulo="Intervención">
              {intervenciones.length === 0 ? (
                <p className="tenue-imp">Sin definir</p>
              ) : (
                <ul className="lista-carpeta">
                  {intervenciones.map((g) => (
                    <li key={g.codigo}>
                      <strong>{g.texto}</strong>
                      {g.subs.length > 0 && ` (${g.subs.join(", ")})`}
                      {g.codigo === "derivacion" && k.intervencion_derivacion && `: ${k.intervencion_derivacion}`}
                      {g.codigo === "otro" && k.intervencion_otro && `: ${k.intervencion_otro}`}
                    </li>
                  ))}
                </ul>
              )}
            </Tarjeta>
            <Tarjeta titulo="Domicilio">
              <Fila etiqueta="Dirección" valor={p.domicilio} />
              <Fila etiqueta="Barrio" valor={p.barrio} />
              <Fila etiqueta="Localidad" valor={p.localidad} />
              <Fila etiqueta="Departamento" valor={p.departamento} />
            </Tarjeta>
            <Tarjeta titulo="Cobertura">
              <Fila etiqueta="Salud" valor={coberturas.join(", ")} />
              <Fila etiqueta="CUD" valor={p.cud ? texto(f.cud, p.cud) : ""} />
              {!coberturas.length && !p.cud && <p className="tenue-imp">Sin datos</p>}
            </Tarjeta>
            <Tarjeta titulo="Responsables" ancho>
              <p className="responsables-carpeta">
                {c.responsables.length ? c.responsables.map((r) => r.nombre_completo).join(" · ") : "Sin asignar"}
              </p>
            </Tarjeta>
          </div>
        </>
      )}
      <footer className="pie-imp">
        Caso {c.numero} · abierto el {fecha(c.abierto_en)} · impreso el {fechaHora(new Date().toISOString())} · Escanee el QR para abrir el caso en SULAM
      </footer>
    </article>
  );
}

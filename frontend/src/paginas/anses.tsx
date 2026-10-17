// Certificación negativa de ANSES: CUIL listo para pegar, acceso a ANSES,
// lectura automática del PDF descargado (a revisar) y registro con vencimiento.
import { useRef, useState } from "react";
import { ApiError, api, subirConProgreso, type UsuarioBreve } from "../api";
import { Aviso, Cargando, Modal, Seccion, fecha, useDatos } from "../comun";

export interface Negativa {
  id: number;
  cuil: string | null;
  fecha_emision: string;
  vence: string | null;
  estado: "vigente" | "por_vencer" | "vencida" | "no_emitida";
  resultado: "sin_registros" | "con_registros" | "no_emitida";
  resultado_texto: string;
  detalle: string | null;
  codigo_validacion: string | null;
  documento_id: string | null;
  origen: string;
  observaciones: string | null;
  usuario: UsuarioBreve | null;
  en: string;
}

interface InfoNegativa {
  cuil: string | null;
  cuil_sugeridos: string[];
  genero_conocido: boolean;
  url_anses: string;
  dias_vigencia: number;
  ultima: Negativa | null;
  historial: Negativa[];
  puede_registrar: boolean;
}

interface Lectura {
  cuil: string | null;
  cuil_coincide: boolean | null;
  fecha_emision: string | null;
  codigo_validacion: string | null;
  resultado: Negativa["resultado"] | null;
  seguridad: string;
  detalle: string | null;
  es_negativa_anses: boolean;
  avisos: string[];
}

const RESULTADOS: Record<string, string> = {
  sin_registros: "No registra (negativa limpia)",
  con_registros: "Registra prestaciones, aportes u obra social",
  no_emitida: "ANSES no emitió la negativa",
};

export function useNegativa(personaId: string) {
  return useDatos(() => api.get<InfoNegativa>(`/personas/${personaId}/negativa-anses`), [personaId]);
}

/** Etiqueta corta del estado, para el caso y el legajo. */
export function ChipNegativa({ n }: { n: Negativa | null | undefined }) {
  if (!n) return <span className="chip-negativa chip-neg-sin">Negativa ANSES: sin registrar</span>;
  if (n.estado === "no_emitida") return <span className="chip-negativa chip-neg-registra">ANSES no emitió la negativa ({fecha(n.fecha_emision)})</span>;
  const res = n.resultado === "sin_registros" ? "no registra" : "registra";
  if (n.estado === "vencida") return <span className="chip-negativa chip-neg-vencida">Negativa ANSES vencida el {fecha(n.vence)} ({res})</span>;
  return (
    <span className={`chip-negativa ${n.resultado === "sin_registros" ? "chip-neg-ok" : "chip-neg-registra"}`}>
      Negativa ANSES: {res} · vence {fecha(n.vence)}
      {n.estado === "por_vencer" ? " (pronto)" : ""}
    </span>
  );
}

async function copiar(texto: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(texto.replace(/\D/g, ""));
    return true;
  } catch {
    return false;
  }
}

/** Bloque completo: en el legajo (computadora) y en la pantalla del celular. */
export function PanelNegativa({ personaId, casoId, movil }: { personaId: string; casoId?: string; movil?: boolean }) {
  const info = useNegativa(personaId);
  const [registrar, setRegistrar] = useState(false);
  const [copiado, setCopiado] = useState<string | null>(null);
  if (info.error) return <Aviso error={info.error} />;
  if (!info.datos) return <Cargando />;
  const d = info.datos;
  const cuiles = d.cuil ? [d.cuil] : d.cuil_sugeridos;
  const abrirAnses = async (cuil?: string) => {
    if (cuil && (await copiar(cuil))) setCopiado(cuil);
    window.open(d.url_anses, "_blank", "noopener");
  };
  const formulario = (
    <FormNegativa
      personaId={personaId}
      casoId={casoId}
      info={d}
      alGuardar={() => {
        setRegistrar(false);
        info.recargar();
      }}
    />
  );
  return (
    <div className={`panel-negativa ${movil ? "panel-negativa-movil" : ""}`}>
      <div className="negativa-estado">
        <ChipNegativa n={d.ultima} />
        {d.ultima?.documento_id && (
          <a href={`/api/documentos/${d.ultima.documento_id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
            Ver PDF
          </a>
        )}
      </div>
      {d.ultima?.resultado === "con_registros" && d.ultima.detalle && <p className="negativa-detalle">{d.ultima.detalle}</p>}

      {d.puede_registrar && (
        <ol className="negativa-pasos">
          <li>
            <strong>CUIL</strong>{" "}
            {cuiles.length === 0 ? (
              <span className="tenue">El legajo no tiene DNI: busque el CUIL en la documentación de la persona.</span>
            ) : (
              <>
                {cuiles.map((c) => (
                  <button key={c} type="button" className="boton boton-chico cuil" onClick={async () => (await copiar(c)) && setCopiado(c)} title="Copiar">
                    {c} {copiado === c ? "✓ copiado" : "⧉"}
                  </button>
                ))}
                {!d.cuil && (
                  <span className="tenue">
                    {" "}
                    {d.genero_conocido ? "Calculado del DNI: verifíquelo." : "Calculado del DNI; el legajo no tiene género, pruebe ambos."}
                  </span>
                )}
              </>
            )}
          </li>
          <li>
            <button type="button" className="boton" onClick={() => abrirAnses(cuiles.length === 1 ? cuiles[0] : undefined)}>
              Abrir ANSES ↗
            </button>{" "}
            <span className="tenue">Pegue el CUIL, elija el período y descargue el PDF. SULAM no envía datos a ANSES: lo hace usted desde su navegador.</span>
          </li>
          <li>
            <button type="button" className="boton boton-primario" onClick={() => setRegistrar(true)}>
              Subir el PDF de la negativa
            </button>{" "}
            <span className="tenue">SULAM lo lee, usted revisa y queda en el legajo con vencimiento a {d.dias_vigencia} días.</span>
          </li>
        </ol>
      )}

      {d.historial.length > 1 && (
        <details className="negativa-historial">
          <summary>Negativas anteriores ({d.historial.length - 1})</summary>
          <ul>
            {d.historial.slice(1).map((n) => (
              <li key={n.id}>
                {fecha(n.fecha_emision)} · {RESULTADOS[n.resultado]}
                {n.documento_id && (
                  <>
                    {" · "}
                    <a href={`/api/documentos/${n.documento_id}/archivo?en_linea=true`} target="_blank" rel="noreferrer">
                      PDF
                    </a>
                  </>
                )}
                {n.usuario && <span className="tenue"> — {n.usuario.nombre_completo}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {registrar &&
        (movil ? (
          <div className="m-hoja-modal">{formulario}</div>
        ) : (
          <Modal titulo="Registrar negativa de ANSES" alCerrar={() => setRegistrar(false)}>
            {formulario}
          </Modal>
        ))}
    </div>
  );
}

export function SeccionNegativa({ personaId, casoId }: { personaId: string; casoId?: string }) {
  return (
    <Seccion titulo="Certificación negativa de ANSES">
      <PanelNegativa personaId={personaId} casoId={casoId} />
    </Seccion>
  );
}

function hoyIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function FormNegativa({ personaId, casoId, info, alGuardar }: { personaId: string; casoId?: string; info: InfoNegativa; alGuardar: () => void }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [lectura, setLectura] = useState<Lectura | null>(null);
  const [leyendo, setLeyendo] = useState(false);
  const [resultado, setResultado] = useState<string>("");
  const [emision, setEmision] = useState(hoyIso());
  const [cuil, setCuil] = useState(info.cuil ?? (info.cuil_sugeridos.length === 1 ? info.cuil_sugeridos[0] : ""));
  const [codigo, setCodigo] = useState("");
  const [detalle, setDetalle] = useState("");
  const [obs, setObs] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [avance, setAvance] = useState<number | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  const elegir = async (f: File | null) => {
    setArchivo(f);
    setLectura(null);
    setError(null);
    if (!f) return;
    setLeyendo(true);
    try {
      const fd = new FormData();
      fd.append("archivo", f);
      const l = await subirConProgreso<Lectura>(`/personas/${personaId}/negativa-anses/leer`, fd, () => {});
      setLectura(l);
      if (l.resultado) setResultado(l.resultado);
      if (l.fecha_emision) setEmision(l.fecha_emision);
      if (l.cuil) setCuil(l.cuil);
      if (l.codigo_validacion) setCodigo(l.codigo_validacion);
      if (l.detalle) setDetalle(l.detalle);
    } catch (e) {
      setError(e);
    } finally {
      setLeyendo(false);
    }
  };

  const guardar = async () => {
    setError(null);
    if (!resultado) return setError("Elija el resultado.");
    if (resultado !== "no_emitida" && !archivo) return setError("Adjunte el PDF descargado de ANSES.");
    const fd = new FormData();
    fd.append("resultado", resultado);
    fd.append("fecha_emision", emision);
    if (cuil) fd.append("cuil", cuil);
    if (codigo) fd.append("codigo_validacion", codigo);
    if (detalle && resultado === "con_registros") fd.append("detalle", detalle);
    if (obs) fd.append("observaciones", obs);
    if (casoId) fd.append("caso_id", casoId);
    if (archivo && resultado !== "no_emitida") {
      fd.append("archivo", archivo);
      fd.append("leido_del_pdf", lectura ? "true" : "false");
    }
    setAvance(0);
    try {
      await subirConProgreso(`/personas/${personaId}/negativa-anses`, fd, setAvance);
      alGuardar();
    } catch (e) {
      setError(e instanceof ApiError ? e : new Error("No se pudo guardar."));
      setAvance(null);
    }
  };

  const cuilAjeno = lectura && lectura.cuil && lectura.cuil_coincide === false;
  return (
    <div className="formulario form-negativa">
      <div className="campo">
        <span className="campo-etiqueta">PDF descargado de ANSES</span>
        <input ref={entrada} type="file" accept="application/pdf" onChange={(e) => elegir(e.target.files?.[0] ?? null)} />
        {leyendo && <span className="campo-ayuda">Leyendo el PDF…</span>}
      </div>
      {lectura && (
        <div className={`aviso ${lectura.avisos.length ? "aviso-advertencia" : "aviso-exito"}`}>
          {lectura.avisos.length === 0 ? (
            <p>Leído del PDF. Revise los datos antes de guardar.</p>
          ) : (
            lectura.avisos.map((a) => <p key={a}>{a}</p>)
          )}
        </div>
      )}
      <fieldset className="opciones-resultado">
        <legend className="campo-etiqueta">Resultado *</legend>
        {Object.entries(RESULTADOS).map(([k, v]) => (
          <label key={k} className={`casilla ${resultado === k ? "elegido" : ""}`}>
            <input type="radio" name="resultado" value={k} checked={resultado === k} onChange={() => setResultado(k)} />
            {v}
            {lectura?.resultado === k && <small className="tenue"> (según el PDF)</small>}
          </label>
        ))}
      </fieldset>
      {resultado === "no_emitida" && (
        <p className="tenue">Cuando ANSES no la emite, suele ser porque la persona registra algo (aportes, prestación u obra social). Se registra sin PDF.</p>
      )}
      <div className="grilla">
        <label className="campo">
          <span className="campo-etiqueta">{resultado === "no_emitida" ? "Fecha de la consulta" : "Fecha de emisión"} *</span>
          <input type="date" value={emision} max={hoyIso()} onChange={(e) => setEmision(e.target.value)} />
        </label>
        <label className="campo">
          <span className="campo-etiqueta">CUIL</span>
          <input value={cuil} onChange={(e) => setCuil(e.target.value)} inputMode="numeric" />
        </label>
        {resultado !== "no_emitida" && (
          <label className="campo">
            <span className="campo-etiqueta">Código de validación</span>
            <input value={codigo} onChange={(e) => setCodigo(e.target.value)} />
          </label>
        )}
      </div>
      {resultado === "con_registros" && (
        <label className="campo">
          <span className="campo-etiqueta">Qué registra</span>
          <textarea rows={3} value={detalle} onChange={(e) => setDetalle(e.target.value)} placeholder="Ej.: Pensión no contributiva, PAMI" />
        </label>
      )}
      <label className="campo">
        <span className="campo-etiqueta">Observaciones</span>
        <input value={obs} onChange={(e) => setObs(e.target.value)} />
      </label>
      <Aviso error={error} />
      {cuilAjeno && <Aviso error="El CUIL del PDF no corresponde a esta persona: no se puede guardar en este legajo." />}
      <div className="fila-botones">
        <button
          type="button"
          className="boton boton-primario"
          onClick={guardar}
          disabled={avance !== null || leyendo || !!cuilAjeno || !resultado || (resultado !== "no_emitida" && !archivo)}
        >
          {avance !== null ? "Guardando…" : "Guardar en el legajo"}
        </button>
      </div>
    </div>
  );
}

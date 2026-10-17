// Carpetas en papel: dónde están y pases (pedir, entregar, pasar, recibir).
// Muy simple: un botón para pedir y uno para confirmar la entrega o la recepción.
import { useEffect, useState } from "react";
import { api, type UsuarioBreve } from "../api";
import { EtiquetaHoy, useHoy } from "./miasistencia";
import { Aviso, Cargando, Seccion, Vacio, fechaHora, useDatos, useEnvio, useSesion } from "../comun";

interface Ubicacion {
  area: { id: number; nombre: string };
  usuario: UsuarioBreve | null;
  desde: string;
}

export interface Pase {
  id: number;
  tipo: "pedido" | "envio";
  objeto: { tipo: string; persona_id: string; expediente_id?: string; texto: string };
  desde: { area: string | null; usuario: UsuarioBreve | null };
  hacia: { area: string; usuario: UsuarioBreve | null };
  motivo: string | null;
  estado: "pendiente" | "hecho" | "rechazado" | "cancelado";
  iniciado_por: UsuarioBreve | null;
  iniciado_en: string;
  resuelto_por: UsuarioBreve | null;
  resuelto_en: string | null;
  respuesta: string | null;
  puedo_confirmar: boolean;
  puedo_cancelar: boolean;
}

interface Estado {
  ubicacion: Ubicacion | null;
  pendiente: Pase | null;
  historial: Pase[];
  puedo: { registrar: boolean; pedir: boolean; pasar: boolean };
  la_tengo: boolean;
}

interface Bandeja {
  entregar: Pase[];
  recibir: Pase[];
  mis_pedidos: Pase[];
  recientes: Pase[];
  en_mi_poder: { tipo: string; persona_id: string; expediente_id?: string; texto: string; desde: string }[];
  area_registro: number | null;
}

const corta = (a: string | null | undefined) => (a ?? "").replace(/^(Departamento|División)\s+/, "");

export function avisarPases() {
  window.dispatchEvent(new Event("sulam:pases"));
}

export function usePasesPendientes() {
  const r = useDatos(() => api.get<{ entregar: number; recibir: number; cantidad: number }>("/archivo/pendientes"), []);
  useEffect(() => {
    const f = () => r.recargar();
    window.addEventListener("sulam:pases", f);
    return () => window.removeEventListener("sulam:pases", f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return r;
}

function dondeEsta(u: Ubicacion) {
  return u.usuario ? `La tiene ${u.usuario.nombre_completo} (${corta(u.area.nombre)})` : `En ${u.area.nombre}`;
}

function textoPase(p: Pase) {
  const hacia = p.hacia.usuario ? p.hacia.usuario.nombre_completo : p.hacia.area;
  if (p.tipo === "pedido") return `${p.iniciado_por?.nombre_completo ?? "Alguien"} la pidió`;
  return `Enviada a ${hacia}`;
}

// ---------------------------------------------------------------- en el legajo, el caso o el expediente

export function CarpetaFisica({
  personaId,
  expedienteId,
  compacto,
  movil,
}: {
  personaId?: string;
  expedienteId?: string;
  compacto?: boolean;
  movil?: boolean;
}) {
  const { catalogos, yo } = useSesion();
  const params = personaId ? { persona_id: personaId } : { expediente_id: expedienteId };
  const { datos: d, error, recargar } = useDatos(() => api.get<Estado>("/archivo/ubicacion", params), [personaId, expedienteId]);
  const envio = useEnvio();
  const [modo, setModo] = useState<null | "pedir" | "pasar" | "registrar">(null);
  const [motivo, setMotivo] = useState("");
  const [area, setArea] = useState("");
  const [persona, setPersona] = useState("");
  const [historial, setHistorial] = useState(false);
  const hoy = useHoy().datos;
  if (error) return <Aviso error={error} />;
  if (!d) return <Cargando />;
  const registro = catalogos.areas.find((a) => a.nombre === "Oficina de Registro");
  const hecho = () => {
    setModo(null);
    setMotivo("");
    setArea("");
    setPersona("");
    recargar();
    avisarPases();
  };
  const accion = (f: () => Promise<unknown>) => envio.ejecutar(f).then((r) => r !== undefined && hecho());
  const usuariosDelArea = catalogos.usuarios_asignables.filter((u) => {
    const a = catalogos.areas.find((x) => String(x.id) === area);
    return a && u.area === a.nombre;
  });

  return (
    <div className={`carpeta ${compacto ? "carpeta-compacta" : ""} ${movil ? "carpeta-movil" : ""}`}>
      <div className="carpeta-estado">
        <span className="carpeta-icono" aria-hidden>
          🗂
        </span>
        <div>
          <strong>{d.ubicacion ? (d.la_tengo && d.ubicacion.usuario ? "La carpeta la tiene usted" : dondeEsta(d.ubicacion)) : "No se registró dónde está la carpeta en papel"}</strong>
          {d.ubicacion?.usuario && !d.la_tengo && <EtiquetaHoy hoy={hoy} usuarioId={d.ubicacion.usuario.id} />}
          {d.ubicacion && <span className="tenue"> · desde {fechaHora(d.ubicacion.desde)}</span>}
          {d.pendiente && (
            <div className="carpeta-pendiente">
              ⏳ {textoPase(d.pendiente)} el {fechaHora(d.pendiente.iniciado_en)}
              {d.pendiente.motivo && ` («${d.pendiente.motivo}»)`} — falta que{" "}
              {d.pendiente.tipo === "pedido" ? "quien la tiene confirme la entrega" : "quien la recibe confirme"}.
            </div>
          )}
        </div>
      </div>

      <div className="carpeta-acciones">
        {d.pendiente?.puedo_confirmar && (
          <button className="boton boton-primario" disabled={envio.enviando} onClick={() => accion(() => api.post(`/archivo/pases/${d.pendiente!.id}/confirmar`))}>
            {d.pendiente.tipo === "pedido" ? "Entregado" : "Recibido"}
          </button>
        )}
        {d.pendiente?.puedo_cancelar && (
          <button className="boton boton-texto" disabled={envio.enviando} onClick={() => accion(() => api.post(`/archivo/pases/${d.pendiente!.id}/cancelar`))}>
            Cancelar pedido
          </button>
        )}
        {d.puedo.pedir && modo === null && (
          <button className="boton boton-primario" onClick={() => setModo("pedir")}>
            Pedir la carpeta
          </button>
        )}
        {d.puedo.pasar && modo === null && (
          <>
            {registro && d.ubicacion?.area.id !== registro.id && (
              <button
                className="boton"
                disabled={envio.enviando}
                onClick={() => accion(() => api.post("/archivo/envios", { ...params, hacia_area_id: registro.id }))}
              >
                Devolver a Registro
              </button>
            )}
            <button className="boton" onClick={() => setModo("pasar")}>
              Pasar a…
            </button>
          </>
        )}
        {d.puedo.registrar && !d.pendiente && modo === null && (
          <button className={d.ubicacion ? "boton boton-chico boton-texto" : "boton"} onClick={() => setModo("registrar")}>
            {d.ubicacion ? "Corregir ubicación" : "Registrar dónde está"}
          </button>
        )}
        {!compacto && d.historial.length > 0 && (
          <button type="button" className="boton-enlace" onClick={() => setHistorial(!historial)}>
            {historial ? "Ocultar movimientos" : `Movimientos (${d.historial.length})`}
          </button>
        )}
      </div>

      {modo === "pedir" && (
        <div className="carpeta-form">
          <input placeholder="Para qué (opcional): visita, informe, juzgado…" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          <div className="fila-botones">
            <button className="boton" onClick={() => setModo(null)}>
              Volver
            </button>
            <button className="boton boton-primario" disabled={envio.enviando} onClick={() => accion(() => api.post("/archivo/pedidos", { ...params, motivo: motivo || null }))}>
              Enviar pedido
            </button>
          </div>
          <p className="tenue">Le avisa a {d.ubicacion ? dondeEsta(d.ubicacion).replace(/^En /, "").replace(/^La tiene /, "") : "quien la tiene"}; cuando se la den, la confirman en SULAM.</p>
        </div>
      )}

      {(modo === "pasar" || modo === "registrar") && (
        <div className="carpeta-form">
          <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Área">
            <option value="">{modo === "pasar" ? "¿A qué área?" : "¿En qué área está?"}</option>
            {catalogos.areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
          {area && usuariosDelArea.length > 0 && (
            <select value={persona} onChange={(e) => setPersona(e.target.value)} aria-label="Persona">
              <option value="">{modo === "pasar" ? "Al área (cualquiera la recibe)" : "Está en el área (archivada)"}</option>
              {usuariosDelArea.map((u) => (
                <option key={u.id} value={u.id}>
                  {modo === "pasar" ? "A " : "La tiene "}
                  {u.nombre_completo}
                  {hoy?.[u.id] ? ` (${hoy[u.id].texto.toLowerCase()})` : ""}
                </option>
              ))}
            </select>
          )}
          {modo === "registrar" && (
            <label className="casilla">
              <input
                type="checkbox"
                checked={persona === yo.id}
                onChange={(e) => {
                  if (e.target.checked) {
                    setArea(String(yo.area?.id ?? ""));
                    setPersona(yo.id);
                  } else setPersona("");
                }}
              />
              La tengo yo
            </label>
          )}
          {modo === "pasar" && <input placeholder="Motivo (opcional)" value={motivo} onChange={(e) => setMotivo(e.target.value)} />}
          <div className="fila-botones">
            <button className="boton" onClick={() => setModo(null)}>
              Volver
            </button>
            <button
              className="boton boton-primario"
              disabled={!area || envio.enviando}
              onClick={() =>
                accion(() =>
                  modo === "pasar"
                    ? api.post("/archivo/envios", { ...params, hacia_area_id: Number(area), hacia_usuario_id: persona || null, motivo: motivo || null })
                    : api.put("/archivo/ubicacion", { ...params, area_id: Number(area), usuario_id: persona || null }),
                )
              }
            >
              {modo === "pasar" ? "Pasar (lo confirma quien la recibe)" : "Guardar ubicación"}
            </button>
          </div>
        </div>
      )}
      <Aviso error={envio.error} />

      {historial && (
        <ul className="carpeta-historial">
          {d.historial.map((p) => (
            <li key={p.id}>
              <span className={`pase-estado pase-${p.estado}`}>{{ pendiente: "Pendiente", hecho: "Hecho", rechazado: "No se pudo", cancelado: "Cancelado" }[p.estado]}</span>{" "}
              {fechaHora(p.resuelto_en ?? p.iniciado_en)} · {p.desde.usuario?.nombre_completo ?? corta(p.desde.area)} → {p.hacia.usuario?.nombre_completo ?? corta(p.hacia.area)}
              {p.motivo && <span className="tenue"> · {p.motivo}</span>}
              {p.respuesta && <span className="tenue"> · «{p.respuesta}»</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SeccionCarpeta({ personaId }: { personaId: string }) {
  return (
    <Seccion titulo="Carpeta en papel">
      <CarpetaFisica personaId={personaId} />
    </Seccion>
  );
}

// ---------------------------------------------------------------- bandeja de pases

function FilaPase({ p, alCambiar, movil }: { p: Pase; alCambiar: () => void; movil?: boolean }) {
  const envio = useEnvio();
  const [rechazo, setRechazo] = useState<string | null>(null);
  const hacer = (f: () => Promise<unknown>) =>
    envio.ejecutar(f).then((r) => {
      if (r !== undefined) {
        alCambiar();
        avisarPases();
      }
    });
  const enlace = p.objeto.tipo === "legajo" ? `#${movil ? "/m/legajo/" : "/legajos/"}${p.objeto.persona_id}` : `#${movil ? "/m/legajo/" : "/legajos/"}${p.objeto.persona_id}`;
  return (
    <li className="fila-pase">
      <div>
        <a href={enlace}>
          <strong>{p.objeto.texto}</strong>
        </a>
        <span className="tenue">
          {p.tipo === "pedido"
            ? ` · la pide ${p.hacia.usuario?.nombre_completo ?? p.hacia.area}${p.hacia.usuario ? ` (${corta(p.hacia.area)})` : ""}`
            : ` · de ${p.desde.usuario?.nombre_completo ?? corta(p.desde.area)} para ${p.hacia.usuario?.nombre_completo ?? corta(p.hacia.area)}`}
          {" · "}
          {fechaHora(p.iniciado_en)}
        </span>
        {p.motivo && <div className="tenue">«{p.motivo}»</div>}
        {p.estado !== "pendiente" && (
          <div className="tenue">
            {p.estado === "hecho" ? "✓ Hecho" : p.estado === "rechazado" ? "✗ No se pudo" : "Cancelado"}
            {p.resuelto_en && ` el ${fechaHora(p.resuelto_en)}`}
            {p.respuesta && ` · «${p.respuesta}»`}
          </div>
        )}
      </div>
      <div className="fila-pase-acciones">
        {p.puedo_confirmar && rechazo === null && (
          <>
            <button className="boton boton-primario" disabled={envio.enviando} onClick={() => hacer(() => api.post(`/archivo/pases/${p.id}/confirmar`))}>
              {p.tipo === "pedido" ? "Entregado" : "Recibido"}
            </button>
            <button className="boton boton-texto" onClick={() => setRechazo("")}>
              No se puede
            </button>
          </>
        )}
        {rechazo !== null && (
          <>
            <input autoFocus placeholder="Por qué (p. ej., la tiene otra persona)" value={rechazo} onChange={(e) => setRechazo(e.target.value)} />
            <button className="boton" disabled={!rechazo.trim() || envio.enviando} onClick={() => hacer(() => api.post(`/archivo/pases/${p.id}/rechazar`, { respuesta: rechazo }))}>
              Avisar
            </button>
          </>
        )}
        {p.puedo_cancelar && (
          <button className="boton boton-texto" disabled={envio.enviando} onClick={() => hacer(() => api.post(`/archivo/pases/${p.id}/cancelar`))}>
            Cancelar
          </button>
        )}
      </div>
      <Aviso error={envio.error} />
    </li>
  );
}

export function PaginaPases({ movil }: { movil?: boolean }) {
  const { datos: b, error, recargar } = useDatos(() => api.get<Bandeja>("/archivo/bandeja"), []);
  const envio = useEnvio();
  if (error) return <Aviso error={error} />;
  if (!b) return <Cargando />;
  const devolver = (x: Bandeja["en_mi_poder"][number]) =>
    envio
      .ejecutar(() =>
        api.post("/archivo/envios", {
          persona_id: x.expediente_id ? null : x.persona_id,
          expediente_id: x.expediente_id ?? null,
          hacia_area_id: b.area_registro,
        }),
      )
      .then((r) => {
        if (r !== undefined) {
          recargar();
          avisarPases();
        }
      });
  const bloque = (titulo: string, lista: Pase[], vacio: string, ayuda?: string) => (
    <Seccion titulo={`${titulo}${lista.length ? ` (${lista.length})` : ""}`}>
      {ayuda && lista.length > 0 && <p className="tenue">{ayuda}</p>}
      {lista.length === 0 ? (
        <Vacio>{vacio}</Vacio>
      ) : (
        <ul className="lista-pases">
          {lista.map((p) => (
            <FilaPase key={p.id} p={p} alCambiar={recargar} movil={movil} />
          ))}
        </ul>
      )}
    </Seccion>
  );
  return (
    <div className={movil ? "pases-movil" : ""}>
      {!movil && <h1>Pases de carpetas</h1>}
      <p className="tenue">Para pedir una carpeta, búsquela y toque «Pedir la carpeta» en el legajo.</p>
      {bloque("Para entregar", b.entregar, "Nadie le pidió carpetas.", "Cuando la entregue, toque «Entregado».")}
      {bloque("Para recibir", b.recibir, "No hay carpetas en camino hacia usted o su área.", "Cuando la tenga en la mano, toque «Recibido».")}
      {bloque("Mis pedidos", b.mis_pedidos, "No tiene pedidos pendientes.")}
      <Seccion titulo={`Carpetas que tengo${b.en_mi_poder.length ? ` (${b.en_mi_poder.length})` : ""}`}>
        {b.en_mi_poder.length === 0 ? (
          <Vacio>No tiene carpetas a su nombre.</Vacio>
        ) : (
          <ul className="lista-pases">
            {b.en_mi_poder.map((x) => (
              <li key={(x.expediente_id ?? "") + x.persona_id} className="fila-pase">
                <div>
                  <a href={`#${movil ? "/m/legajo/" : "/legajos/"}${x.persona_id}`}>
                    <strong>{x.texto}</strong>
                  </a>
                  <span className="tenue"> · desde {fechaHora(x.desde)}</span>
                </div>
                {b.area_registro && (
                  <div className="fila-pase-acciones">
                    <button className="boton" disabled={envio.enviando} onClick={() => devolver(x)}>
                      Devolver a Registro
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <Aviso error={envio.error} />
      </Seccion>
      {b.recientes.length > 0 && bloque("Últimos movimientos", b.recientes, "")}
      {!movil && <CargaInicial alCargar={recargar} />}
    </div>
  );
}

/** Para anotar de una vez las carpetas que están en el área (carga inicial del archivo). */
function CargaInicial({ alCargar }: { alCargar: () => void }) {
  const { yo } = useSesion();
  const [texto, setTexto] = useState("");
  const [r, setR] = useState<{ cargadas: string[]; ya_ubicadas: { numero: string; donde: string }[]; no_encontradas: string[] } | null>(null);
  const envio = useEnvio();
  if (!yo.area) return null;
  const numeros = texto.split(/[\s,;]+/).filter(Boolean);
  return (
    <Seccion titulo={`Anotar carpetas que están en ${yo.area.nombre}`}>
      <p className="tenue">
        Para empezar: escriba o pegue los números de legajo de las carpetas que tienen en el área (uno por renglón o separados por coma). Solo se
        anotan las que todavía no tienen ubicación.
      </p>
      <textarea rows={4} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={"4123456\n6234511\n…"} />
      <div className="fila-botones">
        <button
          className="boton boton-primario"
          disabled={numeros.length === 0 || envio.enviando}
          onClick={() =>
            envio.ejecutar(() => api.post<typeof r>("/archivo/carga-inicial", { numeros })).then((x) => {
              if (x) {
                setR(x);
                setTexto("");
                alCargar();
              }
            })
          }
        >
          Anotar {numeros.length || ""} {numeros.length === 1 ? "carpeta" : "carpetas"}
        </button>
      </div>
      <Aviso error={envio.error} />
      {r && (
        <div className="aviso aviso-info">
          <p>Anotadas: {r.cargadas.length ? r.cargadas.join(", ") : "ninguna"}.</p>
          {r.ya_ubicadas.length > 0 && <p>Ya tenían ubicación: {r.ya_ubicadas.map((x) => `${x.numero} (${x.donde})`).join(", ")}.</p>}
          {r.no_encontradas.length > 0 && <p>No existen en SULAM: {r.no_encontradas.join(", ")}.</p>}
        </div>
      )}
    </Seccion>
  );
}

/** Aviso del inicio (computadora y celular). */
export function PasesPendientes({ movil }: { movil?: boolean }) {
  const { datos } = usePasesPendientes();
  if (!datos || datos.cantidad === 0) return null;
  const partes = [];
  if (datos.entregar) partes.push(`${datos.entregar} ${datos.entregar === 1 ? "carpeta para entregar" : "carpetas para entregar"}`);
  if (datos.recibir) partes.push(`${datos.recibir} ${datos.recibir === 1 ? "carpeta para recibir" : "carpetas para recibir"}`);
  return (
    <a className={`pases-inicio ${movil ? "pases-inicio-movil" : ""}`} href={movil ? "#/m/pases" : "#/pases"}>
      🗂 <strong>Pases:</strong> {partes.join(" y ")} →
    </a>
  );
}

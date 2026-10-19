// Chat interno: conversaciones 1 a 1 y en grupo entre personas que usan SULAM.
// No hay tiempo real: la pantalla consulta cada pocos segundos mientras está abierta.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Aviso, Cargando, Modal, Vacio, navegar, useDatos, useEnvio, useSesion } from "../comun";

interface Persona {
  id: string;
  nombre_completo: string;
  area: string | null;
  roles: string[];
}

interface Conversacion {
  id: string;
  tipo: "directo" | "grupo";
  titulo: string;
  participantes: Persona[];
  creada_por: string;
  ultimo: { cuerpo: string; autor: string; mio: boolean; creado_en: string } | null;
  no_leidos: number;
  ultimo_mensaje_en: string;
}

interface Mensaje {
  id: string;
  autor: { id: string; nombre_completo: string };
  cuerpo: string | null;
  borrado: boolean;
  creado_en: string;
  mio: boolean;
}

const base = (movil?: boolean) => (movil ? "/m/chat" : "/chat");

function esHoy(d: Date) {
  const h = new Date();
  return d.getFullYear() === h.getFullYear() && d.getMonth() === h.getMonth() && d.getDate() === h.getDate();
}

function cuando(iso: string): string {
  const d = new Date(iso);
  const hora = d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
  return esHoy(d) ? hora : `${d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" })} ${hora}`;
}

function corta(nombre: string) {
  return nombre.replace(/^(Departamento|División)\s+/, "");
}

/** Mensajes sin leer, para la insignia del menú. Consulta cada 20 segundos y al cambiar de pantalla. */
export function useChatNoLeidos(ruta: string) {
  const { puede } = useSesion();
  const [n, setN] = useState(0);
  const permitido = puede("chat", "usar");
  const traer = useCallback(async () => {
    if (!permitido) return;
    try {
      setN((await api.get<{ mensajes: number }>("/chat/no-leidos")).mensajes);
    } catch {
      /* sin conexión: se vuelve a intentar */
    }
  }, [permitido]);
  useEffect(() => {
    traer();
    const t = setInterval(traer, 20_000);
    return () => clearInterval(t);
  }, [traer, ruta]);
  return n;
}

export function InsigniaChat({ ruta }: { ruta: string }) {
  const n = useChatNoLeidos(ruta);
  if (!n) return null;
  return (
    <span className="insignia" aria-label={`${n} mensajes sin leer`}>
      {n}
    </span>
  );
}

export function PaginaChat({ id, movil }: { id?: string; movil?: boolean }) {
  const lista = useDatos(() => api.get<{ conversaciones: Conversacion[]; no_leidos: number }>("/chat/conversaciones"), []);
  const [nueva, setNueva] = useState(false);
  const { recargar } = lista;
  useEffect(() => {
    const t = setInterval(recargar, 8_000);
    return () => clearInterval(t);
  }, [recargar]);
  const conversaciones = lista.datos?.conversaciones ?? [];
  const abierta = conversaciones.find((c) => c.id === id) ?? null;
  const verLista = !movil || !id;
  const verConversacion = !movil || !!id;
  return (
    <div className={`chat ${movil ? "chat-movil" : ""}`}>
      {verLista && (
        <aside className="chat-lista" aria-label="Conversaciones">
          <header>
            {!movil && <h1>Chat</h1>}
            <button className={movil ? "m-boton m-boton-primario" : "boton boton-primario"} onClick={() => setNueva(true)}>
              Nueva conversación
            </button>
          </header>
          <Aviso error={lista.error} />
          {!lista.datos ? (
            <Cargando />
          ) : conversaciones.length === 0 ? (
            <Vacio>Todavía no tiene conversaciones. Empiece una con «Nueva conversación».</Vacio>
          ) : (
            <ul>
              {conversaciones.map((c) => (
                <li key={c.id}>
                  <a href={`#${base(movil)}/${c.id}`} className={`${c.id === id ? "activa" : ""} ${c.no_leidos ? "sin-leer" : ""}`} aria-current={c.id === id ? "true" : undefined}>
                    <span className="chat-avatar" aria-hidden>
                      {c.tipo === "grupo" ? "👥" : c.titulo.charAt(0).toUpperCase()}
                    </span>
                    <span className="chat-resumen">
                      <strong>{c.titulo}</strong>
                      <small>{c.ultimo ? `${c.ultimo.mio ? "Yo: " : c.tipo === "grupo" ? `${c.ultimo.autor}: ` : ""}${c.ultimo.cuerpo}` : "Sin mensajes todavía"}</small>
                    </span>
                    <span className="chat-meta">
                      {c.ultimo && <small>{cuando(c.ultimo.creado_en)}</small>}
                      {c.no_leidos > 0 && (
                        <span className="insignia" aria-label={`${c.no_leidos} sin leer`}>
                          {c.no_leidos}
                        </span>
                      )}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </aside>
      )}
      {verConversacion && (
        <section className="chat-conversacion">
          {id && lista.datos && !abierta ? (
            <Vacio>Esa conversación no existe o no participa en ella.</Vacio>
          ) : id && abierta ? (
            <Hilo key={abierta.id} c={abierta} movil={movil} alCambiar={recargar} />
          ) : (
            !movil && <Vacio>Elija una conversación o empiece una nueva.</Vacio>
          )}
        </section>
      )}
      {nueva && (
        <Modal titulo="Nueva conversación" alCerrar={() => setNueva(false)}>
          <FormNueva
            movil={movil}
            alCrear={(c) => {
              setNueva(false);
              recargar();
              navegar(`${base(movil)}/${c.id}`);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function Hilo({ c, movil, alCambiar }: { c: Conversacion; movil?: boolean; alCambiar: () => void }) {
  const [mensajes, setMensajes] = useState<Mensaje[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [texto, setTexto] = useState("");
  const [sumar, setSumar] = useState(false);
  const envio = useEnvio();
  const fin = useRef<HTMLDivElement>(null);
  const ultimo = useRef<string | null>(null);
  const { yo } = useSesion();

  const traer = useCallback(async () => {
    try {
      const r = await api.get<{ mensajes: Mensaje[] }>(`/chat/conversaciones/${c.id}/mensajes`, { despues: ultimo.current ?? undefined });
      setError(null);
      if (ultimo.current === null) {
        setMensajes(r.mensajes);
      } else if (r.mensajes.length) {
        setMensajes((prev) => {
          const ya = new Set((prev ?? []).map((m) => m.id));
          return [...(prev ?? []), ...r.mensajes.filter((m) => !ya.has(m.id))];
        });
      }
      if (r.mensajes.length) ultimo.current = r.mensajes[r.mensajes.length - 1].id;
      else if (ultimo.current === null) ultimo.current = "";
      if (r.mensajes.length) alCambiar();
    } catch (e) {
      setError(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.id]);

  useEffect(() => {
    ultimo.current = null;
    setMensajes(null);
    traer();
    const t = setInterval(traer, 5_000);
    return () => clearInterval(t);
  }, [traer]);

  useEffect(() => {
    fin.current?.scrollIntoView({ block: "end" });
  }, [mensajes?.length]);

  const enviar = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const cuerpo = texto.trim();
    if (!cuerpo) return;
    const m = await envio.ejecutar(() => api.post<Mensaje>(`/chat/conversaciones/${c.id}/mensajes`, { cuerpo }));
    if (m) {
      setTexto("");
      setMensajes((prev) => (prev && prev.some((x) => x.id === m.id) ? prev : [...(prev ?? []), m]));
      ultimo.current = m.id;
      alCambiar();
    }
  };

  const borrar = async (m: Mensaje) => {
    if (!confirm("¿Borrar este mensaje? Queda «mensaje borrado» para todos.")) return;
    if (await envio.ejecutar(() => api.delete(`/chat/mensajes/${m.id}`))) {
      setMensajes((prev) => (prev ?? []).map((x) => (x.id === m.id ? { ...x, borrado: true, cuerpo: null } : x)));
    }
  };

  const salir = async () => {
    if (!confirm("¿Salir de este grupo? Deja de ver sus mensajes.")) return;
    if (await envio.ejecutar(() => api.post(`/chat/conversaciones/${c.id}/salir`))) {
      alCambiar();
      navegar(base(movil));
    }
  };

  const otros = c.participantes.filter((p) => p.id !== yo.id);
  return (
    <>
      <header className="chat-cabecera">
        <div>
          <h2>{c.titulo}</h2>
          <small className="tenue">
            {c.tipo === "grupo"
              ? `${c.participantes.length} personas: ${c.participantes.map((p) => p.nombre_completo).join(", ")}`
              : [otros[0]?.area && corta(otros[0].area), otros[0]?.roles.join(" · ")].filter(Boolean).join(" · ")}
          </small>
        </div>
        {c.tipo === "grupo" && (
          <div className="chat-acciones">
            {c.creada_por === yo.id && (
              <button type="button" className="boton boton-chico" onClick={() => setSumar(true)}>
                Sumar personas
              </button>
            )}
            <button type="button" className="boton boton-chico boton-texto" onClick={salir}>
              Salir del grupo
            </button>
          </div>
        )}
      </header>
      <div className="chat-mensajes" role="log" aria-live="polite" aria-label="Mensajes">
        <Aviso error={error} />
        {!mensajes ? (
          <Cargando />
        ) : mensajes.length === 0 ? (
          <Vacio>Todavía no hay mensajes. Escriba el primero.</Vacio>
        ) : (
          mensajes.map((m) => (
            <div key={m.id} className={`chat-burbuja ${m.mio ? "mio" : ""} ${m.borrado ? "borrado" : ""}`}>
              {!m.mio && c.tipo === "grupo" && <strong>{m.autor.nombre_completo}</strong>}
              <p>{m.borrado ? "Mensaje borrado" : m.cuerpo}</p>
              <small>
                {cuando(m.creado_en)}
                {m.mio && !m.borrado && (
                  <button type="button" className="chat-borrar" onClick={() => borrar(m)} aria-label="Borrar mensaje">
                    Borrar
                  </button>
                )}
              </small>
            </div>
          ))
        )}
        <div ref={fin} />
      </div>
      <form className="chat-escribir" onSubmit={enviar}>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !movil) {
              e.preventDefault();
              enviar();
            }
          }}
          placeholder={movil ? "Escribir un mensaje…" : "Escribir un mensaje (Enter envía, Mayús+Enter hace un renglón)…"}
          aria-label="Mensaje"
          rows={movil ? 2 : 3}
          maxLength={2000}
        />
        <button className={movil ? "m-boton m-boton-primario" : "boton boton-primario"} disabled={envio.enviando || !texto.trim()}>
          Enviar
        </button>
      </form>
      <Aviso error={envio.error} />
      {sumar && (
        <Modal titulo="Sumar personas al grupo" alCerrar={() => setSumar(false)}>
          <SelectorPersonas
            excluir={c.participantes.map((p) => p.id)}
            etiquetaBoton="Sumar al grupo"
            alElegir={async (ids) => {
              const r = await envio.ejecutar(() => api.post(`/chat/conversaciones/${c.id}/participantes`, { usuarios_ids: ids }));
              if (r) {
                setSumar(false);
                alCambiar();
              }
            }}
          />
        </Modal>
      )}
    </>
  );
}

function SelectorPersonas({ excluir = [], etiquetaBoton, alElegir }: { excluir?: string[]; etiquetaBoton: string; alElegir: (ids: string[]) => void }) {
  const [q, setQ] = useState("");
  const [elegidas, setElegidas] = useState<string[]>([]);
  const personas = useDatos(() => api.get<Persona[]>("/chat/usuarios", { q }), [q]);
  const visibles = (personas.datos ?? []).filter((p) => !excluir.includes(p.id));
  return (
    <div className="chat-selector">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nombre" aria-label="Buscar persona" maxLength={100} autoFocus />
      <Aviso error={personas.error} />
      {!personas.datos ? (
        <Cargando />
      ) : visibles.length === 0 ? (
        <Vacio>No hay personas con ese nombre.</Vacio>
      ) : (
        <ul>
          {visibles.map((p) => (
            <li key={p.id}>
              <label className="casilla">
                <input
                  type="checkbox"
                  checked={elegidas.includes(p.id)}
                  onChange={(e) => setElegidas((prev) => (e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id)))}
                />
                <span>
                  {p.nombre_completo}
                  <small className="tenue">
                    {" "}
                    · {[p.area && corta(p.area), p.roles.join(" · ")].filter(Boolean).join(" · ") || "sin área"}
                  </small>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="boton boton-primario" disabled={elegidas.length === 0} onClick={() => alElegir(elegidas)}>
        {etiquetaBoton}
        {elegidas.length ? ` (${elegidas.length})` : ""}
      </button>
    </div>
  );
}

function FormNueva({ alCrear, movil }: { alCrear: (c: Conversacion) => void; movil?: boolean }) {
  const [modo, setModo] = useState<"directo" | "grupo">("directo");
  const [titulo, setTitulo] = useState("");
  const [q, setQ] = useState("");
  const personas = useDatos(() => api.get<Persona[]>("/chat/usuarios", { q }), [q]);
  const envio = useEnvio();
  return (
    <div className="chat-nueva">
      <div className={movil ? "m-chips" : "segmentado"} role="group" aria-label="Tipo de conversación">
        <button type="button" className={modo === "directo" ? "activo" : ""} onClick={() => setModo("directo")}>
          Con una persona
        </button>
        <button type="button" className={modo === "grupo" ? "activo" : ""} onClick={() => setModo("grupo")}>
          Grupo
        </button>
      </div>
      {modo === "directo" ? (
        <>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nombre" aria-label="Buscar persona" maxLength={100} autoFocus />
          <Aviso error={personas.error ?? envio.error} />
          {!personas.datos ? (
            <Cargando />
          ) : personas.datos.length === 0 ? (
            <Vacio>No hay personas con ese nombre.</Vacio>
          ) : (
            <ul className="chat-personas">
              {personas.datos.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    disabled={envio.enviando}
                    onClick={async () => {
                      const c = await envio.ejecutar(() => api.post<Conversacion>("/chat/conversaciones", { tipo: "directo", usuario_id: p.id }));
                      if (c) alCrear(c);
                    }}
                  >
                    <strong>{p.nombre_completo}</strong>
                    <small>{[p.area && corta(p.area), p.roles.join(" · ")].filter(Boolean).join(" · ") || "sin área"}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <>
          <label className="campo">
            <span className="campo-etiqueta">Nombre del grupo *</span>
            <input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={120} placeholder="Ej.: Guardia del fin de semana" />
          </label>
          <Aviso error={envio.error} />
          <SelectorPersonas
            etiquetaBoton="Crear grupo"
            alElegir={async (ids) => {
              const c = await envio.ejecutar(() => api.post<Conversacion>("/chat/conversaciones", { tipo: "grupo", titulo, usuarios_ids: ids }));
              if (c) alCrear(c);
            }}
          />
        </>
      )}
    </div>
  );
}

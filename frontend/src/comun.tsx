import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, type Catalogos, type Formularios, type PersonaResumen, type Yo } from "./api";

// ---------------------------------------------------------------- navegación (hash)

export function rutaActual(): string {
  return window.location.hash.replace(/^#/, "") || "/";
}

/** Pantalla chica o táctil: se ofrece la versión para celular. */
export function esCelular(): boolean {
  return window.matchMedia("(max-width: 700px), (pointer: coarse) and (max-width: 1000px)").matches;
}

export function navegar(ruta: string) {
  window.location.hash = ruta;
}

export function useRuta(): string {
  const [ruta, setRuta] = useState(rutaActual());
  useEffect(() => {
    const f = () => {
      setRuta(rutaActual());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return ruta;
}

export function Enlace({ a, children, className }: { a: string; children: ReactNode; className?: string }) {
  return (
    <a href={"#" + a} className={className}>
      {children}
    </a>
  );
}

// ---------------------------------------------------------------- sesión

interface Sesion {
  yo: Yo;
  catalogos: Catalogos;
  formularios: Formularios;
  puede: (modulo: string, accion: string) => boolean;
  recargarCatalogos: () => void;
}

export const SesionCtx = createContext<Sesion | null>(null);

export function useSesion(): Sesion {
  const s = useContext(SesionCtx);
  if (!s) throw new Error("Sin sesión");
  return s;
}

// ---------------------------------------------------------------- datos

export function useDatos<T>(cargar: () => Promise<T>, deps: unknown[]) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [version, setVersion] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const f = useCallback(cargar, deps);
  useEffect(() => {
    let vigente = true;
    setError(null);
    f()
      .then((d) => vigente && setDatos(d))
      .catch((e) => vigente && setError(e));
    return () => {
      vigente = false;
    };
  }, [f, version]);
  return { datos, error, recargar: () => setVersion((v) => v + 1), setDatos };
}

// ---------------------------------------------------------------- formato

const fmtFecha = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" });
const fmtFechaHora = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function fecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.length === 10 ? new Date(iso + "T12:00:00") : new Date(iso);
  return fmtFecha.format(d);
}

export function fechaHora(iso: string | null | undefined): string {
  return iso ? fmtFechaHora.format(new Date(iso)) : "—";
}

export function edad(iso: string | null): number | null {
  if (!iso) return null;
  const n = new Date(iso + "T12:00:00");
  const hoy = new Date();
  let e = hoy.getFullYear() - n.getFullYear();
  if (hoy.getMonth() < n.getMonth() || (hoy.getMonth() === n.getMonth() && hoy.getDate() < n.getDate())) e--;
  return e;
}

export function documento(p: Pick<PersonaResumen, "tipo_documento" | "numero_documento" | "sin_documento">): string {
  if (p.numero_documento) return `${p.tipo_documento ?? ""} ${Number(p.numero_documento) ? Number(p.numero_documento).toLocaleString("es-AR") : p.numero_documento}`.trim();
  return p.sin_documento ? "Sin documento" : "Documento no informado";
}

export function nombre(p: Pick<PersonaResumen, "apellidos" | "nombres">): string {
  return `${p.apellidos.toUpperCase()}, ${p.nombres}`;
}

export function tamano(bytes?: number): string {
  if (bytes === undefined) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const ESTADOS: Record<string, string> = {
  abierto: "Abierto",
  en_seguimiento: "En seguimiento",
  pausado: "Pausado",
  cerrado: "Cerrado",
};

// ---------------------------------------------------------------- componentes

export function Estado({ estado }: { estado: string }) {
  return <span className={`insignia estado-${estado}`}>{ESTADOS[estado] ?? estado}</span>;
}

export function Aviso({ error, tipo = "error" }: { error: unknown; tipo?: "error" | "info" | "exito" }) {
  if (!error) return null;
  const texto = typeof error === "string" ? error : error instanceof Error ? error.message : String(error);
  return (
    <div className={`aviso aviso-${tipo}`} role={tipo === "error" ? "alert" : "status"}>
      {texto}
    </div>
  );
}

export function Cargando() {
  return <p className="cargando">Cargando…</p>;
}

export function Vacio({ children }: { children: ReactNode }) {
  return <p className="vacio">{children}</p>;
}

export function Campo({
  etiqueta,
  children,
  ayuda,
  ancho,
}: {
  etiqueta: string;
  children: ReactNode;
  ayuda?: string;
  ancho?: "completo" | "medio";
}) {
  return (
    <label className={`campo ${ancho ? "campo-" + ancho : ""}`}>
      <span className="campo-etiqueta">{etiqueta}</span>
      {children}
      {ayuda && <span className="campo-ayuda">{ayuda}</span>}
    </label>
  );
}

export function Modal({
  titulo,
  children,
  alCerrar,
  ancho,
}: {
  titulo: string;
  children: ReactNode;
  alCerrar: () => void;
  ancho?: boolean;
}) {
  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === "Escape" && alCerrar();
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [alCerrar]);
  return (
    <div className="modal-fondo" onMouseDown={(e) => e.target === e.currentTarget && alCerrar()}>
      <div className={`modal ${ancho ? "modal-ancho" : ""}`} role="dialog" aria-modal="true" aria-label={titulo}>
        <header className="modal-cabecera">
          <h2>{titulo}</h2>
          <button type="button" className="boton-icono" onClick={alCerrar} aria-label="Cerrar">
            ×
          </button>
        </header>
        <div className="modal-cuerpo">{children}</div>
      </div>
    </div>
  );
}

export function Seccion({
  titulo,
  acciones,
  children,
  id,
}: {
  titulo: string;
  acciones?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section className="seccion" id={id}>
      <header className="seccion-cabecera">
        <h2>{titulo}</h2>
        {acciones && <div className="seccion-acciones">{acciones}</div>}
      </header>
      {children}
    </section>
  );
}

/** Ejecuta una acción asíncrona mostrando el estado de envío y el error. */
export function useEnvio() {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const ejecutar = async <T,>(f: () => Promise<T>): Promise<T | undefined> => {
    setEnviando(true);
    setError(null);
    try {
      return await f();
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setEnviando(false);
    }
  };
  return { enviando, error, setError, ejecutar };
}

export function valor(e: { target: { value: string } }): string {
  return e.target.value;
}

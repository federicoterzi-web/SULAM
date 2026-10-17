// Versión para celular: las mismas funciones de SULAM pensadas para el pulgar.
// Pantallas cortas, botones grandes, teclado numérico para DNI y fechas, y la
// cámara integrada. Nada se guarda en el teléfono: todo va directo al servidor.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, type Caso, type Legajo, type PersonaResumen } from "../api";
import { Aviso, Cargando, ESTADOS, documento, edad, fecha, navegar, nombre, useDatos, useSesion } from "../comun";
import { textoLista } from "../paginas/formularios";
import { CaratulaMovil, NuevaPersonaMovil, ReiteracionMovil } from "./carga";
import { EvolucionMovil } from "./evolucion";
import { FotosMovil } from "./fotos";
import { RecursosMovil } from "./recursos";
import { VisitasMovil } from "./visitas";
import { UbicacionDomicilio } from "../paginas/ubicacion";
import type { Articulacion } from "../paginas/articulaciones";
import { ContactoFormMovil, FormularioCasoMovil, FormularioLegajoMovil, IngresoMovil, RecursoFormMovil } from "./formularios";

// ---------------------------------------------------------------- aviso entre pantallas

let avisoPendiente: string | null = null;

/** Muestra un aviso breve en la próxima pantalla (p. ej. «Evolución guardada»). */
export function avisar(texto: string) {
  avisoPendiente = texto;
}

function AvisoFlotante() {
  const [texto, setTexto] = useState<string | null>(null);
  useEffect(() => {
    if (avisoPendiente) {
      setTexto(avisoPendiente);
      avisoPendiente = null;
    }
  });
  useEffect(() => {
    if (!texto) return;
    const t = setTimeout(() => setTexto(null), 3500);
    return () => clearTimeout(t);
  }, [texto]);
  if (!texto) return null;
  return (
    <div className="m-aviso-flotante" role="status" onClick={() => setTexto(null)}>
      ✓ {texto}
    </div>
  );
}

// ---------------------------------------------------------------- estructura

export function Movil({ ruta, alSalir, alCambiarPassword }: { ruta: string; alSalir: () => void; alCambiarPassword: () => void }) {
  const p = ruta.split("?")[0].split("/").filter(Boolean).slice(1); // sin la "m"
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [ruta]);

  const salir = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      alSalir();
      navegar("/m");
    }
  };

  const seccion = p[0] ?? "";
  // En los formularios se ocultan las pestañas: más lugar y sin toques accidentales.
  const enFormulario =
    p[0] === "nuevo" || p[0] === "ingreso" || p.length > 2 || ((p[0] === "recursos" || p[0] === "contactos") && p[1] === "nuevo");
  return (
    <div className={`m-app ${enFormulario ? "m-app-formulario" : ""}`}>
      <header className="m-barra">
        {p.length > 0 ? (
          <button className="m-barra-boton" onClick={() => history.back()} aria-label="Volver">
            ‹
          </button>
        ) : (
          <span className="m-barra-marca">SULAM</span>
        )}
        <span className="m-barra-titulo">{titulo(p)}</span>
        <button className="m-barra-boton" onClick={() => setMenu(!menu)} aria-label="Más opciones" aria-expanded={menu}>
          ⋮
        </button>
      </header>
      {menu && (
        <div className="m-menu-fondo" onClick={() => setMenu(false)}>
          <nav className="m-menu" onClick={(e) => e.stopPropagation()}>
            <MenuUsuario />
            <a href={"#" + equivalenteCompleto(p)}>Ver en la versión completa</a>
            <button onClick={alCambiarPassword}>Cambiar contraseña</button>
            <button onClick={salir}>Cerrar sesión</button>
          </nav>
        </div>
      )}
      <main className="m-contenido" id="contenido">
        <AvisoFlotante />
        <Pantalla p={p} ruta={ruta} />
      </main>
      {!enFormulario && (
      <nav className="m-pestanas" aria-label="Secciones">
        <a href="#/m" className={seccion === "" ? "activo" : ""}>
          <span aria-hidden>⌂</span>Inicio
        </a>
        <a href="#/m/buscar" className={seccion === "buscar" ? "activo" : ""}>
          <span aria-hidden>⌕</span>Buscar
        </a>
        <PestanaNuevo activo={seccion === "nuevo"} />
        <PestanaRecursos activo={seccion === "recursos"} />
      </nav>
      )}
    </div>
  );
}

function PestanaNuevo({ activo }: { activo: boolean }) {
  const { puede } = useSesion();
  if (!puede("casos", "crear")) return null;
  return (
    <a href="#/m/nuevo" className={activo ? "activo" : ""}>
      <span aria-hidden>＋</span>Nuevo caso
    </a>
  );
}

function PestanaRecursos({ activo }: { activo: boolean }) {
  const { puede } = useSesion();
  if (!puede("recursos", "consultar")) return null;
  return (
    <a href="#/m/recursos" className={activo ? "activo" : ""}>
      <span aria-hidden>⌖</span>Recursos
    </a>
  );
}

function MenuUsuario() {
  const { yo } = useSesion();
  return (
    <div className="m-menu-usuario">
      <strong>{yo.nombre_completo}</strong>
      <small>{yo.roles.join(" · ") || "Sin rol"}</small>
      {yo.inactividad_minutos && <small>La sesión se cierra tras {yo.inactividad_minutos} min sin uso.</small>}
    </div>
  );
}

function titulo(p: string[]): string {
  switch (p[0]) {
    case undefined:
      return "";
    case "buscar":
      return "Buscar";
    case "recursos":
      return p[1] === "nuevo" ? "Nuevo recurso" : p[2] === "editar" ? "Editar recurso" : "Recursos";
    case "contactos":
      return p[1] === "nuevo" ? "Nuevo contacto" : "Editar contacto";
    case "ingreso":
      return "Mesa de Entrada";
    case "visitas":
      return "Salida de visitas";
    case "nuevo":
      return "Nuevo caso";
    case "legajo":
      return (
        { caratula: "Carátula", fotos: "Fotos", editar: "Datos personales", vinculado: "Vínculo", expediente: "Expediente" }[p[2] ?? ""] ??
        "Legajo"
      );
    case "caso":
      return (
        {
          evolucion: "Evolución",
          fotos: "Fotos",
          reiteracion: "Reiteración",
          demanda: "Registro de demanda",
          estado: "Estado del caso",
          asignar: "Asignar / derivar",
          editar: "Editar caso",
          caratula: "Carátula",
          articulacion: "Articulación",
        }[p[2] ?? ""] ?? "Caso"
      );
    default:
      return "";
  }
}

function equivalenteCompleto(p: string[]): string {
  if (p[0] === "legajo" && p[1]) return `/legajos/${p[1]}`;
  if (p[0] === "caso" && p[1]) return `/casos/${p[1]}`;
  if (p[0] === "buscar" && p[1]) return `/buscar/${p[1]}`;
  if (p[0] === "recursos" && p[1] && p[1] !== "nuevo") return `/recursos/${p[1]}`;
  if (p[0] === "recursos") return "/recursos";
  if (p[0] === "contactos") return "/contactos";
  if (p[0] === "ingreso") return "/mesa";
  if (p[0] === "visitas") return "/visitas";
  return "/";
}

function parametro(ruta: string, clave: string): string {
  return new URLSearchParams(ruta.split("?")[1] ?? "").get(clave) ?? "";
}

function Pantalla({ p, ruta }: { p: string[]; ruta: string }) {
  switch (p[0]) {
    case undefined:
      return <InicioMovil />;
    case "recursos":
      if (p[1] === "nuevo") return <RecursoFormMovil />;
      if (p[1] && p[2] === "editar") return <RecursoFormMovil id={p[1]} key={p[1]} />;
      return <RecursosMovil />;
    case "contactos":
      if (p[1] === "nuevo") return <ContactoFormMovil />;
      if (p[1] && p[2] === "editar") return <ContactoFormMovil id={p[1]} key={p[1]} />;
      return <Aviso error="Pantalla inexistente." />;
    case "ingreso":
      return <IngresoMovil />;
    case "visitas":
      return <VisitasMovil />;
    case "buscar":
      return <BuscarMovil q={decodeURIComponent(p[1] ?? "")} key={p[1] ?? ""} />;
    case "nuevo":
      return <NuevaPersonaMovil dni={parametro(ruta, "dni")} />;
    case "legajo":
      if (p[2] === "caratula") return <CaratulaMovil personaId={p[1]} key={p[1]} />;
      if (p[2] === "fotos") return <FotosMovil personaId={p[1]} key={p[1]} />;
      if (p[2] === "editar" || p[2] === "vinculado" || p[2] === "expediente")
        return <FormularioLegajoMovil personaId={p[1]} que={p[2]} vinculadoId={parametro(ruta, "editar") || undefined} key={ruta} />;
      return <LegajoMovil id={p[1]} key={p[1]} />;
    case "caso":
      if (p[2] === "evolucion") return <EvolucionMovil casoId={p[1]} key={p[1]} />;
      if (p[2] === "fotos") return <FotosMovil casoId={p[1]} demandaId={parametro(ruta, "demanda")} key={p[1]} />;
      if (p[2] === "reiteracion") return <ReiteracionMovil casoId={p[1]} key={p[1]} />;
      if (p[2]) return <FormularioCasoMovil casoId={p[1]} que={p[2]} demandaId={parametro(ruta, "editar") || undefined} key={ruta} />;
      return <CasoMovil id={p[1]} key={p[1]} />;
    default:
      return <Aviso error="Pantalla inexistente." />;
  }
}

// ---------------------------------------------------------------- piezas comunes

export function Tarjeta({ a, children, className = "" }: { a?: string; children: ReactNode; className?: string }) {
  return a ? (
    <a className={`m-tarjeta m-tarjeta-enlace ${className}`} href={"#" + a}>
      {children}
    </a>
  ) : (
    <div className={`m-tarjeta ${className}`}>{children}</div>
  );
}

export function Accion({ a, onClick, icono, children, principal }: { a?: string; onClick?: () => void; icono: string; children: ReactNode; principal?: boolean }) {
  const clase = `m-accion ${principal ? "m-accion-principal" : ""}`;
  const contenido = (
    <>
      <span className="m-accion-icono" aria-hidden>
        {icono}
      </span>
      <span>{children}</span>
    </>
  );
  return a ? (
    <a className={clase} href={"#" + a}>
      {contenido}
    </a>
  ) : (
    <button type="button" className={clase} onClick={onClick}>
      {contenido}
    </button>
  );
}

function telefonos(texto: string | null | undefined): string[] {
  if (!texto) return [];
  return texto
    .split(/[\/,;]| y | o /)
    .map((t) => t.trim())
    .filter((t) => t.replace(/\D/g, "").length >= 6);
}

export function Llamar({ telefono, quien }: { telefono: string | null | undefined; quien?: string }) {
  const lista = telefonos(telefono);
  if (lista.length === 0) return null;
  return (
    <>
      {lista.map((t) => (
        <a key={t} className="m-llamar" href={`tel:${t.replace(/[^\d+]/g, "")}`}>
          <span aria-hidden>✆</span> Llamar {quien ? `a ${quien}` : ""} · {t}
        </a>
      ))}
    </>
  );
}

function FichaPersona({ p }: { p: PersonaResumen }) {
  const e = edad(p.fecha_nacimiento);
  return (
    <>
      <strong className="m-nombre">{nombre(p)}</strong>
      <span className="m-detalle">
        {documento(p)}
        {e !== null && ` · ${e} años`}
        {p.localidad && ` · ${p.localidad}`}
      </span>
    </>
  );
}

function FichaCaso({ c, conPersona }: { c: Caso; conPersona?: boolean }) {
  const car = c.caratula;
  return (
    <>
      <span className="m-fila-titulo">
        <strong>
          {car?.numero_actuacion ? `Actuación ${car.numero_actuacion}/${car.anio_actuacion}` : c.numero}
        </strong>
        <span className={`m-estado estado-${c.estado}`}>{ESTADOS[c.estado]}</span>
      </span>
      {conPersona && c.persona && <span className="m-nombre-chico">{nombre(c.persona)}</span>}
      <span className="m-detalle">
        {c.area?.nombre.replace(/^Departamento |^División /, "") ?? "Sin área"}
        {c.ultima_actividad && ` · últ. actividad ${fecha(c.ultima_actividad)}`}
      </span>
    </>
  );
}

// ---------------------------------------------------------------- inicio

function InicioMovil() {
  const { yo, puede } = useSesion();
  const consultaCasos = puede("casos", "consultar");
  const mios = useDatos(
    () => (consultaCasos ? api.get<Caso[]>("/casos", { asignados_a_mi: true, limite: 30 }) : Promise.resolve(null)),
    [consultaCasos],
  );
  const recientes = useDatos(
    () => (mios.datos && mios.datos.length === 0 ? api.get<Caso[]>("/casos", { limite: 15 }) : Promise.resolve(null)),
    [mios.datos],
  );
  return (
    <>
      <p className="m-saludo">Hola, {yo.nombre_completo.split(" ")[0]}</p>
      <CajaBusqueda inicial="" />
      <div className="m-acciones">
        {puede("mesa_entrada", "crear") && (
          <Accion a="/m/ingreso" icono="⇲" principal={!consultaCasos}>
            Registrar ingreso en Mesa de Entrada
          </Accion>
        )}
        {consultaCasos && (
          <Accion a="/m/visitas" icono="⌖">
            Mapa de casos y salida de visitas
          </Accion>
        )}
        {puede("recursos", "crear") && (
          <Accion a="/m/recursos/nuevo" icono="＋">
            Agregar un lugar al mapa de recursos
          </Accion>
        )}
      </div>
      {consultaCasos && <h2 className="m-subtitulo">Mis casos</h2>}
      {mios.error && <Aviso error={mios.error} />}
      {!consultaCasos ? null : !mios.datos ? (
        <Cargando />
      ) : mios.datos.length === 0 ? (
        <p className="m-tenue">No tiene casos asignados.</p>
      ) : (
        mios.datos.map((c) => (
          <Tarjeta key={c.id} a={`/m/caso/${c.id}`}>
            <FichaCaso c={c} conPersona />
          </Tarjeta>
        ))
      )}
      {recientes.datos && recientes.datos.length > 0 && (
        <>
          <h2 className="m-subtitulo">Con actividad reciente</h2>
          {recientes.datos.map((c) => (
            <Tarjeta key={c.id} a={`/m/caso/${c.id}`}>
              <FichaCaso c={c} conPersona />
            </Tarjeta>
          ))}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- búsqueda

function CajaBusqueda({ inicial, autoFocus }: { inicial: string; autoFocus?: boolean }) {
  const [q, setQ] = useState(inicial);
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    const t = q.trim();
    if (t.length >= 2) navegar("/m/buscar/" + encodeURIComponent(t));
  };
  return (
    <form className="m-busqueda" onSubmit={enviar} role="search">
      <input
        type="search"
        enterKeyHint="search"
        autoFocus={autoFocus}
        placeholder="DNI, apellido o N° de legajo"
        aria-label="Buscar"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <button aria-label="Buscar">⌕</button>
      <button
        type="button"
        className="m-busqueda-teclado"
        aria-label="Usar teclado numérico"
        title="Teclado numérico"
        onClick={(e) => {
          const input = (e.currentTarget.parentElement as HTMLFormElement).querySelector("input")!;
          input.inputMode = input.inputMode === "numeric" ? "search" : "numeric";
          input.blur();
          setTimeout(() => input.focus(), 50);
        }}
      >
        123
      </button>
    </form>
  );
}

interface Resultado {
  personas: PersonaResumen[];
  casos: Caso[];
}

function BuscarMovil({ q }: { q: string }) {
  const { puede } = useSesion();
  const { datos, error } = useDatos(
    () => (q.length >= 2 ? api.get<Resultado>("/buscar", { q }) : Promise.resolve(null)),
    [q],
  );
  const dni = q.replace(/\D/g, "");
  const pareceDni = dni.length >= 6 && dni.length === q.replace(/[.\s]/g, "").length;
  return (
    <>
      <CajaBusqueda inicial={q} autoFocus={!q} />
      {error && <Aviso error={error} />}
      {q && !datos && !error && <Cargando />}
      {datos && (
        <>
          {datos.personas.length + datos.casos.length === 0 && <p className="m-tenue">No hay coincidencias para «{q}».</p>}
          {datos.personas.map((p) => (
            <Tarjeta key={p.id} a={`/m/legajo/${p.id}`}>
              <FichaPersona p={p} />
            </Tarjeta>
          ))}
          {datos.casos.map((c) => (
            <Tarjeta key={c.id} a={`/m/caso/${c.id}`}>
              <FichaCaso c={c} conPersona />
            </Tarjeta>
          ))}
          {puede("personas", "crear") && puede("casos", "crear") && datos.personas.length === 0 && (
            <Accion a={`/m/nuevo${pareceDni ? "?dni=" + dni : ""}`} icono="＋" principal>
              {pareceDni ? `Nuevo legajo con DNI ${Number(dni).toLocaleString("es-AR")}` : "Nuevo legajo y caso"}
            </Accion>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- legajo

function LegajoMovil({ id }: { id: string }) {
  const { puede } = useSesion();
  const { datos: l, error, recargar } = useDatos(() => api.get<Legajo>(`/personas/${id}`), [id]);
  if (error) return <Aviso error={error} />;
  if (!l) return <Cargando />;
  const anio = new Date().getFullYear();
  const delAnio = l.casos.find((c) => c.caratula?.anio_actuacion === anio);
  const vinculados = l.vinculados.filter((v) => v.activo && v.telefono);
  return (
    <>
      <Tarjeta className="m-cabecera">
        <FichaPersona p={l} />
        <span className="m-detalle">Legajo N° {l.numero_legajo}</span>
        {l.domicilio && <span className="m-detalle">{[l.domicilio, l.localidad, l.departamento].filter(Boolean).join(", ")}</span>}
      </Tarjeta>
      <Llamar telefono={l.telefono} />
      {vinculados.map((v) => (
        <Llamar key={v.id} telefono={v.telefono} quien={`${v.nombres ?? v.nombre_institucion ?? ""} (${v.tipo_vinculo.nombre.toLowerCase()})`} />
      ))}

      <div className="m-acciones">
        {l.permisos.crear_caso &&
          (delAnio ? (
            <Accion a={`/m/caso/${delAnio.id}/reiteracion`} icono="↻" principal>
              Nueva demanda (reiteración de la actuación {delAnio.caratula.numero_actuacion}/{anio})
            </Accion>
          ) : (
            <Accion a={`/m/legajo/${id}/caratula`} icono="＋" principal>
              Nueva carátula ({anio})
            </Accion>
          ))}
        {l.permisos.cargar_documento && (
          <Accion a={`/m/legajo/${id}/fotos`} icono="◉">
            Sacar fotos de documentos
          </Accion>
        )}
        {l.permisos.modificar && (
          <Accion a={`/m/legajo/${id}/editar`} icono="✎">
            Editar datos personales
          </Accion>
        )}
        {l.permisos.modificar && (
          <Accion a={`/m/legajo/${id}/vinculado`} icono="＋">
            Agregar persona o institución vinculada
          </Accion>
        )}
        {l.permisos.crear_expediente && (
          <Accion a={`/m/legajo/${id}/expediente`} icono="▤">
            Vincular expediente
          </Accion>
        )}
      </div>

      {l.vinculados.length > 0 && (
        <>
          <h2 className="m-subtitulo">Vinculados</h2>
          {l.vinculados.map((v) => (
            <Tarjeta key={v.id} a={l.permisos.modificar ? `/m/legajo/${id}/vinculado?editar=${v.id}` : undefined} className={v.activo ? "" : "m-inactivo"}>
              <strong>
                {v.es_institucion ? v.nombre_institucion : `${(v.apellidos ?? "").toUpperCase()}, ${v.nombres ?? ""}`}
              </strong>
              <span className="m-detalle">
                {v.tipo_vinculo.nombre}
                {!v.activo && " (inactivo)"}
                {v.telefono && ` · ${v.telefono}`}
              </span>
              {l.permisos.modificar && <span className="m-detalle m-enlace">Tocar para editar</span>}
            </Tarjeta>
          ))}
        </>
      )}

      <h2 className="m-subtitulo">Ubicación del domicilio</h2>
      <UbicacionDomicilio persona={l} puedeModificar={l.permisos.modificar} alCambiar={recargar} />

      {puede("casos", "consultar") && (
        <>
          <h2 className="m-subtitulo">Casos</h2>
          {l.casos.length === 0 && <p className="m-tenue">Sin casos.</p>}
          {l.casos.map((c) => (
            <Tarjeta key={c.id} a={`/m/caso/${c.id}`}>
              <FichaCaso c={c} />
            </Tarjeta>
          ))}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- caso

interface CasoDetalle extends Caso {
  persona: Legajo;
  evoluciones: { id: number; texto: string; fecha: string; autor: { nombre_completo: string } | null }[];
  demandas: { id: string; fecha: string; escaneos: string[] }[];
  documentos: { id: string; titulo?: string; cargado_en: string; tipo_documental: { nombre: string } }[];
  reiteraciones: { id: number; fecha: string }[];
  permisos: { modificar: boolean; derivar: boolean };
}

function CasoMovil({ id }: { id: string }) {
  const { formularios: f, puede } = useSesion();
  const { datos: c, error } = useDatos(() => api.get<CasoDetalle>(`/casos/${id}`), [id]);
  const [todas, setTodas] = useState(false);
  if (error) return <Aviso error={error} />;
  if (!c) return <Cargando />;
  const car = c.caratula;
  const evol = [...c.evoluciones].reverse();
  const visibles = todas ? evol : evol.slice(0, 3);
  const indicadores = textoLista(f.indicadores, car.indicadores);
  const sinEscaneo = c.demandas.filter((d) => d.escaneos.length === 0);
  return (
    <>
      <Tarjeta className="m-cabecera">
        <FichaCaso c={c} />
        <a className="m-nombre m-enlace" href={`#/m/legajo/${c.persona.id}`}>
          {nombre(c.persona)}
        </a>
        <span className="m-detalle">
          {documento(c.persona)}
          {c.persona.fecha_nacimiento && ` · ${edad(c.persona.fecha_nacimiento)} años`}
        </span>
        {car.fecha_ingreso && <span className="m-detalle">Ingreso: {fecha(car.fecha_ingreso)}</span>}
        {c.reiteraciones.length > 0 && (
          <span className="m-detalle">
            Reiteraciones: {c.reiteraciones.map((r) => fecha(r.fecha)).join(", ")}
          </span>
        )}
      </Tarjeta>

      {indicadores && (
        <p className="m-indicadores">
          <strong>Indicadores:</strong> {indicadores}
        </p>
      )}
      {c.motivo && <p className="m-motivo">{c.motivo}</p>}
      <Llamar telefono={c.persona.telefono} />

      <div className="m-acciones">
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/evolucion`} icono="✎" principal>
            Agregar evolución
          </Accion>
        )}
        {puede("documentos", "crear") && (
          <Accion a={`/m/caso/${id}/fotos`} icono="◉">
            Sacar fotos
          </Accion>
        )}
        {c.permisos.modificar && sinEscaneo.length > 0 && puede("documentos", "crear") && (
          <Accion a={`/m/caso/${id}/fotos?demanda=${sinEscaneo[0].id}`} icono="▤">
            Fotografiar registro de demanda del {fecha(sinEscaneo[0].fecha)}
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/demanda`} icono="▦">
            {c.demandas.length ? "Nuevo registro de demanda" : "Cargar registro de demanda"}
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/articulacion`} icono="⇄">
            Registrar articulación con otra institución
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/reiteracion`} icono="↻">
            Registrar reiteración
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/estado`} icono="◐">
            Cambiar estado
          </Accion>
        )}
        {c.permisos.derivar && (
          <Accion a={`/m/caso/${id}/asignar`} icono="⇢">
            Asignar / derivar
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/caratula`} icono="▭">
            Editar carátula
          </Accion>
        )}
        {c.permisos.modificar && (
          <Accion a={`/m/caso/${id}/editar`} icono="✎">
            Editar datos del caso
          </Accion>
        )}
      </div>

      <>
          <h2 className="m-subtitulo">Evolución</h2>
          {evol.length === 0 && <p className="m-tenue">Sin registros todavía.</p>}
          <ol className="m-evolucion">
            {visibles.map((x) => (
              <li key={x.id}>
                <span className="m-detalle">
                  {fecha(x.fecha)} · {x.autor?.nombre_completo ?? "—"}
                </span>
                <p>{x.texto}</p>
              </li>
            ))}
          </ol>
          {evol.length > 3 && !todas && (
            <button className="m-boton-texto" onClick={() => setTodas(true)}>
              Ver las {evol.length} entradas
            </button>
          )}
          {c.demandas.length > 0 && (
            <>
              <h2 className="m-subtitulo">Registros de demanda</h2>
              {c.demandas.map((d) => (
                <Tarjeta key={d.id} a={c.permisos.modificar ? `/m/caso/${id}/demanda?editar=${d.id}` : undefined}>
                  <strong>Registro del {fecha(d.fecha)}</strong>
                  <span className="m-detalle">
                    {d.escaneos.length ? "Con escaneo" : "Sin escaneo"}
                    {c.permisos.modificar && " · tocar para editar"}
                  </span>
                </Tarjeta>
              ))}
            </>
          )}
          <ArticulacionesMovil casoId={id} />
          {c.documentos.length > 0 && (
            <>
              <h2 className="m-subtitulo">Documentos</h2>
              {c.documentos.slice(0, 8).map((d) => (
                <Tarjeta key={d.id}>
                  <strong>{d.titulo ?? d.tipo_documental.nombre}</strong>
                  <span className="m-detalle">
                    {d.tipo_documental.nombre} · {fecha(d.cargado_en)}
                  </span>
                </Tarjeta>
              ))}
            </>
          )}
      </>
    </>
  );
}

function ArticulacionesMovil({ casoId }: { casoId: string }) {
  const { datos } = useDatos(() => api.get<Articulacion[]>(`/casos/${casoId}/articulaciones`), [casoId]);
  if (!datos || datos.length === 0) return null;
  return (
    <>
      <h2 className="m-subtitulo">Articulaciones</h2>
      {datos.map((a) => (
        <Tarjeta key={a.id}>
          <strong>{a.contacto?.nombre ?? a.recurso?.nombre ?? "—"}</strong>
          <span className="m-detalle">
            {fecha(a.fecha)}
            {a.contacto?.institucion && ` · ${a.contacto.institucion}`}
          </span>
          {a.motivo && <span className="m-detalle">{a.motivo}</span>}
          {a.resultado && <span className="m-detalle">Resultado: {a.resultado}</span>}
          {a.contacto && <Llamar telefono={a.contacto.telefono} />}
        </Tarjeta>
      ))}
    </>
  );
}

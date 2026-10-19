import { PaginaPases, usePasesPendientes } from "./paginas/archivo";
import { PaginaNovedades, usePendientes } from "./paginas/novedades";
import { PaginaPersonal } from "./paginas/personal";
import { PaginaEstadisticas } from "./paginas/estadisticas";
import { PaginaBandeja } from "./paginas/bandeja";
import { PaginaAgenda } from "./paginas/agenda";
import { PaginaParticipacion } from "./paginas/participacion";
import { PaginaBuscarDocumentos } from "./paginas/textos";
import { BotonAvisos, useNotificaciones } from "./notificaciones";
import { PaginaMiAsistencia, usePendientesPersonal } from "./paginas/miasistencia";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api, configurarSesion, type Catalogos, type Formularios, type Yo } from "./api";
import { Aviso, Cargando, Campo, Enlace, SesionCtx, esCelular, navegar, rutaActual, useEnvio, useRuta } from "./comun";
import { Movil } from "./movil/movil";
import { PaginaAdmin } from "./paginas/admin";
import { PaginaAuditoria } from "./paginas/auditoria";
import { PaginaBuscar } from "./paginas/buscar";
import { PaginaCaso, PaginaCasos } from "./paginas/casos";
import { PaginaExpedientes } from "./paginas/expedientes";
import { PaginaFichas } from "./paginas/fichas";
import { PaginaColaImpresion } from "./paginas/cola";
import { PaginaRecurso, PaginaRecursos } from "./paginas/recursos";
import { PaginaResidencias } from "./paginas/residencias";
import { PaginaAntecedentes } from "./paginas/antecedentes";
import { InsigniaChat, PaginaChat } from "./paginas/chat";
import { PaginaSubsidio, PaginaSubsidios } from "./paginas/subsidios";
import { PaginaContactos } from "./paginas/contactos";
import { PaginaInforme } from "./paginas/informes";
import { PaginaPlantillas } from "./paginas/plantillas";
import { PaginaVisitas } from "./paginas/visitas";
import { PaginaLegajo } from "./paginas/legajo";
import { PaginaLegajos } from "./paginas/legajos";
import { PaginaIngreso, PaginaMesa } from "./paginas/mesa";
import { PaginaTablero } from "./paginas/tablero";
import { Impresion } from "./paginas/impresion";

export function App() {
  const [yo, setYo] = useState<Yo | null>(null);
  const [cargando, setCargando] = useState(true);
  // Sesión vencida con la pantalla abierta: se pide la contraseña encima, sin
  // desmontar la página, para no perder lo que se estaba escribiendo.
  const [vencida, setVencida] = useState(false);

  const salir = useCallback(() => {
    setVencida(false);
    setYo(null);
  }, []);


  const actual = useRef<string | null>(null);
  const entrar = useCallback((y: Yo) => {
    configurarSesion(y.csrf_token, () => setVencida(true));
    // Si al reingresar entra otra persona, no se le muestra la pantalla de la anterior.
    if (actual.current && actual.current !== y.id) navegar(esCelular() ? "/m" : "/");
    actual.current = y.id;
    setVencida(false);
    setYo(y);
  }, []);

  useEffect(() => {
    api
      .get<Yo>("/auth/me")
      .then(entrar)
      .catch(() => setYo(null))
      .finally(() => setCargando(false));
  }, [entrar]);

  if (cargando) return <Cargando />;
  if (!yo)
    return (
      <Login
        alEntrar={(y) => {
          entrar(y);
          const r = rutaActual();
          if (esCelular() && !r.startsWith("/m") && !r.startsWith("/imprimir/") && !r.startsWith("/c/")) navegar("/m");
        }}
      />
    );
  if (yo.debe_cambiar_password) return <CambioPassword yo={yo} alCambiar={entrar} obligatorio />;
  return (
    <>
      <Principal key={yo.id} yo={yo} alSalir={salir} alActualizar={entrar} />
      {vencida && (
        <div className="modal-fondo modal-fondo-sesion">
          <Login alEntrar={entrar} usuarioInicial={yo.usuario} vencida />
        </div>
      )}
    </>
  );
}

function Login({
  alEntrar,
  usuarioInicial = "",
  vencida,
}: {
  alEntrar: (y: Yo) => void;
  usuarioInicial?: string;
  vencida?: boolean;
}) {
  const [usuario, setUsuario] = useState(usuarioInicial);
  const [password, setPassword] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const dispositivo = esCelular() ? "movil" : "escritorio";
    const y = await ejecutar(() => api.post<Yo>("/auth/login", { usuario, password, dispositivo }));
    if (y) alEntrar(y);
  };

  const formulario = (
      <form className="tarjeta-acceso" onSubmit={enviar}>
        {vencida ? (
          <>
            <h1>La sesión se cerró</h1>
            <p>
              Pasó un tiempo sin uso y SULAM cerró la sesión por seguridad. Ingrese su contraseña para seguir: lo que
              estaba cargando sigue en pantalla.
            </p>
          </>
        ) : (
          <div className="marca-acceso">
            <span className="marca-sigla">SULAM</span>
            <span className="marca-texto">Sistema Único de Legajos de Adultos Mayores</span>
            <span className="marca-org">Dirección de Adultos Mayores · Tucumán</span>
          </div>
        )}
        <Campo etiqueta="Usuario">
          <input autoFocus={!vencida} autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="username" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        </Campo>
        <Campo etiqueta="Contraseña">
          <input
            type="password"
            autoFocus={vencida}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Campo>
        <Aviso error={error} />
        <button className="boton boton-primario boton-bloque" disabled={enviando}>
          {enviando ? "Ingresando…" : vencida ? "Seguir" : "Ingresar"}
        </button>
      </form>
  );
  return vencida ? formulario : <main className="pantalla-acceso">{formulario}</main>;
}

export function CambioPassword({
  yo,
  alCambiar,
  obligatorio,
  alCancelar,
}: {
  yo: Yo;
  alCambiar: (y: Yo) => void;
  obligatorio?: boolean;
  alCancelar?: () => void;
}) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const { enviando, error, setError, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (nueva !== repetida) {
      setError("Las contraseñas nuevas no coinciden.");
      return;
    }
    const y = await ejecutar(() =>
      api.post<Yo>("/auth/password", { password_actual: actual, password_nueva: nueva }),
    );
    if (y) alCambiar(y);
  };

  const formulario = (
    <form className="tarjeta-acceso" onSubmit={enviar}>
      <h1>Cambiar contraseña</h1>
      {obligatorio && (
        <p>
          Hola, {yo.nombre_completo}. Antes de continuar debe elegir una contraseña personal de al menos 10
          caracteres que combine letras con números o símbolos.
        </p>
      )}
      <Campo etiqueta="Contraseña actual">
        <input type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} required />
      </Campo>
      <Campo etiqueta="Nueva contraseña">
        <input type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} required />
      </Campo>
      <Campo etiqueta="Repetir nueva contraseña">
        <input type="password" autoComplete="new-password" value={repetida} onChange={(e) => setRepetida(e.target.value)} required />
      </Campo>
      <Aviso error={error} />
      <div className="fila-botones">
        {alCancelar && (
          <button type="button" className="boton" onClick={alCancelar}>
            Cancelar
          </button>
        )}
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
  return obligatorio ? <main className="pantalla-acceso">{formulario}</main> : formulario;
}

interface ItemMenu {
  ruta: string;
  texto: string;
  permiso?: [string, string];
}

/** El menú lateral muestra una entrada por grupo; las pantallas del grupo se ven como solapas arriba del contenido. */
const GRUPOS: { texto: string; miembros: ItemMenu[] }[] = [
  { texto: "Tablero", miembros: [{ ruta: "/", texto: "Tablero" }] },
  { texto: "Novedades", miembros: [{ ruta: "/novedades", texto: "Novedades" }] },
  {
    texto: "Legajos y casos",
    miembros: [
      { ruta: "/legajos", texto: "Legajos", permiso: ["personas", "consultar"] },
      { ruta: "/casos", texto: "Casos", permiso: ["casos", "consultar"] },
      { ruta: "/imprimir-caratulas", texto: "Imprimir carátulas", permiso: ["casos", "consultar"] },
    ],
  },
  {
    texto: "Mesa y expedientes",
    miembros: [
      { ruta: "/mesa", texto: "Mesa de Entrada", permiso: ["mesa_entrada", "consultar"] },
      { ruta: "/expedientes", texto: "Expedientes", permiso: ["expedientes", "consultar"] },
      { ruta: "/pases", texto: "Pases de carpetas" },
    ],
  },
  {
    texto: "Agenda y salidas",
    miembros: [
      { ruta: "/agenda", texto: "Agenda", permiso: ["agenda", "consultar"] },
      { ruta: "/visitas", texto: "Mapa de casos y salidas", permiso: ["casos", "consultar"] },
    ],
  },
  { texto: "Chat", miembros: [{ ruta: "/chat", texto: "Chat", permiso: ["chat", "usar"] }] },
  { texto: "Antecedentes", miembros: [{ ruta: "/antecedentes", texto: "Antecedentes", permiso: ["antecedentes", "consultar"] }] },
  { texto: "Subsidios", miembros: [{ ruta: "/subsidios", texto: "Subsidios", permiso: ["subsidios", "consultar"] }] },
  { texto: "Participación y Sensibilización", miembros: [{ ruta: "/participacion", texto: "Participación y Sensibilización", permiso: ["participacion", "consultar"] }] },
  {
    texto: "Documentos",
    miembros: [
      { ruta: "/bandeja", texto: "Digitalización", permiso: ["documentos", "crear"] },
      { ruta: "/buscar-documentos", texto: "Buscar en documentos", permiso: ["documentos", "consultar"] },
      { ruta: "/fichas", texto: "Fichas en papel" },
    ],
  },
  {
    texto: "Red de recursos",
    miembros: [
      { ruta: "/recursos", texto: "Recursos y mapa", permiso: ["recursos", "consultar"] },
      { ruta: "/residencias", texto: "Residencias e internaciones", permiso: ["residencias", "consultar"] },
      { ruta: "/contactos", texto: "Contactos", permiso: ["recursos", "consultar"] },
    ],
  },
  {
    texto: "Personal y asistencia",
    miembros: [
      { ruta: "/personal", texto: "Personal", permiso: ["personal", "consultar"] },
      { ruta: "/mi-asistencia", texto: "Mi asistencia" },
    ],
  },
  { texto: "Estadísticas", miembros: [{ ruta: "/estadisticas", texto: "Estadísticas", permiso: ["estadisticas", "consultar"] }] },
  {
    texto: "Administración",
    miembros: [
      { ruta: "/admin", texto: "Administración", permiso: ["administracion", "administrar"] },
      { ruta: "/plantillas", texto: "Plantillas de informes", permiso: ["plantillas", "modificar"] },
      { ruta: "/auditoria", texto: "Auditoría", permiso: ["auditoria", "consultar"] },
    ],
  },
];

function Insignia({ ruta, de }: { ruta: string; de: string }) {
  if (de === "/novedades") return <InsigniaNovedades ruta={ruta} />;
  if (de === "/chat") return <InsigniaChat ruta={ruta} />;
  if (de === "/pases") return <InsigniaPases ruta={ruta} />;
  if (de === "/mi-asistencia") return <InsigniaPersonal ruta={ruta} cual="para_aprobar" />;
  if (de === "/personal") return <InsigniaPersonal ruta={ruta} cual="para_registrar" />;
  return null;
}

function Principal({ yo, alSalir, alActualizar }: { yo: Yo; alSalir: () => void; alActualizar: (y: Yo) => void }) {
  const ruta = useRuta();
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [formularios, setFormularios] = useState<Formularios | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busqueda, setBusqueda] = useState("");
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [cambiarPw, setCambiarPw] = useState(false);
  const avisos = useNotificaciones(yo);

  const recargarCatalogos = useCallback(() => {
    api.get<Catalogos>("/catalogos").then(setCatalogos).catch(setError);
  }, []);
  useEffect(recargarCatalogos, [recargarCatalogos]);
  useEffect(() => {
    api.get<Formularios>("/formularios").then(setFormularios).catch(setError);
  }, []);
  useEffect(() => setMenuAbierto(false), [ruta]);

  const puede = useCallback((m: string, a: string) => `${m}.${a}` in yo.permisos, [yo]);

  const salir = async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      alSalir();
      navegar("/");
    }
  };

  if (error) return <Aviso error={error} />;
  if (!catalogos || !formularios) return <Cargando />;

  const buscar = (e: FormEvent) => {
    e.preventDefault();
    if (busqueda.trim().length >= 2) navegar("/buscar/" + encodeURIComponent(busqueda.trim()));
  };

  const seccion = "/" + (ruta.split("?")[0].split("/")[1] ?? "");
  // Grupos del menú con lo que el rol permite ver; la pantalla actual pertenece a uno de ellos (o a ninguno).
  const visible = (m: ItemMenu) => !m.permiso || puede(...m.permiso) || (m.ruta === "/estadisticas" && puede("personal", "consultar"));
  const grupos = GRUPOS.map((g) => ({ ...g, miembros: g.miembros.filter(visible) })).filter((g) => g.miembros.length > 0);
  const grupo = grupos.find((g) => g.miembros.some((m) => m.ruta === seccion)) ?? null;

  // Enlace del QR de la carátula: abre el caso en la versión que corresponde al dispositivo.
  if (ruta.startsWith("/c/")) {
    const id = ruta.split("/")[2] ?? "";
    location.replace("#" + (esCelular() ? `/m/caso/${id}` : `/casos/${id}`));
    return <Cargando />;
  }

  const cambioPw = cambiarPw && (
    <div className="modal-fondo">
      <CambioPassword
        yo={yo}
        alCambiar={(y) => {
          alActualizar(y);
          setCambiarPw(false);
        }}
        alCancelar={() => setCambiarPw(false)}
      />
    </div>
  );

  return (
    <SesionCtx.Provider value={{ yo, catalogos, formularios, puede, recargarCatalogos }}>
      {ruta.startsWith("/imprimir/") ? (
        <Impresion ruta={ruta} />
      ) : ruta === "/m" || ruta.startsWith("/m/") ? (
        <>
          <Movil avisos={avisos} ruta={ruta} alSalir={salir} alCambiarPassword={() => setCambiarPw(true)} />
          {cambioPw}
        </>
      ) : (
      <>
      <a className="saltar" href="#contenido" onClick={(e) => { e.preventDefault(); document.getElementById("contenido")?.focus(); }}>
        Ir al contenido
      </a>
      <header className="barra">
        <button className="boton-menu" onClick={() => setMenuAbierto(!menuAbierto)} aria-label="Menú" aria-expanded={menuAbierto}>
          ☰
        </button>
        <Enlace a="/" className="barra-marca">
          SULAM
        </Enlace>
        <form className="barra-busqueda" onSubmit={buscar} role="search">
          <input
            type="search"
            placeholder="Buscar por apellido, DNI, N° de legajo, caso o expediente"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            aria-label="Buscar"
          />
        </form>
        <div className="barra-usuario">
          <span className="barra-nombre">
            {yo.nombre_completo}
            <small>{yo.roles.join(" · ") || "Sin rol"}</small>
          </span>
          <BotonAvisos avisos={avisos} />
          <button className="boton boton-chico" onClick={() => setCambiarPw(true)}>
            Contraseña
          </button>
          <button className="boton boton-chico" onClick={salir}>
            Salir
          </button>
        </div>
      </header>
      <div className="cuerpo">
        <nav className={`menu ${menuAbierto ? "abierto" : ""}`} aria-label="Secciones">
          {grupos.map((g) => (
            <Enlace key={g.texto} a={g.miembros[0].ruta} className={grupo === g ? "activo" : ""}>
              {g.texto}
              <span className="menu-insignias">
                {g.miembros.map((m) => (
                  <Insignia key={m.ruta} ruta={ruta} de={m.ruta} />
                ))}
              </span>
            </Enlace>
          ))}
          <Enlace a="/m" className="menu-celular">
            Versión para celular
          </Enlace>
          <div className="menu-pie">
            Versión 0.1 · Datos de prueba
          </div>
        </nav>
        <main id="contenido" tabIndex={-1} className="contenido">
          {grupo && grupo.miembros.length > 1 && (
            <nav className="subnav" aria-label={grupo.texto}>
              {grupo.miembros.map((m) => (
                <Enlace key={m.ruta} a={m.ruta} className={seccion === m.ruta ? "activo" : ""}>
                  {m.texto}
                  <Insignia ruta={ruta} de={m.ruta} />
                </Enlace>
              ))}
            </nav>
          )}
          <Rutas ruta={ruta} />
        </main>
      </div>
      {cambioPw}
      </>
      )}
    </SesionCtx.Provider>
  );
}

function Rutas({ ruta }: { ruta: string }) {
  const p = ruta.split("?")[0].split("/").filter(Boolean);
  switch (p[0]) {
    case undefined:
      return <PaginaTablero />;
    case "legajos":
      return p[1] ? <PaginaLegajo id={p[1]} key={p[1]} /> : <PaginaLegajos />;
    case "casos":
      return p[1] ? <PaginaCaso id={p[1]} key={p[1]} /> : <PaginaCasos />;
    case "mesa":
      return p[1] ? <PaginaIngreso id={p[1]} key={p[1]} /> : <PaginaMesa />;
    case "expedientes":
      return <PaginaExpedientes />;
    case "visitas":
      return <PaginaVisitas />;
    case "contactos":
      return <PaginaContactos />;
    case "informes":
      return <PaginaInforme id={p[1]} key={p[1]} />;
    case "plantillas":
      return <PaginaPlantillas />;
    case "novedades":
      return <PaginaNovedades />;
    case "pases":
      return <PaginaPases />;
    case "personal":
      return <PaginaPersonal />;
    case "estadisticas":
      return <PaginaEstadisticas />;
    case "mi-asistencia":
      return <PaginaMiAsistencia />;
    case "bandeja":
      return <PaginaBandeja />;
    case "agenda":
      return <PaginaAgenda />;
    case "participacion":
      return <PaginaParticipacion />;
    case "buscar-documentos":
      return <PaginaBuscarDocumentos />;
    case "subsidios":
      return p[1] ? <PaginaSubsidio id={p[1]} key={p[1]} /> : <PaginaSubsidios />;
    case "residencias":
      return <PaginaResidencias />;
    case "antecedentes":
      return <PaginaAntecedentes />;
    case "chat":
      return <PaginaChat id={p[1]} key={p[1] ?? "lista"} />;
    case "recursos":
      return p[1] ? <PaginaRecurso id={p[1]} key={p[1]} /> : <PaginaRecursos />;
    case "imprimir-caratulas":
      return <PaginaColaImpresion />;
    case "fichas":
      return <PaginaFichas />;
    case "buscar":
      return <PaginaBuscar q={decodeURIComponent(p[1] ?? "")} key={p[1]} />;
    case "auditoria":
      return <PaginaAuditoria />;
    case "admin":
      return <PaginaAdmin pestaña={p[1] ?? "usuarios"} />;
    default:
      return <Aviso error={new ApiError(404, "Página inexistente.")} />;
  }
}

/** Cantidad de novedades sin confirmar, junto al menú. Se actualiza al navegar. */
function InsigniaNovedades({ ruta }: { ruta: string }) {
  const { datos, recargar } = usePendientes();
  useEffect(() => {
    recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta]);
  if (!datos || datos.cantidad === 0) return null;
  return (
    <span className="insignia" aria-label={`${datos.cantidad} sin confirmar`}>
      {datos.cantidad}
    </span>
  );
}

function InsigniaPases({ ruta }: { ruta: string }) {
  const { datos, recargar } = usePasesPendientes();
  useEffect(() => {
    recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta]);
  if (!datos || datos.cantidad === 0) return null;
  return (
    <span className="insignia" aria-label={`${datos.cantidad} pases pendientes`}>
      {datos.cantidad}
    </span>
  );
}

function InsigniaPersonal({ ruta, cual }: { ruta: string; cual: "para_aprobar" | "para_registrar" }) {
  const { datos, recargar } = usePendientesPersonal();
  useEffect(() => {
    recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta]);
  const n = datos?.[cual] ?? 0;
  if (!n) return null;
  return (
    <span className="insignia" aria-label={`${n} pedidos ${cual === "para_aprobar" ? "para aprobar" : "para registrar"}`}>
      {n}
    </span>
  );
}

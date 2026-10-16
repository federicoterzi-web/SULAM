import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, api, configurarSesion, type Catalogos, type Yo } from "./api";
import { Aviso, Cargando, Campo, Enlace, SesionCtx, navegar, useEnvio, useRuta } from "./comun";
import { PaginaAdmin } from "./paginas/admin";
import { PaginaAuditoria } from "./paginas/auditoria";
import { PaginaBuscar } from "./paginas/buscar";
import { PaginaCaso, PaginaCasos } from "./paginas/casos";
import { PaginaExpedientes } from "./paginas/expedientes";
import { PaginaLegajo } from "./paginas/legajo";
import { PaginaLegajos } from "./paginas/legajos";
import { PaginaIngreso, PaginaMesa } from "./paginas/mesa";
import { PaginaTablero } from "./paginas/tablero";

export function App() {
  const [yo, setYo] = useState<Yo | null>(null);
  const [cargando, setCargando] = useState(true);

  const salir = useCallback(() => {
    setYo(null);
  }, []);

  const entrar = useCallback(
    (y: Yo) => {
      configurarSesion(y.csrf_token, salir);
      setYo(y);
    },
    [salir],
  );

  useEffect(() => {
    api
      .get<Yo>("/auth/me")
      .then(entrar)
      .catch(() => setYo(null))
      .finally(() => setCargando(false));
  }, [entrar]);

  if (cargando) return <Cargando />;
  if (!yo) return <Login alEntrar={entrar} />;
  if (yo.debe_cambiar_password) return <CambioPassword yo={yo} alCambiar={entrar} obligatorio />;
  return <Principal yo={yo} alSalir={salir} alActualizar={entrar} />;
}

function Login({ alEntrar }: { alEntrar: (y: Yo) => void }) {
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const { enviando, error, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const y = await ejecutar(() => api.post<Yo>("/auth/login", { usuario, password }));
    if (y) alEntrar(y);
  };

  return (
    <main className="pantalla-acceso">
      <form className="tarjeta-acceso" onSubmit={enviar}>
        <div className="marca-acceso">
          <span className="marca-sigla">SULAM</span>
          <span className="marca-texto">Sistema Único de Legajos de Adultos Mayores</span>
          <span className="marca-org">Dirección de Adultos Mayores · Tucumán</span>
        </div>
        <Campo etiqueta="Usuario">
          <input autoFocus autoComplete="username" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        </Campo>
        <Campo etiqueta="Contraseña">
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Campo>
        <Aviso error={error} />
        <button className="boton boton-primario boton-bloque" disabled={enviando}>
          {enviando ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </main>
  );
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

const MENU: { ruta: string; texto: string; permiso?: [string, string] }[] = [
  { ruta: "/", texto: "Tablero" },
  { ruta: "/legajos", texto: "Legajos", permiso: ["personas", "consultar"] },
  { ruta: "/casos", texto: "Casos", permiso: ["casos", "consultar"] },
  { ruta: "/mesa", texto: "Mesa de Entrada", permiso: ["mesa_entrada", "consultar"] },
  { ruta: "/expedientes", texto: "Expedientes", permiso: ["expedientes", "consultar"] },
  { ruta: "/auditoria", texto: "Auditoría", permiso: ["auditoria", "consultar"] },
  { ruta: "/admin", texto: "Administración", permiso: ["administracion", "administrar"] },
];

function Principal({ yo, alSalir, alActualizar }: { yo: Yo; alSalir: () => void; alActualizar: (y: Yo) => void }) {
  const ruta = useRuta();
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busqueda, setBusqueda] = useState("");
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [cambiarPw, setCambiarPw] = useState(false);

  const recargarCatalogos = useCallback(() => {
    api.get<Catalogos>("/catalogos").then(setCatalogos).catch(setError);
  }, []);
  useEffect(recargarCatalogos, [recargarCatalogos]);
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
  if (!catalogos) return <Cargando />;

  const buscar = (e: FormEvent) => {
    e.preventDefault();
    if (busqueda.trim().length >= 2) navegar("/buscar/" + encodeURIComponent(busqueda.trim()));
  };

  const seccion = "/" + (ruta.split("?")[0].split("/")[1] ?? "");

  return (
    <SesionCtx.Provider value={{ yo, catalogos, puede, recargarCatalogos }}>
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
          {MENU.filter((m) => !m.permiso || puede(...m.permiso)).map((m) => (
            <Enlace key={m.ruta} a={m.ruta} className={seccion === m.ruta ? "activo" : ""}>
              {m.texto}
            </Enlace>
          ))}
          <div className="menu-pie">
            Versión 0.1 · Datos de prueba
          </div>
        </nav>
        <main id="contenido" tabIndex={-1} className="contenido">
          <Rutas ruta={ruta} />
        </main>
      </div>
      {cambiarPw && (
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

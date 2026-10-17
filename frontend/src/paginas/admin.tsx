import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Enlace, Modal, Seccion, fechaHora, useDatos, useEnvio, useSesion } from "../comun";

interface UsuarioAdmin {
  id: string;
  usuario: string;
  nombre_completo: string;
  email: string | null;
  area: { id: number; nombre: string } | null;
  roles: { id: number; nombre: string }[];
  activo: boolean;
  debe_cambiar_password: boolean;
  ultimo_acceso: string | null;
  bloqueado_hasta: string | null;
}

interface Permiso {
  modulo: string;
  accion: string;
  alcance: string;
}

interface RolAdmin {
  id: number;
  nombre: string;
  descripcion: string | null;
  activo: boolean;
  inicio: string | null;
  permisos: Permiso[];
}

const INICIOS: Record<string, string> = {
  direccion: "Dirección (resumen general)",
  jefatura: "Jefatura de departamento o división (su área y su equipo)",
  tecnico: "Técnico/a (sus casos por urgencia)",
  carga: "Carga de datos (lo que falta digitalizar)",
  mesa: "Mesa de Entrada (ingresos)",
  administrativo_area: "Administrativo de área",
};

interface CatalogoPermisos {
  modulos: { modulo: string; nombre: string; acciones: string[] }[];
  acciones: Record<string, string>;
  alcances: string[];
}

const ALCANCE_TEXTO: Record<string, string> = {
  propios: "Propios",
  asignados: "Asignados",
  area: "Su área",
  todos: "Todos",
};

export function PaginaAdmin({ pestaña }: { pestaña: string }) {
  return (
    <>
      <h1>Administración</h1>
      <nav className="pestañas" aria-label="Administración">
        <Enlace a="/admin/usuarios" className={pestaña === "usuarios" ? "activo" : ""}>
          Usuarios
        </Enlace>
        <Enlace a="/admin/roles" className={pestaña === "roles" ? "activo" : ""}>
          Roles y permisos
        </Enlace>
        <Enlace a="/admin/catalogos" className={pestaña === "catalogos" ? "activo" : ""}>
          Catálogos
        </Enlace>
      </nav>
      {pestaña === "roles" ? <Roles /> : pestaña === "catalogos" ? <Catalogos /> : <Usuarios />}
    </>
  );
}

// ---------------------------------------------------------------- usuarios

function Usuarios() {
  const { datos, error, recargar } = useDatos(() => api.get<UsuarioAdmin[]>("/admin/usuarios"), []);
  const roles = useDatos(() => api.get<RolAdmin[]>("/admin/roles"), []);
  const [editar, setEditar] = useState<UsuarioAdmin | "nuevo" | null>(null);
  const [reset, setReset] = useState<UsuarioAdmin | null>(null);
  const { recargarCatalogos } = useSesion();

  if (error) return <Aviso error={error} />;
  if (!datos || !roles.datos) return <Cargando />;
  const listo = () => {
    setEditar(null);
    setReset(null);
    recargar();
    recargarCatalogos();
  };

  return (
    <Seccion
      titulo="Usuarios"
      acciones={
        <button className="boton boton-primario" onClick={() => setEditar("nuevo")}>
          Nuevo usuario
        </button>
      }
    >
      <table className="tabla">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Nombre</th>
            <th>Área</th>
            <th>Roles</th>
            <th>Último acceso</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {datos.map((u) => (
            <tr key={u.id} className={u.activo ? "" : "fila-inactiva"}>
              <td>
                <code>{u.usuario}</code>
                {!u.activo && <small> (inactivo)</small>}
                {u.bloqueado_hasta && new Date(u.bloqueado_hasta) > new Date() && <span className="insignia bloqueado">Bloqueado</span>}
              </td>
              <td>{u.nombre_completo}</td>
              <td>{u.area?.nombre ?? "—"}</td>
              <td>{u.roles.map((r) => r.nombre).join(", ") || "—"}</td>
              <td>{u.debe_cambiar_password ? <span className="tenue">Pendiente de primer ingreso</span> : fechaHora(u.ultimo_acceso)}</td>
              <td className="acciones-fila">
                <button className="boton boton-chico" onClick={() => setEditar(u)}>
                  Editar
                </button>
                <button className="boton boton-chico" onClick={() => setReset(u)}>
                  Restablecer contraseña
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editar && (
        <Modal titulo={editar === "nuevo" ? "Nuevo usuario" : `Editar ${editar.usuario}`} alCerrar={() => setEditar(null)}>
          <FormUsuario usuario={editar === "nuevo" ? undefined : editar} roles={roles.datos} alGuardar={listo} />
        </Modal>
      )}
      {reset && (
        <Modal titulo={`Restablecer contraseña de ${reset.usuario}`} alCerrar={() => setReset(null)}>
          <FormReset usuario={reset} alGuardar={listo} />
        </Modal>
      )}
    </Seccion>
  );
}

function FormUsuario({ usuario, roles, alGuardar }: { usuario?: UsuarioAdmin; roles: RolAdmin[]; alGuardar: () => void }) {
  const { catalogos } = useSesion();
  const [d, setD] = useState({
    usuario: usuario?.usuario ?? "",
    nombre_completo: usuario?.nombre_completo ?? "",
    email: usuario?.email ?? "",
    area_id: String(usuario?.area?.id ?? ""),
    password_inicial: "",
    activo: usuario?.activo ?? true,
  });
  const [rolesSel, setRolesSel] = useState<Set<number>>(new Set(usuario?.roles.map((r) => r.id) ?? []));
  const { enviando, error, ejecutar } = useEnvio();
  const cambia = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const comun = {
      nombre_completo: d.nombre_completo,
      email: d.email || null,
      area_id: d.area_id ? Number(d.area_id) : null,
      roles: [...rolesSel],
    };
    const r = await ejecutar(() =>
      usuario
        ? api.patch(`/admin/usuarios/${usuario.id}`, { ...comun, activo: d.activo })
        : api.post("/admin/usuarios", { ...comun, usuario: d.usuario, password_inicial: d.password_inicial }),
    );
    if (r) alGuardar();
  };

  return (
    <form onSubmit={enviar} className="formulario">
      {!usuario && (
        <Campo etiqueta="Nombre de usuario *" ayuda="Letras, números, punto, guion. Ej.: maria.gomez">
          <input value={d.usuario} onChange={cambia("usuario")} required pattern="[a-zA-Z0-9._\-]{3,80}" autoFocus />
        </Campo>
      )}
      <Campo etiqueta="Nombre completo *">
        <input value={d.nombre_completo} onChange={cambia("nombre_completo")} required />
      </Campo>
      <Campo etiqueta="Correo electrónico">
        <input type="email" value={d.email} onChange={cambia("email")} />
      </Campo>
      <Campo etiqueta="Área">
        <select value={d.area_id} onChange={cambia("area_id")}>
          <option value="">Sin área</option>
          {catalogos.areas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <fieldset className="grupo-casillas">
        <legend>Roles</legend>
        {roles.map((r) => (
          <label key={r.id} className="casilla">
            <input
              type="checkbox"
              checked={rolesSel.has(r.id)}
              onChange={(e) => {
                const s = new Set(rolesSel);
                if (e.target.checked) s.add(r.id);
                else s.delete(r.id);
                setRolesSel(s);
              }}
            />
            {r.nombre} {!r.activo && <small>(inactivo)</small>}
          </label>
        ))}
      </fieldset>
      {usuario ? (
        <label className="casilla">
          <input type="checkbox" checked={d.activo} onChange={(e) => setD({ ...d, activo: e.target.checked })} />
          Usuario activo (al desactivarlo se cierran sus sesiones)
        </label>
      ) : (
        <Campo etiqueta="Contraseña inicial *" ayuda="Al menos 10 caracteres. La persona deberá cambiarla en su primer ingreso.">
          <input type="text" value={d.password_inicial} onChange={cambia("password_inicial")} required minLength={10} autoComplete="off" />
        </Campo>
      )}
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar
        </button>
      </div>
    </form>
  );
}

function FormReset({ usuario, alGuardar }: { usuario: UsuarioAdmin; alGuardar: () => void }) {
  const [pw, setPw] = useState("");
  const { enviando, error, ejecutar } = useEnvio();
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await ejecutar(() => api.post(`/admin/usuarios/${usuario.id}/password`, { password_temporal: pw }));
    if (r) alGuardar();
  };
  return (
    <form onSubmit={enviar} className="formulario">
      <p>Se cerrarán las sesiones abiertas de {usuario.nombre_completo} y deberá elegir una contraseña nueva al ingresar.</p>
      <Campo etiqueta="Contraseña temporal *">
        <input value={pw} onChange={(e) => setPw(e.target.value)} required minLength={10} autoComplete="off" autoFocus />
      </Campo>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Restablecer
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- roles

function Roles() {
  const { datos, error, recargar } = useDatos(() => api.get<RolAdmin[]>("/admin/roles"), []);
  const cat = useDatos(() => api.get<CatalogoPermisos>("/admin/permisos-catalogo"), []);
  const [editar, setEditar] = useState<RolAdmin | "nuevo" | null>(null);

  if (error || cat.error) return <Aviso error={error ?? cat.error} />;
  if (!datos || !cat.datos) return <Cargando />;

  return (
    <Seccion
      titulo="Roles"
      acciones={
        <button className="boton boton-primario" onClick={() => setEditar("nuevo")}>
          Nuevo rol
        </button>
      }
    >
      <p className="tenue">
        Los roles iniciales son una propuesta: la matriz definitiva de permisos se define institucionalmente. Cada
        cambio queda registrado en la auditoría con el antes y el después.
      </p>
      <div className="tarjetas">
        {datos.map((r) => (
          <article key={r.id} className={`tarjeta ${r.activo ? "" : "fila-inactiva"}`}>
            <h3>{r.nombre}</h3>
            <p className="tenue">{r.descripcion}</p>
            <p>
              {r.permisos.length} permisos · Inicio: {r.inicio ? INICIOS[r.inicio]?.split(" (")[0] ?? r.inicio : "general"}
            </p>
            <button className="boton boton-chico" onClick={() => setEditar(r)}>
              Ver y editar permisos
            </button>
          </article>
        ))}
      </div>
      {editar && (
        <Modal titulo={editar === "nuevo" ? "Nuevo rol" : editar.nombre} alCerrar={() => setEditar(null)} ancho>
          <FormRol
            rol={editar === "nuevo" ? undefined : editar}
            catalogo={cat.datos}
            alGuardar={() => {
              setEditar(null);
              recargar();
            }}
          />
        </Modal>
      )}
    </Seccion>
  );
}

function FormRol({ rol, catalogo, alGuardar }: { rol?: RolAdmin; catalogo: CatalogoPermisos; alGuardar: () => void }) {
  const [nombre, setNombre] = useState(rol?.nombre ?? "");
  const [descripcion, setDescripcion] = useState(rol?.descripcion ?? "");
  const [activo, setActivo] = useState(rol?.activo ?? true);
  const [inicio, setInicio] = useState(rol?.inicio ?? "");
  const [permisos, setPermisos] = useState<Record<string, string>>(
    Object.fromEntries((rol?.permisos ?? []).map((p) => [`${p.modulo}.${p.accion}`, p.alcance])),
  );
  const { enviando, error, ejecutar } = useEnvio();

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const lista = Object.entries(permisos)
      .filter(([, a]) => a)
      .map(([k, alcance]) => {
        const [modulo, accion] = k.split(".");
        return { modulo, accion, alcance };
      });
    const cuerpo = { nombre, descripcion: descripcion || null, activo, inicio: inicio || null, permisos: lista };
    const r = await ejecutar(() => (rol ? api.put(`/admin/roles/${rol.id}`, cuerpo) : api.post("/admin/roles", cuerpo)));
    if (r) alGuardar();
  };

  return (
    <form onSubmit={enviar} className="formulario">
      <div className="grilla">
        <Campo etiqueta="Nombre *">
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} required />
        </Campo>
        <label className="casilla">
          <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} />
          Rol activo
        </label>
        <Campo etiqueta="Descripción" ancho="completo">
          <input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
        </Campo>
        <Campo etiqueta="Página de inicio" ayuda="Lo que ve al entrar quien tiene este rol.">
          <select value={inicio} onChange={(e) => setInicio(e.target.value)}>
            <option value="">General</option>
            {Object.entries(INICIOS).map(([k, t]) => (
              <option key={k} value={k}>
                {t}
              </option>
            ))}
          </select>
        </Campo>
      </div>
      <p className="tenue">
        Alcance: <strong>Propios</strong> = lo que el usuario creó; <strong>Asignados</strong> = casos donde es
        responsable; <strong>Su área</strong> = casos del área del usuario; <strong>Todos</strong> = sin restricción.
      </p>
      <table className="tabla tabla-compacta matriz">
        <thead>
          <tr>
            <th>Módulo</th>
            <th>Acción</th>
            <th>Alcance</th>
          </tr>
        </thead>
        <tbody>
          {catalogo.modulos.flatMap((m) =>
            m.acciones.map((a, i) => {
              const k = `${m.modulo}.${a}`;
              return (
                <tr key={k}>
                  {i === 0 && <th rowSpan={m.acciones.length}>{m.nombre}</th>}
                  <td>{catalogo.acciones[a] ?? a}</td>
                  <td>
                    <select
                      value={permisos[k] ?? ""}
                      onChange={(e) => setPermisos({ ...permisos, [k]: e.target.value })}
                      aria-label={`${m.nombre}: ${a}`}
                    >
                      <option value="">Sin permiso</option>
                      {catalogo.alcances.map((al) => (
                        <option key={al} value={al}>
                          {ALCANCE_TEXTO[al] ?? al}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            }),
          )}
        </tbody>
      </table>
      <Aviso error={error} />
      <div className="fila-botones">
        <button className="boton boton-primario" disabled={enviando}>
          Guardar rol
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- catálogos

const CATALOGOS: { clave: string; titulo: string }[] = [
  { clave: "areas", titulo: "Áreas" },
  { clave: "tipos-documentales", titulo: "Tipos documentales" },
  { clave: "tipos-vinculo", titulo: "Tipos de vínculo" },
];

function Catalogos() {
  return (
    <>
      <Numeracion />
      {CATALOGOS.map((c) => (
        <Catalogo key={c.clave} {...c} />
      ))}
    </>
  );
}

interface Item {
  id: number;
  nombre: string;
  activo: boolean;
}

function Catalogo({ clave, titulo }: { clave: string; titulo: string }) {
  const { recargarCatalogos } = useSesion();
  const { datos, error, recargar } = useDatos(() => api.get<Item[]>(`/admin/catalogos/${clave}`), [clave]);
  const [nuevo, setNuevo] = useState("");
  const envio = useEnvio();

  const guardar = async (f: () => Promise<unknown>) => {
    const r = await envio.ejecutar(f);
    if (r) {
      recargar();
      recargarCatalogos();
    }
  };

  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  return (
    <Seccion titulo={titulo}>
      <table className="tabla tabla-compacta">
        <tbody>
          {datos.map((it) => (
            <tr key={it.id} className={it.activo ? "" : "fila-inactiva"}>
              <td>
                <input
                  defaultValue={it.nombre}
                  aria-label="Nombre"
                  onBlur={(e) =>
                    e.target.value !== it.nombre &&
                    guardar(() => api.patch(`/admin/catalogos/${clave}/${it.id}`, { nombre: e.target.value, activo: it.activo }))
                  }
                />
              </td>
              <td>
                <label className="casilla">
                  <input
                    type="checkbox"
                    checked={it.activo}
                    onChange={(e) =>
                      guardar(() => api.patch(`/admin/catalogos/${clave}/${it.id}`, { nombre: it.nombre, activo: e.target.checked }))
                    }
                  />
                  Activo
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form
        className="filtros"
        onSubmit={(e) => {
          e.preventDefault();
          if (nuevo.trim()) guardar(() => api.post(`/admin/catalogos/${clave}`, { nombre: nuevo.trim(), activo: true })).then(() => setNuevo(""));
        }}
      >
        <input value={nuevo} onChange={(e) => setNuevo(e.target.value)} placeholder="Agregar…" aria-label={`Agregar a ${titulo}`} />
        <button className="boton">Agregar</button>
      </form>
      <Aviso error={envio.error} />
    </Seccion>
  );
}

function Numeracion() {
  const [anio, setAnio] = useState(new Date().getFullYear());
  const { datos, error, recargar } = useDatos(
    () => api.get<{ anio: number; proximo: number; mayor_registrado: number | null }>(`/admin/numeracion/${anio}`),
    [anio],
  );
  const [proximo, setProximo] = useState("");
  const envio = useEnvio();
  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    const r = await envio.ejecutar(() => api.put("/admin/numeracion", { anio, proximo: Number(proximo) }));
    if (r) {
      setProximo("");
      recargar();
    }
  };
  return (
    <Seccion titulo="Numeración de actuaciones (carátulas)">
      <p className="tenue">
        La Actuación N° es correlativa por año y coincide con el número de caso. Para continuar la numeración que se
        llevaba en papel, indique el próximo número a asignar. No puede ser menor o igual al mayor ya registrado.
      </p>
      <Aviso error={error} />
      <form className="filtros" onSubmit={guardar}>
        <label>
          Año <input type="number" value={anio} min={1990} max={2100} onChange={(e) => setAnio(Number(e.target.value))} style={{ width: "6rem" }} />
        </label>
        {datos && (
          <span>
            Próximo número: <strong>{datos.proximo}</strong>
            {datos.mayor_registrado !== null && <span className="tenue"> (mayor registrado: {datos.mayor_registrado})</span>}
          </span>
        )}
        <input type="number" min={1} value={proximo} onChange={(e) => setProximo(e.target.value)} placeholder="Nuevo próximo número" aria-label="Nuevo próximo número" />
        <button className="boton" disabled={!proximo || envio.enviando}>
          Fijar
        </button>
      </form>
      <Aviso error={envio.error} />
    </Seccion>
  );
}

// Plantillas de informes: las edita la Dirección (todas) y cada jefatura (las de su área).
import { useState } from "react";
import { api } from "../api";
import { Aviso, Campo, Cargando, Modal, Vacio, fechaHora, useDatos, useEnvio, useSesion } from "../comun";
import { BarraFormato, EditorTexto, useCatalogoInformes } from "./informes";

interface SeccionPlantilla {
  titulo: string;
  guia: string;
  texto: string;
}

interface Plantilla {
  id: number;
  nombre: string;
  descripcion: string | null;
  area: { id: number; nombre: string } | null;
  tipo_documental: { id: number; nombre: string } | null;
  titulo: string;
  destinatario: boolean;
  destinatario_inicial: string;
  numerar: boolean;
  datos: string[];
  secciones: SeccionPlantilla[];
  activo: boolean;
  orden: number;
  actualizado_en: string;
  puede_editar: boolean;
}

export function PaginaPlantillas() {
  const lista = useDatos(() => api.get<Plantilla[]>("/plantillas"), []);
  const { yo, puede } = useSesion();
  const [editar, setEditar] = useState<Plantilla | "nueva" | null>(null);
  const todas = yo.permisos["plantillas.modificar"] === "todos";
  return (
    <>
      <header className="inicio-cabecera">
        <div>
          <h1>Plantillas de informes</h1>
          <p className="tenue">
            Cada plantilla define qué datos de la persona se completan solos y qué secciones lleva el informe. Quien redacta puede
            quitar o agregar datos y secciones en cada informe.{" "}
            {todas ? "Usted puede editar todas." : `Usted puede editar las de ${yo.area?.nombre ?? "su área"}; las generales las edita la Dirección.`}
          </p>
        </div>
        {puede("plantillas", "modificar") && (
          <button className="boton boton-primario" onClick={() => setEditar("nueva")}>
            Nueva plantilla
          </button>
        )}
      </header>
      <Aviso error={lista.error} />
      {!lista.datos ? (
        <Cargando />
      ) : lista.datos.length === 0 ? (
        <Vacio>No hay plantillas.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Plantilla</th>
              <th>Área</th>
              <th>Secciones</th>
              <th>Se guarda como</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lista.datos.map((p) => (
              <tr key={p.id} className={p.activo ? "" : "fila-inactiva"}>
                <td>
                  <strong>{p.nombre}</strong>
                  {!p.activo && <small> (desactivada)</small>}
                  {p.descripcion && <div className="tenue">{p.descripcion}</div>}
                </td>
                <td>{p.area?.nombre ?? "Toda la Dirección"}</td>
                <td>{p.secciones.map((s) => s.titulo || "(sin título)").join(" · ")}</td>
                <td>{p.tipo_documental?.nombre ?? "—"}</td>
                <td>
                  {p.puede_editar ? (
                    <button className="boton boton-chico" onClick={() => setEditar(p)}>
                      Editar
                    </button>
                  ) : (
                    <button className="boton boton-chico boton-texto" onClick={() => setEditar(p)}>
                      Ver
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editar && (
        <Modal titulo={editar === "nueva" ? "Nueva plantilla" : editar.nombre} alCerrar={() => setEditar(null)} ancho>
          <FormPlantilla
            plantilla={editar === "nueva" ? undefined : editar}
            alGuardar={() => {
              setEditar(null);
              lista.recargar();
            }}
          />
        </Modal>
      )}
    </>
  );
}

let uidSec = 0;

function FormPlantilla({ plantilla, alGuardar }: { plantilla?: Plantilla; alGuardar: () => void }) {
  const { catalogos, yo } = useSesion();
  const cat = useCatalogoInformes();
  const todas = yo.permisos["plantillas.modificar"] === "todos";
  const soloLectura = plantilla ? !plantilla.puede_editar : false;
  const [f, setF] = useState(() => ({
    nombre: plantilla?.nombre ?? "",
    descripcion: plantilla?.descripcion ?? "",
    area_id: plantilla ? plantilla.area?.id ?? null : todas ? null : yo.area?.id ?? null,
    tipo_documental_id: plantilla?.tipo_documental?.id ?? null,
    titulo: plantilla?.titulo ?? "",
    destinatario: plantilla?.destinatario ?? false,
    destinatario_inicial: plantilla?.destinatario_inicial ?? "",
    numerar: plantilla?.numerar ?? true,
    datos: plantilla?.datos ?? ["nombre", "fecha_nacimiento", "edad", "documento", "domicilio"],
    secciones: (plantilla?.secciones ?? [{ titulo: "", guia: "", texto: "" }]).map((s) => ({ ...s, uid: `p${++uidSec}` })),
    activo: plantilla?.activo ?? true,
    orden: plantilla?.orden ?? 0,
  }));
  const envio = useEnvio();
  if (cat.error) return <Aviso error={cat.error} />;
  if (!cat.datos) return <Cargando />;
  const campos = cat.datos.campos;
  const etiqueta = (c: string) => campos.find((x) => x.clave === c)?.etiqueta ?? c;
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const mover = <T,>(lista: T[], i: number, d: number) => {
    const n = [...lista];
    const j = i + d;
    if (j < 0 || j >= n.length) return lista;
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  };
  const setSec = (uid: string, campo: keyof SeccionPlantilla, v: string) =>
    set("secciones", f.secciones.map((s) => (s.uid === uid ? { ...s, [campo]: v } : s)));

  const guardar = (e: React.FormEvent) => {
    e.preventDefault();
    envio.ejecutar(async () => {
      const cuerpo = { ...f, secciones: f.secciones.map(({ titulo, guia, texto }) => ({ titulo, guia, texto })) };
      if (plantilla) await api.put(`/plantillas/${plantilla.id}`, cuerpo);
      else await api.post("/plantillas", cuerpo);
      alGuardar();
    });
  };

  return (
    <form className="formulario form-plantilla" onSubmit={guardar}>
      <fieldset disabled={soloLectura} className="sin-borde">
        {soloLectura && <Aviso tipo="info" error="Esta plantilla la edita la Dirección o la jefatura de su área." />}
        <div className="grilla">
          <Campo etiqueta="Nombre de la plantilla *">
            <input required value={f.nombre} onChange={(e) => set("nombre", e.target.value)} />
          </Campo>
          <Campo etiqueta="Área">
            <select value={f.area_id ?? ""} onChange={(e) => set("area_id", e.target.value ? Number(e.target.value) : null)}>
              {todas && <option value="">Toda la Dirección</option>}
              {catalogos.areas
                .filter((a) => todas || a.id === yo.area?.id || a.id === f.area_id)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre}
                  </option>
                ))}
            </select>
          </Campo>
          <Campo etiqueta="Descripción" ancho="completo" ayuda="Se muestra al elegir la plantilla.">
            <input value={f.descripcion} onChange={(e) => set("descripcion", e.target.value)} />
          </Campo>
          <Campo etiqueta="Título impreso" ayuda="Vacío: no se imprime título (p. ej., en notas).">
            <input value={f.titulo} onChange={(e) => set("titulo", e.target.value)} />
          </Campo>
          <Campo etiqueta="Al firmar se guarda como">
            <select value={f.tipo_documental_id ?? ""} onChange={(e) => set("tipo_documental_id", e.target.value ? Number(e.target.value) : null)}>
              <option value="">Otros documentos</option>
              {catalogos.tipos_documentales.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <label className="casilla">
            <input type="checkbox" checked={f.numerar} onChange={(e) => set("numerar", e.target.checked)} /> Numerar las secciones (1., 2., 3.…)
          </label>
          <label className="casilla">
            <input type="checkbox" checked={f.destinatario} onChange={(e) => set("destinatario", e.target.checked)} /> Lleva destinatario
          </label>
          <label className="casilla">
            <input type="checkbox" checked={f.activo} onChange={(e) => set("activo", e.target.checked)} /> Activa (se ofrece al redactar)
          </label>
          {f.destinatario && (
            <Campo etiqueta="Destinatario sugerido" ancho="completo">
              <textarea rows={4} value={f.destinatario_inicial} onChange={(e) => set("destinatario_inicial", e.target.value)} />
            </Campo>
          )}
        </div>

        <h3>Datos de la persona que se completan solos</h3>
        <ol className="lista-ordenable">
          {f.datos.map((c, i) => (
            <li key={c}>
              <span>{etiqueta(c)}</span>
              <span className="botones-orden">
                <button type="button" onClick={() => set("datos", mover(f.datos, i, -1))} disabled={i === 0} title="Subir">
                  ↑
                </button>
                <button type="button" onClick={() => set("datos", mover(f.datos, i, 1))} disabled={i === f.datos.length - 1} title="Bajar">
                  ↓
                </button>
                <button type="button" onClick={() => set("datos", f.datos.filter((x) => x !== c))} title="Quitar" aria-label={`Quitar ${etiqueta(c)}`}>
                  ×
                </button>
              </span>
            </li>
          ))}
        </ol>
        <select
          value=""
          aria-label="Agregar dato"
          onChange={(e) => e.target.value && set("datos", [...f.datos, e.target.value])}
        >
          <option value="">+ Agregar dato…</option>
          {campos
            .filter((c) => !f.datos.includes(c.clave))
            .map((c) => (
              <option key={c.clave} value={c.clave}>
                {c.etiqueta}
              </option>
            ))}
        </select>

        <h3>Secciones</h3>
        <BarraFormato />
        {f.secciones.map((s, i) => (
          <div className="plantilla-seccion" key={s.uid}>
            <div className="plantilla-seccion-cabecera">
              <span className="seccion-numero">{i + 1}</span>
              <input aria-label="Título de la sección" placeholder="Título (vacío = sin título, p. ej. el cuerpo de una nota)" value={s.titulo} onChange={(e) => setSec(s.uid, "titulo", e.target.value)} />
              <span className="botones-orden">
                <button type="button" onClick={() => set("secciones", mover(f.secciones, i, -1))} disabled={i === 0} title="Subir">
                  ↑
                </button>
                <button type="button" onClick={() => set("secciones", mover(f.secciones, i, 1))} disabled={i === f.secciones.length - 1} title="Bajar">
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => set("secciones", f.secciones.filter((x) => x.uid !== s.uid))}
                  disabled={f.secciones.length === 1}
                  title="Quitar"
                  aria-label={`Quitar la sección ${s.titulo}`}
                >
                  ×
                </button>
              </span>
            </div>
            <input
              className="plantilla-guia"
              aria-label="Guía para quien redacta"
              placeholder="Guía para quien redacta (qué escribir aquí; no se imprime)"
              value={s.guia}
              onChange={(e) => setSec(s.uid, "guia", e.target.value)}
            />
            <EditorTexto
              uid={s.uid}
              inicial={s.texto}
              soloLectura={soloLectura}
              etiqueta={`Texto inicial de ${s.titulo || "la sección"}`}
              placeholder="Texto inicial (opcional): frases que se repiten en todos los informes"
              alCambiar={(h) => setSec(s.uid, "texto", h)}
            />
          </div>
        ))}
        <button type="button" className="boton" onClick={() => set("secciones", [...f.secciones, { titulo: "", guia: "", texto: "", uid: `p${++uidSec}` }])}>
          + Agregar sección
        </button>
      </fieldset>
      {plantilla && <p className="tenue">Última modificación: {fechaHora(plantilla.actualizado_en)}. Los cambios valen para los informes nuevos; los ya redactados no cambian.</p>}
      <Aviso error={envio.error} />
      {!soloLectura && (
        <div className="fila-botones">
          <button className="boton boton-primario" disabled={envio.enviando}>
            {envio.enviando ? "Guardando…" : "Guardar plantilla"}
          </button>
        </div>
      )}
    </form>
  );
}

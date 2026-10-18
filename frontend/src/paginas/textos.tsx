import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Documento } from "../api";
import { Aviso, Cargando, Modal, Vacio, useDatos, useEnvio, useSesion } from "../comun";

interface TextoDoc {
  estado: "pendiente" | "listo" | "sin_texto" | "error";
  hojas: { hoja: number; trozos: { t: string; k: "nombre" | "documento" | "institucion" | null }[] }[];
  cuenta: { nombre: number; documento: number; institucion: number };
  alerta: string | null;
  paginas: number;
}

const ROTULO: Record<string, string> = { nombre: "Nombre de la persona", documento: "Documento de la persona", institucion: "Dirección" };

/** Texto leído del documento, con el nombre y los datos de la persona y las menciones a la Dirección resaltados. */
export function VerTexto({ documento, alCerrar }: { documento: Documento; alCerrar: () => void }) {
  const { datos, error, recargar } = useDatos(() => api.get<TextoDoc>(`/documentos/${documento.id}/texto`), [documento.id]);
  const { enviando, error: errorLeer, ejecutar } = useEnvio();
  const { puede } = useSesion();
  const [sobreHoja, setSobreHoja] = useState(false);
  const cuerpo = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(-1);

  const marcas = () => Array.from(cuerpo.current?.querySelectorAll<HTMLElement>("mark") ?? []);
  const siguiente = () => {
    const m = marcas();
    if (!m.length) return;
    const i = (pos + 1) % m.length;
    setPos(i);
    m[i].scrollIntoView({ block: "center", behavior: "smooth" });
  };
  useEffect(() => {
    marcas().forEach((m, i) => m.classList.toggle("txt-actual", i === pos));
  });

  const releer = async () => {
    await ejecutar(() => api.post(`/documentos/${documento.id}/leer-texto`, {}));
    recargar();
  };

  return (
    <Modal titulo={`Texto de «${documento.titulo}»`} alCerrar={alCerrar} ancho>
      <Aviso error={error || errorLeer} />
      {!datos && !error && <Cargando />}
      {datos && (
        <>
          {datos.alerta && <p className="aviso aviso-error" role="alert">{datos.alerta}</p>}
          {datos.estado === "pendiente" && <p className="tenue">El texto de este documento todavía no se leyó.</p>}
          {datos.estado === "sin_texto" && <p className="tenue">No se pudo leer texto en este documento (¿foto borrosa o escrita a mano?).</p>}
          {datos.estado === "error" && <p className="tenue">Hubo un problema al leer este documento.</p>}
          {datos.hojas.length > 0 && (
            <div className="txt-barra">
              {(["nombre", "documento", "institucion"] as const).map((k) => (
                <span key={k} className={`txt-leyenda txt-${k}`}>
                  {ROTULO[k]}: <strong>{datos.cuenta[k]}</strong>
                </span>
              ))}
              <button type="button" className="boton boton-chico" onClick={siguiente}>
                Ir a la siguiente marca
              </button>
            </div>
          )}
          {datos.paginas > 0 && puede("documentos", "descargar") && (
            <div className="txt-barra">
              <button type="button" className={`boton boton-chico ${sobreHoja ? "" : "boton-primario"}`} onClick={() => setSobreHoja(false)}>
                Ver el texto
              </button>
              <button type="button" className={`boton boton-chico ${sobreHoja ? "boton-primario" : ""}`} onClick={() => setSobreHoja(true)}>
                Ver marcado sobre la hoja
              </button>
            </div>
          )}
          {sobreHoja && <HojaMarcada id={documento.id} paginas={datos.paginas} />}
          <div ref={cuerpo} className="txt-cuerpo" hidden={sobreHoja}>
            {datos.hojas.map((h) => (
              <section key={h.hoja}>
                <h3>Hoja {h.hoja}</h3>
                <p>
                  {h.trozos.map((t, i) => (t.k ? <mark key={i} className={`txt-${t.k}`} title={ROTULO[t.k]}>{t.t}</mark> : <span key={i}>{t.t}</span>))}
                </p>
              </section>
            ))}
          </div>
          {datos.estado !== "listo" && (
            <button type="button" className="boton" disabled={enviando} onClick={releer}>
              {enviando ? "Leyendo…" : "Leer el texto ahora"}
            </button>
          )}
        </>
      )}
    </Modal>
  );
}

interface Marcas {
  hojas: number;
  disponible: boolean;
  marcas: { k: "nombre" | "documento" | "institucion"; t: string; x: number; y: number; w: number; h: number }[];
}

/** La hoja como imagen con cajas de color sobre cada palabra marcada. */
function HojaMarcada({ id, paginas }: { id: string; paginas: number }) {
  const [hoja, setHoja] = useState(1);
  const { datos, error } = useDatos(() => api.get<Marcas>(`/documentos/${id}/hojas/${hoja}/marcas`), [id, hoja]);
  return (
    <div>
      <div className="txt-barra">
        <button type="button" className="boton boton-chico" disabled={hoja <= 1} onClick={() => setHoja(hoja - 1)}>
          ◀ Hoja anterior
        </button>
        <span>
          Hoja {hoja} de {paginas}
        </span>
        <button type="button" className="boton boton-chico" disabled={hoja >= paginas} onClick={() => setHoja(hoja + 1)}>
          Hoja siguiente ▶
        </button>
        {datos && <small className="tenue">{datos.marcas.length} marcas</small>}
      </div>
      <Aviso error={error} />
      {!datos && !error && <Cargando />}
      {datos && !datos.disponible && <p className="tenue">El lector de texto no está instalado en el servidor: no se pueden ubicar las marcas.</p>}
      <div className="txt-hoja">
       <div className="txt-hoja-interna">
        <img src={`/api/documentos/${id}/hojas/${hoja}/imagen`} alt={`Hoja ${hoja}`} />
        {datos?.marcas.map((m, i) => (
          <span
            key={i}
            className={`txt-caja txt-${m.k}`}
            title={ROTULO[m.k]}
            style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.w * 100}%`, height: `${m.h * 100}%` }}
          />
        ))}
       </div>
      </div>
    </div>
  );
}

interface Resultado extends Documento {
  persona: { id: string; nombre: string } | null;
  fragmento: string;
}

export function PaginaBuscarDocumentos() {
  const [q, setQ] = useState("");
  const [r, setR] = useState<{ total: number; resultados: Resultado[] } | null>(null);
  const [ver, setVer] = useState<Resultado | null>(null);
  const { enviando, error, ejecutar } = useEnvio();
  const buscar = async (e: FormEvent) => {
    e.preventDefault();
    const x = await ejecutar(() => api.get<{ total: number; resultados: Resultado[] }>("/documentos/buscar", { q }));
    if (x) setR(x);
  };
  return (
    <div className="pagina">
      <h1>Buscar en documentos</h1>
      <p className="tenue">Busca en el texto leído de los documentos. Solo aparecen los de legajos a los que usted tiene acceso, y cada búsqueda queda registrada.</p>
      <form className="buscador" onSubmit={buscar} role="search">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Palabras o frase, por ejemplo: resolución 245" aria-label="Buscar en documentos" />
        <button className="boton boton-primario" disabled={enviando || q.trim().length < 2}>
          Buscar
        </button>
      </form>
      <Aviso error={error} />
      {r && r.total === 0 && <Vacio>No se encontró nada. Los documentos recién cargados pueden tardar unos minutos en poder buscarse.</Vacio>}
      {r && r.total > 0 && (
        <ul className="txt-resultados">
          {r.resultados.map((d) => (
            <li key={d.id}>
              <strong>{d.titulo}</strong> <small className="tenue">· {d.tipo_documental.nombre}</small>
              {d.persona && (
                <div>
                  <a href={`#/legajos/${d.persona.id}`}>{d.persona.nombre}</a>
                </div>
              )}
              <div className="tenue">{d.fragmento}</div>
              <button type="button" className="boton boton-chico" onClick={() => setVer(d)}>
                Ver texto marcado
              </button>
            </li>
          ))}
        </ul>
      )}
      {ver && <VerTexto documento={ver} alCerrar={() => setVer(null)} />}
    </div>
  );
}

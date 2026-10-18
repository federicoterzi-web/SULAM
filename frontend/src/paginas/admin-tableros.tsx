// Administración › Tableros: cada perfil de inicio se arma como una grilla de bloques (widgets) que se arrastran,
// se ensanchan o se ocultan. Lo que se guarda lo ve cualquier persona cuyo rol use ese tablero (sulam/tableros.py).
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Aviso, Cargando, useDatos, useEnvio } from "../comun";

interface Bloque {
  id: string;
  ancho: number;
  visible: boolean;
}

interface Tablero {
  codigo: string;
  nombre: string;
  personalizado: boolean;
  catalogo: { id: string; titulo: string; ancho: number }[];
  diseno: Bloque[];
  roles: string[];
}

const ANCHOS: [number, string][] = [
  [3, "1/4"],
  [4, "1/3"],
  [6, "1/2"],
  [8, "2/3"],
  [9, "3/4"],
  [12, "Completo"],
];

const textoAncho = (n: number) => ANCHOS.find(([v]) => v === n)?.[1] ?? `${n}/12`;

export function Tableros() {
  const lista = useDatos(() => api.get<Tablero[]>("/inicio/disenos"), []);
  const [codigo, setCodigo] = useState<string | null>(null);
  if (lista.error) return <Aviso error={lista.error} />;
  if (!lista.datos) return <Cargando />;
  const actual = lista.datos.find((t) => t.codigo === codigo) ?? lista.datos[0];
  return (
    <section>
      <p className="tenue">
        Armá el tablero de inicio de cada perfil: arrastrá los bloques para cambiar el orden, estiralos desde el borde derecho (o elegí el ancho) y ocultá los que no
        hagan falta. Los cambios los ve cada persona la próxima vez que abre el tablero. La versión para celular no cambia.
      </p>
      <div className="segmentado" role="tablist" aria-label="Tablero a editar">
        {lista.datos.map((t) => (
          <button key={t.codigo} role="tab" aria-selected={t.codigo === actual.codigo} className={t.codigo === actual.codigo ? "activo" : ""} onClick={() => setCodigo(t.codigo)}>
            {t.nombre}
            {t.personalizado && " ●"}
          </button>
        ))}
      </div>
      <Editor key={actual.codigo} tablero={actual} alGuardar={() => lista.recargar()} />
    </section>
  );
}

function Editor({ tablero, alGuardar }: { tablero: Tablero; alGuardar: () => void }) {
  const [items, setItems] = useState<Bloque[]>(tablero.diseno);
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);
  const { enviando, error, ejecutar } = useEnvio();
  const grilla = useRef<HTMLDivElement>(null);
  const titulo = (id: string) => tablero.catalogo.find((c) => c.id === id)?.titulo ?? id;
  const sucio = JSON.stringify(items) !== JSON.stringify(tablero.diseno);
  const visibles = items.filter((b) => b.visible);
  const ocultos = items.filter((b) => !b.visible);

  const mover = (id: string, antesDe: string) => {
    if (id === antesDe) return;
    setItems((xs) => {
      const m = xs.find((x) => x.id === id)!;
      const resto = xs.filter((x) => x.id !== id);
      const i = resto.findIndex((x) => x.id === antesDe);
      return [...resto.slice(0, i), m, ...resto.slice(i)];
    });
    setGuardado(false);
  };
  const corrimiento = (id: string, d: -1 | 1) => {
    const vis = visibles.map((b) => b.id);
    const i = vis.indexOf(id) + d;
    if (i < 0 || i >= vis.length) return;
    // Intercambia con el vecino visible.
    setItems((xs) => {
      const a = xs.findIndex((x) => x.id === id);
      const b = xs.findIndex((x) => x.id === vis[i]);
      const copia = [...xs];
      [copia[a], copia[b]] = [copia[b], copia[a]];
      return copia;
    });
    setGuardado(false);
  };
  const cambiar = (id: string, cambio: Partial<Bloque>) => {
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...cambio } : x)));
    setGuardado(false);
  };

  // Cambio de ancho arrastrando el borde derecho: se ajusta al ancho permitido más cercano.
  const estirar = (ev: React.PointerEvent, id: string) => {
    ev.preventDefault();
    const tarjeta = (ev.currentTarget as HTMLElement).parentElement!;
    const caja = grilla.current!.getBoundingClientRect();
    const col = caja.width / 12;
    const izq = tarjeta.getBoundingClientRect().left;
    const mueve = (e: PointerEvent) => {
      const n = Math.max(3, Math.min(12, Math.round((e.clientX - izq) / col)));
      const v = ANCHOS.reduce((mejor, [a]) => (Math.abs(a - n) < Math.abs(mejor - n) ? a : mejor), 12);
      cambiar(id, { ancho: v });
    };
    const suelta = () => {
      window.removeEventListener("pointermove", mueve);
      window.removeEventListener("pointerup", suelta);
    };
    window.addEventListener("pointermove", mueve);
    window.addEventListener("pointerup", suelta);
  };

  const guardar = async () => {
    const r = await ejecutar(() => api.put(`/inicio/disenos/${tablero.codigo}`, { bloques: items }));
    if (r) {
      setGuardado(true);
      alGuardar();
    }
  };
  const restablecer = async () => {
    if (!window.confirm("¿Volver al diseño original de este tablero?")) return;
    const r = await ejecutar(async () => {
      await api.delete(`/inicio/disenos/${tablero.codigo}`);
      return true;
    });
    if (r) alGuardar();
  };
  // Si el diseño guardado cambia desde afuera (restablecer), se vuelve a leer.
  useEffect(() => setItems(tablero.diseno), [tablero.diseno]);

  return (
    <div className="tablero-editor">
      <p className="tenue">
        {tablero.roles.length > 0 ? <>Lo usan los roles: <strong>{tablero.roles.join(", ")}</strong>.</> : "Ningún rol activo usa este tablero todavía."}
        {tablero.personalizado ? " Tiene un diseño propio." : " Tiene el diseño original."}
      </p>
      <div className="te-grilla" ref={grilla}>
        {visibles.map((b, i) => (
          <div
            key={b.id}
            className={`te-bloque ${arrastrando === b.id ? "arrastrando" : ""} ${sobre === b.id && arrastrando !== b.id ? "destino" : ""}`}
            style={{ gridColumn: `span ${b.ancho}` }}
            draggable
            onDragStart={(e) => {
              setArrastrando(b.id);
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", b.id);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setSobre(b.id);
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (arrastrando) mover(arrastrando, b.id);
              setArrastrando(null);
              setSobre(null);
            }}
            onDragEnd={() => {
              setArrastrando(null);
              setSobre(null);
            }}
          >
            <div className="te-cabecera">
              <span className="te-asa" aria-hidden title="Arrastrar">⠿</span>
              <strong>{titulo(b.id)}</strong>
            </div>
            <div className="te-controles">
              <button type="button" className="boton boton-chico" onClick={() => corrimiento(b.id, -1)} disabled={i === 0} aria-label="Mover antes">
                ◀
              </button>
              <button type="button" className="boton boton-chico" onClick={() => corrimiento(b.id, 1)} disabled={i === visibles.length - 1} aria-label="Mover después">
                ▶
              </button>
              <select value={b.ancho} onChange={(e) => cambiar(b.id, { ancho: Number(e.target.value) })} aria-label="Ancho">
                {ANCHOS.map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
                {!ANCHOS.some(([v]) => v === b.ancho) && <option value={b.ancho}>{textoAncho(b.ancho)}</option>}
              </select>
              <button type="button" className="boton boton-chico" onClick={() => cambiar(b.id, { visible: false })} disabled={visibles.length === 1} title="Ocultar este bloque">
                Ocultar
              </button>
            </div>
            <span className="te-estirar" onPointerDown={(e) => estirar(e, b.id)} title="Arrastrar para cambiar el ancho" aria-hidden />
          </div>
        ))}
      </div>
      {ocultos.length > 0 && (
        <div className="te-ocultos">
          <strong>Ocultos:</strong>
          {ocultos.map((b) => (
            <button key={b.id} type="button" className="boton boton-chico" onClick={() => cambiar(b.id, { visible: true })}>
              ＋ {titulo(b.id)}
            </button>
          ))}
        </div>
      )}
      <Aviso error={error} />
      {guardado && !sucio && <p className="aviso aviso-exito" role="status">Guardado.</p>}
      <div className="fila-botones fila-izquierda">
        <button className="boton boton-primario" onClick={guardar} disabled={!sucio || enviando}>
          Guardar diseño
        </button>
        <button className="boton" onClick={() => setItems(tablero.diseno)} disabled={!sucio}>
          Descartar cambios
        </button>
        <button className="boton" onClick={restablecer} disabled={!tablero.personalizado || enviando}>
          Volver al diseño original
        </button>
      </div>
    </div>
  );
}

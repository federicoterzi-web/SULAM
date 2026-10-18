// Localidad con búsqueda, acotada al departamento elegido. Siempre admite escribir una localidad que no esté en la lista.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "./api";

type Mapa = Record<string, string[]>;
let cache: Promise<Mapa> | null = null;

function cargar(): Promise<Mapa> {
  if (!cache) cache = api.get<Mapa>("/localidades").catch(() => ({}) as Mapa);
  return cache;
}

export function useLocalidades(): Mapa | null {
  const [mapa, setMapa] = useState<Mapa | null>(null);
  useEffect(() => {
    let vivo = true;
    cargar().then((m) => vivo && setMapa(m));
    return () => {
      vivo = false;
    };
  }, []);
  return mapa;
}

const sinTildes = (t: string) =>
  t
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();

/** Mismo cambio de departamento para todos los formularios: si la localidad ya no corresponde, se vacía. */
export function cambiarDepartamento(mapa: Mapa | null, actual: string, nuevoDep: string): string | undefined {
  if (!actual || !mapa) return undefined;
  const lista = mapa[nuevoDep] ?? [];
  return lista.some((x) => sinTildes(x) === sinTildes(actual)) ? undefined : "";
}

/** Cambios a aplicar al formulario cuando se elige el departamento. */
export function alElegirDepartamento(mapa: Mapa | null, d: { localidad: string }, dep: string): { departamento: string; localidad?: string } {
  const vaciar = cambiarDepartamento(mapa, d.localidad, dep);
  return vaciar === undefined ? { departamento: dep } : { departamento: dep, localidad: vaciar };
}

/** Cambios a aplicar cuando se escribe o elige la localidad (si no había departamento, se completa con el de la localidad). */
export function alElegirLocalidad(loc: string, dep?: string): { localidad: string; departamento?: string } {
  return dep ? { localidad: loc, departamento: dep } : { localidad: loc };
}

export function SelectorDepartamento({ valor, alCambiar }: { valor: string; alCambiar: (dep: string) => void; movil?: boolean }) {
  const mapa = useLocalidades();
  const lista = Object.keys(mapa ?? {});
  return (
    <select value={valor} onChange={(e) => alCambiar(e.target.value)}>
      <option value="">—</option>
      {valor && !lista.includes(valor) && <option value={valor}>{valor}</option>}
      {lista.map((x) => (
        <option key={x} value={x}>
          {x}
        </option>
      ))}
    </select>
  );
}

export function SelectorLocalidad({
  departamento,
  valor,
  alCambiar,
  movil,
}: {
  departamento: string;
  valor: string;
  alCambiar: (localidad: string, departamento?: string) => void;
  movil?: boolean;
}) {
  const mapa = useLocalidades();
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);
  const id = useId();
  const caja = useRef<HTMLDivElement>(null);

  const opciones = useMemo(() => {
    if (!mapa) return [] as { loc: string; dep: string }[];
    const todas = departamento ? (mapa[departamento] ?? []).map((loc) => ({ loc, dep: departamento })) : Object.entries(mapa).flatMap(([dep, locs]) => locs.map((loc) => ({ loc, dep })));
    const q = sinTildes(valor);
    return todas.filter((o) => !q || sinTildes(o.loc).includes(q)).slice(0, 60);
  }, [mapa, departamento, valor]);

  useEffect(() => {
    const fuera = (e: MouseEvent) => {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, []);

  const elegir = (o: { loc: string; dep: string }) => {
    alCambiar(o.loc, departamento ? undefined : o.dep);
    setAbierto(false);
  };
  const teclas = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAbierto(true);
      setActivo((a) => Math.min(a + 1, opciones.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && abierto && opciones[activo]) {
      e.preventDefault();
      elegir(opciones[activo]);
    } else if (e.key === "Escape") {
      setAbierto(false);
    }
  };
  const exacta = opciones.some((o) => sinTildes(o.loc) === sinTildes(valor));

  return (
    <div ref={caja} className="combo">
      <input
        value={valor}
        onChange={(e) => {
          alCambiar(e.target.value);
          setAbierto(true);
          setActivo(0);
        }}
        onFocus={() => setAbierto(true)}
        onKeyDown={teclas}
        role="combobox"
        aria-expanded={abierto}
        aria-controls={id}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder={departamento ? "Escriba para buscar" : "Elija primero el departamento (o escriba)"}
        maxLength={200}
      />
      {abierto && opciones.length > 0 && !(exacta && opciones.length === 1) && (
        <ul id={id} role="listbox" className={movil ? "combo-lista combo-lista-movil" : "combo-lista"}>
          {opciones.map((o, i) => (
            <li key={o.dep + o.loc} role="option" aria-selected={i === activo} className={i === activo ? "combo-activa" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => elegir(o)}>
              {o.loc}
              {!departamento && <span className="tenue"> · {o.dep}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

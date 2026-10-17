// Fotos de documentos con la cámara del celular. Cada hoja se achica en el
// teléfono antes de enviarla (menos datos móviles) y el servidor arma un único
// PDF. Las fotos no pasan por la galería y se descartan al terminar.
import { useEffect, useRef, useState } from "react";
import { ApiError, api, subirConProgreso, type Caso, type PersonaDetalle } from "../api";
import { Aviso, Cargando, fecha, nombre, useDatos, useSesion } from "../comun";
import { avisar } from "./movil";

const LADO_MAXIMO = 2000;

interface Hoja {
  id: number;
  blob: Blob;
  url: string;
}

/** Reduce la foto y la vuelve a codificar (quita metadatos como la ubicación). */
async function achicar(archivo: File): Promise<Blob> {
  const url = URL.createObjectURL(archivo);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const escala = Math.min(1, LADO_MAXIMO / Math.max(img.naturalWidth, img.naturalHeight));
    const lienzo = document.createElement("canvas");
    lienzo.width = Math.round(img.naturalWidth * escala);
    lienzo.height = Math.round(img.naturalHeight * escala);
    lienzo.getContext("2d")!.drawImage(img, 0, 0, lienzo.width, lienzo.height);
    return await new Promise<Blob>((ok, mal) =>
      lienzo.toBlob((b) => (b ? ok(b) : mal(new Error("No se pudo procesar la foto."))), "image/jpeg", 0.82),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

interface CasoConDemandas extends Caso {
  persona: PersonaDetalle;
  demandas: { id: string; fecha: string; escaneos: string[] }[];
}

export function FotosMovil({ casoId, personaId, demandaId = "" }: { casoId?: string; personaId?: string; demandaId?: string }) {
  const { catalogos } = useSesion();
  const { datos, error: errorCarga } = useDatos(async () => {
    if (casoId) {
      const c = await api.get<CasoConDemandas>(`/casos/${casoId}`);
      return { persona: c.persona, caso: c };
    }
    return { persona: await api.get<PersonaDetalle>(`/personas/${personaId}`), caso: null as CasoConDemandas | null };
  }, [casoId, personaId]);

  const tipos = catalogos.tipos_documentales;
  const tipoPorNombre = (n: string) => tipos.find((t) => t.nombre === n)?.id;
  const [tipo, setTipo] = useState<number | undefined>(
    tipoPorNombre(demandaId ? "Registro de demanda" : "Otros documentos") ?? tipos[0]?.id,
  );
  const [demanda, setDemanda] = useState(demandaId);
  const [titulo, setTitulo] = useState("");
  const [tituloEditado, setTituloEditado] = useState(false);
  const [hojas, setHojas] = useState<Hoja[]>([]);
  const [procesando, setProcesando] = useState(false);
  const [avance, setAvance] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const camara = useRef<HTMLInputElement>(null);
  const galeria = useRef<HTMLInputElement>(null);
  const siguiente = useRef(1);

  // Las fotos se liberan de la memoria al salir de la pantalla.
  const hojasRef = useRef(hojas);
  hojasRef.current = hojas;
  useEffect(() => () => hojasRef.current.forEach((h) => URL.revokeObjectURL(h.url)), []);

  const tipoActual = tipos.find((t) => t.id === tipo);
  useEffect(() => {
    if (!tituloEditado && tipoActual) {
      const d = datos?.caso?.demandas.find((x) => x.id === demanda);
      setTitulo(d ? `Registro de demanda del ${fecha(d.fecha)} (escaneo)` : `${tipoActual.nombre} (foto ${fecha(new Date().toISOString())})`);
    }
  }, [tipoActual, demanda, datos, tituloEditado]);

  if (errorCarga) return <Aviso error={errorCarga} />;
  if (!datos) return <Cargando />;

  const agregar = async (lista: FileList | null) => {
    if (!lista || lista.length === 0) return;
    setProcesando(true);
    setError(null);
    try {
      const nuevas: Hoja[] = [];
      for (const archivo of Array.from(lista)) {
        if (!archivo.type.startsWith("image/")) {
          setError("Solo se pueden agregar fotos.");
          continue;
        }
        const blob = await achicar(archivo);
        nuevas.push({ id: siguiente.current++, blob, url: URL.createObjectURL(blob) });
      }
      setHojas((h) => [...h, ...nuevas]);
    } catch (e) {
      setError(e);
    } finally {
      setProcesando(false);
      if (camara.current) camara.current.value = "";
      if (galeria.current) galeria.current.value = "";
    }
  };

  const quitar = (id: number) =>
    setHojas((h) => {
      const x = h.find((y) => y.id === id);
      if (x) URL.revokeObjectURL(x.url);
      return h.filter((y) => y.id !== id);
    });

  const subir = (i: number) =>
    setHojas((h) => {
      const n = [...h];
      [n[i - 1], n[i]] = [n[i], n[i - 1]];
      return n;
    });

  const enviar = async () => {
    if (!tipo || hojas.length === 0) return;
    const fd = new FormData();
    hojas.forEach((h, i) => fd.append("fotos", h.blob, `hoja-${i + 1}.jpg`));
    fd.append("tipo_documental_id", String(tipo));
    fd.append("titulo", titulo.trim() || tipoActual?.nombre || "Fotos");
    fd.append("persona_id", datos.persona.id);
    if (casoId) fd.append("caso_id", casoId);
    if (demanda) fd.append("registro_demanda_id", demanda);
    setError(null);
    setAvance(0);
    try {
      const r = await subirConProgreso<{ advertencias?: string[] }>("/documentos/fotos", fd, setAvance);
      avisar(`Documento guardado (${hojas.length} ${hojas.length === 1 ? "hoja" : "hojas"})` + (r.advertencias?.length ? ` · ${r.advertencias[0]}` : ""));
      history.back();
    } catch (e) {
      setError(e instanceof ApiError ? e : new Error("No se pudo enviar."));
      setAvance(null);
    }
  };

  const demandas = datos.caso?.demandas ?? [];
  const tamanoTotal = hojas.reduce((s, h) => s + h.blob.size, 0);
  return (
    <div className="m-formulario">
      <p className="m-contexto">
        {nombre(datos.persona)}
        {datos.caso && ` · Actuación ${datos.caso.caratula.numero_actuacion}/${datos.caso.caratula.anio_actuacion}`}
      </p>

      {demandas.length > 0 && (
        <label className="m-campo">
          <span>¿Es el escaneo de un registro de demanda?</span>
          <select
            value={demanda}
            onChange={(e) => {
              setDemanda(e.target.value);
              if (e.target.value) setTipo(tipoPorNombre("Registro de demanda") ?? tipo);
            }}
          >
            <option value="">No, es otro documento</option>
            {demandas.map((d) => (
              <option key={d.id} value={d.id}>
                Registro del {fecha(d.fecha)}
                {d.escaneos.length ? " (ya tiene escaneo)" : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="m-campo">
        <span>Tipo de documento</span>
        <select value={tipo ?? ""} onChange={(e) => setTipo(Number(e.target.value))}>
          {tipos.map((t) => (
            <option key={t.id} value={t.id}>
              {t.nombre}
            </option>
          ))}
        </select>
      </label>
      <label className="m-campo">
        <span>Título</span>
        <input
          value={titulo}
          onChange={(e) => {
            setTitulo(e.target.value);
            setTituloEditado(true);
          }}
        />
      </label>

      <div className="m-hojas">
        {hojas.map((h, i) => (
          <figure key={h.id} className="m-hoja">
            <img src={h.url} alt={`Hoja ${i + 1}`} />
            <figcaption>
              <span>Hoja {i + 1}</span>
              {i > 0 && (
                <button type="button" onClick={() => subir(i)} aria-label={`Pasar la hoja ${i + 1} antes`}>
                  ↑
                </button>
              )}
              <button type="button" onClick={() => quitar(h.id)} aria-label={`Quitar la hoja ${i + 1}`}>
                ✕
              </button>
            </figcaption>
          </figure>
        ))}
        <button type="button" className="m-hoja m-hoja-nueva" onClick={() => camara.current?.click()} disabled={procesando || avance !== null}>
          <span aria-hidden>◉</span>
          {procesando ? "Procesando…" : hojas.length ? "Sacar otra hoja" : "Sacar foto"}
        </button>
      </div>
      <input ref={camara} type="file" accept="image/*" capture="environment" hidden onChange={(e) => agregar(e.target.files)} />
      <input ref={galeria} type="file" accept="image/jpeg,image/png" multiple hidden onChange={(e) => agregar(e.target.files)} />
      <button type="button" className="m-boton-texto" onClick={() => galeria.current?.click()}>
        Elegir fotos ya guardadas en el teléfono
      </button>
      <p className="m-tenue">
        Apoye la hoja sobre una superficie oscura, con buena luz y sin sombras. Las fotos tomadas desde acá no se guardan en
        la galería.
      </p>

      <Aviso error={error} />
      {avance !== null && (
        <div className="m-progreso" role="progressbar" aria-valuenow={Math.round(avance * 100)} aria-valuemin={0} aria-valuemax={100}>
          <div style={{ width: `${Math.round(avance * 100)}%` }} />
          <span>{avance < 1 ? `Enviando… ${Math.round(avance * 100)}%` : "Armando el PDF…"}</span>
        </div>
      )}
      <div className="m-pie-fijo">
        <button className="m-boton m-boton-primario" onClick={enviar} disabled={hojas.length === 0 || avance !== null || procesando}>
          {hojas.length === 0
            ? "Saque al menos una foto"
            : `Guardar ${hojas.length} ${hojas.length === 1 ? "hoja" : "hojas"} · ${(tamanoTotal / 1024 / 1024).toFixed(1)} MB`}
        </button>
      </div>
    </div>
  );
}

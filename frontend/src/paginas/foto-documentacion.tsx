// Foto de la persona (recortada de su DNI) y panel de documentación del caso abierto.

import { useEffect, useRef, useState } from "react";
import { api, type Documento } from "../api";
import { Aviso, Cargando, Enlace, Modal, Seccion, Vacio, fecha, useDatos, useEnvio, useSesion } from "../comun";

interface Caja {
  x: number;
  y: number;
  w: number;
  h: number;
}

// ---------------------------------------------------------------- foto

export function FotoPersona({ personaId, tiene, nombre, version }: { personaId: string; tiene: boolean; nombre: string; version: number }) {
  const iniciales = nombre
    .split(/[ ,]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
  return tiene ? (
    <img className="foto-persona" src={`/api/personas/${personaId}/foto?v=${version}`} alt={`Foto de ${nombre}`} />
  ) : (
    <div className="foto-persona foto-persona-vacia" aria-hidden="true">
      {iniciales || "?"}
    </div>
  );
}

export function RecorteFoto({ personaId, documentos, alCerrar, alGuardar }: { personaId: string; documentos: Documento[]; alCerrar: () => void; alGuardar: () => void }) {
  const candidatos = documentos.filter((d) => d.mime === "application/pdf" || d.mime?.startsWith("image/"));
  const inicial = candidatos.find((d) => d.tipo_documental.nombre.startsWith("DNI")) ?? candidatos[0];
  const [docId, setDocId] = useState(inicial?.id ?? "");
  const [hoja, setHoja] = useState(1);
  const [hojas, setHojas] = useState(1);
  const [caja, setCaja] = useState<Caja | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const envio = useEnvio();
  const zona = useRef<HTMLDivElement>(null);
  const inicio = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!docId) return;
    let vivo = true;
    setBuscando(true);
    setAviso(null);
    setCaja(null);
    api
      .get<{ hojas: number; hoja: number; caja: Caja | null; deteccion_disponible: boolean }>(`/personas/${personaId}/foto/sugerencia`, { documento_id: docId })
      .then((r) => {
        if (!vivo) return;
        setHojas(r.hojas);
        setHoja(r.hoja);
        setCaja(r.caja);
        if (!r.caja) setAviso(r.deteccion_disponible ? "No se encontró una cara. Marque el recorte arrastrando sobre la imagen." : "La detección automática no está disponible en este servidor. Marque el recorte arrastrando sobre la imagen.");
      })
      .catch(() => vivo && setAviso("No se pudo leer el documento. Marque el recorte arrastrando sobre la imagen."))
      .finally(() => vivo && setBuscando(false));
    return () => {
      vivo = false;
    };
  }, [docId, personaId]);

  const punto = (e: React.PointerEvent) => {
    const r = zona.current!.getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) };
  };
  const empieza = (e: React.PointerEvent) => {
    zona.current?.setPointerCapture(e.pointerId);
    inicio.current = punto(e);
    setCaja(null);
  };
  const arrastra = (e: React.PointerEvent) => {
    if (!inicio.current) return;
    const p = punto(e);
    const a = inicio.current;
    setCaja({ x: Math.min(a.x, p.x), y: Math.min(a.y, p.y), w: Math.abs(p.x - a.x), h: Math.abs(p.y - a.y) });
  };
  const termina = () => {
    inicio.current = null;
  };
  const guardar = async () => {
    if (!caja || caja.w < 0.02 || caja.h < 0.02) return;
    const ok = await envio.ejecutar(() => api.put(`/personas/${personaId}/foto`, { documento_id: docId, hoja, caja }));
    if (ok) alGuardar();
  };

  return (
    <Modal titulo="Foto de la persona" alCerrar={alCerrar} ancho>
      {candidatos.length === 0 ? (
        <Vacio>Todavía no hay un DNI cargado (imagen o PDF). Cargue el documento y vuelva a abrir esta pantalla.</Vacio>
      ) : (
        <div className="formulario">
          <p className="tenue">
            El sistema busca la cara en el DNI y propone un recorte. Revíselo: puede dibujar otro arrastrando sobre la imagen. La imagen no sale del servidor.
          </p>
          {candidatos.length > 1 && (
            <label className="campo">
              <span className="campo-etiqueta">Documento</span>
              <select value={docId} onChange={(e) => setDocId(e.target.value)}>
                {candidatos.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.tipo_documental.nombre} · {d.titulo ?? d.nombre_original}
                  </option>
                ))}
              </select>
            </label>
          )}
          {hojas > 1 && (
            <label className="campo">
              <span className="campo-etiqueta">Hoja</span>
              <select value={hoja} onChange={(e) => { setHoja(Number(e.target.value)); setCaja(null); }}>
                {Array.from({ length: hojas }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    Hoja {i + 1}
                  </option>
                ))}
              </select>
            </label>
          )}
          {buscando && <Cargando />}
          {aviso && !buscando && <div className="aviso aviso-info">{aviso}</div>}
          <div ref={zona} className="recorte-zona" onPointerDown={empieza} onPointerMove={arrastra} onPointerUp={termina} onPointerCancel={termina}>
            <img src={`/api/documentos/${docId}/hojas/${hoja}/imagen`} alt="Documento" draggable={false} />
            {caja && <div className="recorte-caja" style={{ left: `${caja.x * 100}%`, top: `${caja.y * 100}%`, width: `${caja.w * 100}%`, height: `${caja.h * 100}%` }} />}
          </div>
          <Aviso error={envio.error} />
          <div className="fila-botones">
            <button className="boton boton-primario" onClick={guardar} disabled={envio.enviando || !caja || caja.w < 0.02 || caja.h < 0.02}>
              Usar este recorte como foto
            </button>
            <button className="boton" onClick={alCerrar}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- documentación del caso abierto

interface Doc {
  caso_abierto: boolean;
  casos_abiertos: number;
  requeridos: { tipo_id: number; nombre: string; estado: "presente" | "vencido" | "falta"; fecha: string | null; vence: string | null }[];
  faltan: number;
  presentes: { tipo_id: number; nombre: string; cantidad: number; ultimo: string }[];
  subsidios_pendientes: number | null;
}

export function PanelDocumentacion({ personaId, puedeCargar, alCargar, version }: { personaId: string; puedeCargar: boolean; alCargar: () => void; version: number }) {
  const { puede } = useSesion();
  const datos = useDatos(() => api.get<Doc>(`/personas/${personaId}/documentacion`), [personaId, version]);
  if (!puede("documentos", "consultar") || datos.error || !datos.datos || !datos.datos.caso_abierto) return null;
  const d = datos.datos;
  return (
    <Seccion
      titulo={d.faltan ? `Documentación del caso abierto · faltan ${d.faltan}` : "Documentación del caso abierto · completa"}
      acciones={
        puedeCargar && (
          <button className="boton" onClick={alCargar}>
            Cargar documento
          </button>
        )
      }
    >
      {d.requeridos.length === 0 ? (
        <Vacio>La Dirección no definió documentos requeridos para los casos abiertos.</Vacio>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Documento requerido</th>
              <th>Estado</th>
              <th>Cargado</th>
              <th>Vence</th>
            </tr>
          </thead>
          <tbody>
            {d.requeridos.map((r) => (
              <tr key={r.tipo_id}>
                <td>{r.nombre}</td>
                <td>
                  <span className={`marca ${r.estado === "presente" ? "marca-info" : "marca-alerta"}`}>{r.estado === "presente" ? "Presente" : r.estado === "vencido" ? "Vencido" : "Falta"}</span>
                </td>
                <td>{r.fecha ? fecha(r.fecha) : ""}</td>
                <td>{r.vence ? fecha(r.vence) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {d.presentes.length > 0 && (
        <p className="tenue">
          En el legajo: {d.presentes.map((p) => `${p.nombre} (${p.cantidad})`).join(" · ")}
        </p>
      )}
      {d.subsidios_pendientes ? (
        <p>
          Hay <strong>{d.subsidios_pendientes}</strong> {d.subsidios_pendientes === 1 ? "papel" : "papeles"} por presentar en el trámite de subsidios.{" "}
          <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById("s-subsidios")?.scrollIntoView(); }}>
            Ver subsidios
          </a>
        </p>
      ) : null}
      <small className="tenue">
        Qué documentos se exigen lo define la Dirección en Administración. <Enlace a="/admin/catalogos">Catálogos</Enlace>
      </small>
    </Seccion>
  );
}

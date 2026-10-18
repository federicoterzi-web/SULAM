// Notificaciones del navegador: avisan, con SULAM abierto en otra pestaña o en segundo plano,
// que hay algo nuevo para la persona. El texto es siempre genérico (sin nombres ni datos de
// personas). Lo que ya se avisó se recuerda solo en este navegador, para no repetirlo.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Yo } from "./api";

type Avisos = Record<string, string[]>;

const TEXTOS: Record<string, { uno: string; varios: (n: number) => string; ruta: string }> = {
  agenda: { uno: "Tenés una actividad agendada para las próximas horas", varios: (n) => `Tenés ${n} actividades agendadas para las próximas horas`, ruta: "/agenda" },
  participacion_cambios: { uno: "Se reprogramó o cambió de lugar un evento", varios: (n) => `Se reprogramaron o cambiaron de lugar ${n} eventos`, ruta: "/participacion" },
  casos_asignados: { uno: "Te asignaron un caso", varios: (n) => `Te asignaron ${n} casos`, ruta: "/casos" },
  casos_sin_asignar: { uno: "Hay un caso para asignar", varios: (n) => `Hay ${n} casos para asignar`, ruta: "/casos" },
  novedades: { uno: "Hay una novedad para confirmar", varios: (n) => `Hay ${n} novedades para confirmar`, ruta: "/novedades" },
  pases_entregar: { uno: "Hay una carpeta para entregar", varios: (n) => `Hay ${n} carpetas para entregar`, ruta: "/pases" },
  pases_recibir: { uno: "Hay una carpeta para recibir", varios: (n) => `Hay ${n} carpetas para recibir`, ruta: "/pases" },
  personal_aprobar: { uno: "Hay un pedido para aprobar", varios: (n) => `Hay ${n} pedidos para aprobar`, ruta: "/mi-asistencia" },
  personal_registrar: { uno: "Hay un pedido para registrar", varios: (n) => `Hay ${n} pedidos para registrar`, ruta: "/personal" },
  mis_pedidos: { uno: "Respondieron un pedido tuyo", varios: (n) => `Respondieron ${n} pedidos tuyos`, ruta: "/mi-asistencia" },
};

const CADA_MS = 60_000;

export type EstadoAvisos = "no_soportado" | "sin_https" | "bloqueado" | "apagado" | "activo";

interface Guardado {
  activo: boolean;
  vistos: Avisos;
}

const clave = (yo: Yo) => `sulam.avisos.${yo.id}`;

function leer(yo: Yo): Guardado {
  try {
    const t = localStorage.getItem(clave(yo));
    if (t) return JSON.parse(t) as Guardado;
  } catch {
    /* sin almacenamiento: los avisos funcionan igual durante la sesión */
  }
  return { activo: false, vistos: {} };
}

function guardar(yo: Yo, g: Guardado) {
  try {
    localStorage.setItem(clave(yo), JSON.stringify(g));
  } catch {
    /* ver arriba */
  }
}

function estadoActual(g: Guardado): EstadoAvisos {
  if (typeof Notification === "undefined") return "no_soportado";
  if (!window.isSecureContext) return "sin_https";
  if (Notification.permission === "denied") return "bloqueado";
  return g.activo && Notification.permission === "granted" ? "activo" : "apagado";
}

async function mostrar(titulo: string, cuerpo: string, ruta: string, etiqueta: string) {
  const opciones: NotificationOptions & { renotify?: boolean } = {
    body: cuerpo,
    tag: etiqueta,
    icon: "/iconos/sulam-192.png",
    badge: "/iconos/sulam-192.png",
    data: { ruta },
  };
  try {
    // En el celular (Android) solo se puede notificar a través del service worker.
    const reg = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : undefined;
    if (reg) {
      await reg.showNotification(titulo, opciones);
      return;
    }
  } catch {
    /* se prueba el modo directo */
  }
  try {
    const n = new Notification(titulo, opciones);
    n.onclick = () => {
      window.focus();
      location.hash = ruta;
      n.close();
    };
  } catch {
    /* el navegador no lo permite */
  }
}

export function useNotificaciones(yo: Yo) {
  const [estado, setEstado] = useState<EstadoAvisos>(() => estadoActual(leer(yo)));
  const guardado = useRef<Guardado>(leer(yo));
  const total = useRef(0);

  const traer = useCallback(async () => {
    try {
      return (await api.get<{ avisos: Avisos }>("/avisos")).avisos;
    } catch {
      return null;
    }
  }, []);

  const revisar = useCallback(async () => {
    if (estadoActual(guardado.current) !== "activo") return;
    const avisos = await traer();
    if (!avisos) return;
    const afuera = document.hidden || !document.hasFocus();
    const nuevos: { clave: string; n: number }[] = [];
    for (const [k, ids] of Object.entries(avisos)) {
      const antes = new Set(guardado.current.vistos[k] ?? []);
      const n = ids.filter((i) => !antes.has(i)).length;
      if (n > 0 && TEXTOS[k]) nuevos.push({ clave: k, n });
    }
    guardado.current = { ...guardado.current, vistos: avisos };
    guardar(yo, guardado.current);
    total.current = Object.values(avisos).reduce((s, l) => s + l.length, 0);
    document.title = total.current > 0 ? `(${total.current}) SULAM` : "SULAM";
    // Con SULAM a la vista alcanzan los contadores del menú; se avisa solo si está en segundo plano.
    if (!afuera) return;
    for (const x of nuevos.slice(0, 3)) {
      const t = TEXTOS[x.clave];
      await mostrar("SULAM", x.n === 1 ? t.uno : t.varios(x.n), t.ruta, x.clave);
    }
    if (nuevos.length > 3) await mostrar("SULAM", `Tenés ${nuevos.length} avisos nuevos`, "/", "varios");
  }, [yo, traer]);

  useEffect(() => {
    if (estado !== "activo") {
      document.title = "SULAM";
      return;
    }
    revisar();
    const t = window.setInterval(revisar, CADA_MS);
    const alVolver = () => revisar();
    document.addEventListener("visibilitychange", alVolver);
    for (const e of ["sulam:novedades", "sulam:pases", "sulam:personal"]) window.addEventListener(e, alVolver);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", alVolver);
      for (const e of ["sulam:novedades", "sulam:pases", "sulam:personal"]) window.removeEventListener(e, alVolver);
    };
  }, [estado, revisar]);

  // Toque sobre una notificación hecha por el service worker (celular).
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const f = (e: MessageEvent) => {
      if (e.data?.tipo === "sulam:ir" && typeof e.data.ruta === "string") location.hash = e.data.ruta;
    };
    navigator.serviceWorker.addEventListener("message", f);
    return () => navigator.serviceWorker.removeEventListener("message", f);
  }, []);

  const activar = useCallback(async () => {
    if (typeof Notification === "undefined" || !window.isSecureContext) return;
    const permiso = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (permiso !== "granted") {
      setEstado(estadoActual(guardado.current));
      return;
    }
    // Lo que hoy está pendiente no se vuelve a avisar: desde ahora, solo lo nuevo.
    const avisos = (await traer()) ?? {};
    guardado.current = { activo: true, vistos: avisos };
    guardar(yo, guardado.current);
    const hay = Object.values(avisos).reduce((s, l) => s + l.length, 0);
    await mostrar(
      "SULAM",
      hay > 0 ? `Avisos activados. Tenés ${hay} pendiente${hay === 1 ? "" : "s"}.` : "Avisos activados. Te avisaremos cuando haya algo nuevo.",
      "/",
      "activacion",
    );
    setEstado("activo");
  }, [yo, traer]);

  const desactivar = useCallback(() => {
    guardado.current = { ...guardado.current, activo: false };
    guardar(yo, guardado.current);
    setEstado(estadoActual(guardado.current));
  }, [yo]);

  return { estado, activar, desactivar };
}

export type Notificaciones = ReturnType<typeof useNotificaciones>;

const AYUDA: Record<EstadoAvisos, string> = {
  no_soportado: "Este navegador no permite notificaciones.",
  sin_https: "Las notificaciones del navegador solo funcionan en localhost o con https.",
  bloqueado: "Las notificaciones están bloqueadas para este sitio. Se habilitan desde el candado de la barra de direcciones.",
  apagado: "Activar avisos de novedades, casos, carpetas y pedidos en este navegador.",
  activo: "Avisos activados en este navegador. Tocar para desactivarlos.",
};

export function BotonAvisos({ avisos, className = "boton boton-chico" }: { avisos: Notificaciones; className?: string }) {
  const { estado, activar, desactivar } = avisos;
  const inactivo = estado === "no_soportado" || estado === "sin_https" || estado === "bloqueado";
  return (
    <button
      className={className}
      onClick={estado === "activo" ? desactivar : activar}
      disabled={inactivo}
      title={AYUDA[estado]}
      aria-pressed={estado === "activo"}
    >
      {estado === "activo" ? "Avisos: sí" : inactivo ? "Avisos no disponibles" : "Activar avisos"}
    </button>
  );
}

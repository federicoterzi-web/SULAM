// Cliente de la API de SULAM. La sesión viaja en una cookie HttpOnly;
// las operaciones que modifican datos envían además el token CSRF.

let csrf = "";
let alExpirar: () => void = () => {};

export function configurarSesion(token: string, onExpira?: () => void) {
  csrf = token;
  if (onExpira) alExpirar = onExpira;
}

// Modo debug «Ver como»: quien administra ve SULAM con los permisos de otro rol (solo lectura).
// Se guarda en la pestaña (sessionStorage): al cerrarla se vuelve a la vista normal.
export interface VerComo {
  rol: number;
  area?: number;
  nombre: string;
}
export function verComoActual(): VerComo | null {
  try {
    const t = sessionStorage.getItem("sulam-ver-como");
    return t ? (JSON.parse(t) as VerComo) : null;
  } catch {
    return null;
  }
}
export function fijarVerComo(v: VerComo | null) {
  try {
    if (v) sessionStorage.setItem("sulam-ver-como", JSON.stringify(v));
    else sessionStorage.removeItem("sulam-ver-como");
  } catch {
    /* sin almacenamiento: el modo no se recuerda */
  }
}
function cabecerasVerComo(h: Record<string, string>) {
  const v = verComoActual();
  if (!v) return;
  h["X-Ver-Como"] = String(v.rol);
  if (v.area) h["X-Ver-Como-Area"] = String(v.area);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detalle: any,
  ) {
    super(
      typeof detalle === "string"
        ? detalle
        : detalle?.mensaje ?? (Array.isArray(detalle) ? detalleValidacion(detalle) : "Error inesperado."),
    );
  }
}

function detalleValidacion(errores: any[]): string {
  return errores
    .map((e) => {
      const campo = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : "";
      return campo ? `${campo}: ${e.msg}` : e.msg;
    })
    .join(" · ");
}

async function pedir<T>(metodo: string, ruta: string, cuerpo?: unknown): Promise<T> {
  const init: RequestInit = { method: metodo, credentials: "same-origin", headers: {} };
  const headers = init.headers as Record<string, string>;
  cabecerasVerComo(headers);
  if (metodo !== "GET") headers["X-CSRF-Token"] = csrf;
  if (cuerpo instanceof FormData) {
    init.body = cuerpo;
  } else if (cuerpo !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(cuerpo);
  }
  let r: Response;
  try {
    r = await fetch("/api" + ruta, init);
  } catch {
    throw new ApiError(0, "Sin conexión con SULAM. Revise la señal o el wifi y vuelva a intentar; lo cargado sigue en pantalla.");
  }
  if (r.status === 401 && !ruta.startsWith("/auth/login")) alExpirar();
  if (!r.ok) {
    let detalle: any = r.statusText;
    try {
      detalle = (await r.json()).detail;
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(r.status, detalle);
  }
  return (await r.json()) as T;
}

/** Envía un formulario con archivos informando el avance (útil con datos móviles). */
export function subirConProgreso<T>(ruta: string, datos: FormData, alAvanzar: (fraccion: number) => void): Promise<T> {
  return new Promise((resolver, rechazar) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api" + ruta);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    const vc = verComoActual();
    if (vc) xhr.setRequestHeader("X-Ver-Como", String(vc.rol));
    xhr.upload.onprogress = (e) => e.lengthComputable && alAvanzar(e.loaded / e.total);
    xhr.onerror = () => rechazar(new ApiError(0, "Sin conexión: no se pudo enviar. Las fotos siguen en pantalla; reintente."));
    xhr.onload = () => {
      let cuerpo: any = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch {
        /* sin JSON */
      }
      if (xhr.status === 401) alExpirar();
      if (xhr.status >= 200 && xhr.status < 300) resolver(cuerpo as T);
      else rechazar(new ApiError(xhr.status, cuerpo?.detail ?? xhr.statusText));
    };
    xhr.send(datos);
  });
}

export const api = {
  get: <T,>(ruta: string, params?: Record<string, string | number | boolean | undefined | null>) => {
    const qs = params
      ? "?" +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    return pedir<T>("GET", ruta + qs);
  },
  post: <T,>(ruta: string, cuerpo?: unknown) => pedir<T>("POST", ruta, cuerpo ?? {}),
  patch: <T,>(ruta: string, cuerpo: unknown) => pedir<T>("PATCH", ruta, cuerpo),
  put: <T,>(ruta: string, cuerpo: unknown) => pedir<T>("PUT", ruta, cuerpo),
  delete: <T,>(ruta: string) => pedir<T>("DELETE", ruta),
};

// ---------------------------------------------------------------- tipos

export interface Yo {
  id: string;
  usuario: string;
  nombre_completo: string;
  area: { id: number; nombre: string } | null;
  roles: string[];
  permisos: Record<string, string>;
  debe_cambiar_password: boolean;
  csrf_token: string;
  sesion_movil?: boolean;
  inactividad_minutos?: number;
  ver_como?: { rol: string } | null;
}

export interface UsuarioBreve {
  id: string;
  usuario: string;
  nombre_completo: string;
}

export interface PersonaResumen {
  id: string;
  numero_legajo: string;
  legajo_provisorio: string | null;
  apellidos: string;
  nombres: string;
  tipo_documento: string | null;
  numero_documento: string | null;
  sin_documento: boolean;
  fecha_nacimiento: string | null;
  fecha_nacimiento_aproximada: boolean;
  localidad: string | null;
  unificada_en_id: string | null;
  tiene_foto?: boolean;
}

export interface PersonaDetalle extends PersonaResumen {
  motivo_sin_documento: string | null;
  domicilio: string | null;
  telefono: string | null;
  observaciones: string | null;
  genero: string | null;
  barrio: string | null;
  departamento: string | null;
  cud: string | null;
  cobertura_salud: string[];
  obra_social: string | null;
  cobertura_previsional: string[];
  trabajo_informal: boolean | null;
  discapacidades: string[];
  cuil?: string | null;
  lat?: number | null;
  lng?: number | null;
  ubicacion_actualizada_en?: string | null;
  creado_en: string;
}

export interface Opcion {
  codigo: string;
  texto: string;
  subopciones?: Opcion[];
}

export interface Formularios {
  generos: Opcion[];
  cud: Opcion[];
  indicadores: Opcion[];
  intervenciones: Opcion[];
  tipos_ingreso: Opcion[];
  derivado_por: Opcion[];
  cobertura_previsional: Opcion[];
  cobertura_salud: Opcion[];
  discapacidad: Opcion[];
  tipo_vivienda: Opcion[];
  estado_civil: Opcion[];
  estado_funcional: Opcion[];
  departamentos: string[];
}

export interface Caratula {
  numero_actuacion: number | null;
  anio_actuacion: number | null;
  fecha_ingreso: string;
  antecedentes: boolean | null;
  fecha_ultimo_ingreso: string | null;
  tipo_ingreso: string | null;
  tipo_ingreso_detalle: string | null;
  derivado_por: string | null;
  derivado_por_detalle: string | null;
  indicadores: string[];
  intervenciones: string[];
  intervencion_derivacion: string | null;
  intervencion_otro: string | null;
}

export interface Demanda {
  id: string;
  caso_id: string;
  persona_id: string;
  fecha: string;
  receptor: UsuarioBreve | null;
  cargado_por: UsuarioBreve | null;
  cargado_desde_papel: boolean;
  escaneos: string[];
  creado_en: string;
  caso_numero?: string;
  agente?: UsuarioBreve | null;
  datos_persona?: Record<string, string | null>;
  [campo: string]: any;
}

export interface Evolucion {
  id: number;
  texto: string;
  fecha: string;
  autor: UsuarioBreve | null;
  usuario: UsuarioBreve | null;
  en: string;
}

export interface Caso {
  id: string;
  numero: string;
  persona_id: string;
  estado: "abierto" | "en_seguimiento" | "pausado" | "cerrado";
  area: { id: number; nombre: string } | null;
  abierto_en: string;
  cerrado_en: string | null;
  ultima_actividad: string | null;
  motivo: string | null;
  caratula: Caratula;
  caratula_impresa_en?: string | null;
  responsables: UsuarioBreve[];
  persona?: PersonaResumen;
  historial_estados?: {
    estado_anterior: string | null;
    estado_nuevo: string;
    motivo: string | null;
    usuario: UsuarioBreve | null;
    en: string;
  }[];
  asignaciones?: { id: number; usuario: UsuarioBreve; desde: string; hasta: string | null; motivo: string | null }[];
}

export interface Expediente {
  id: string;
  numero: string;
  tipo: "administrativo" | "judicial";
  organismo: string | null;
  caratula: string | null;
  persona_id: string;
  caso_id: string | null;
  observaciones: string | null;
  creado_en: string;
  persona?: PersonaResumen;
}

export interface Vinculado {
  id: string;
  tipo_vinculo: { id: number; nombre: string };
  es_institucion: boolean;
  activo: boolean;
  apellidos?: string | null;
  nombres?: string | null;
  nombre_institucion?: string | null;
  numero_documento?: string | null;
  telefono?: string | null;
  domicilio?: string | null;
  observaciones?: string | null;
}

export interface TipoDocumental {
  id: number;
  nombre: string;
  descripcion: string | null;
  tiene_vencimiento: boolean;
  vigencia_dias: number | null;
  usa_numero: boolean;
  requerido_en_caso_abierto?: boolean;
  campos: { clave: string; etiqueta: string; tipo: "texto" | "fecha" | "numero" }[];
}

export interface Documento {
  id: string;
  persona_id: string | null;
  caso_id: string | null;
  expediente_id: string | null;
  ingreso_id: string | null;
  registro_demanda_id?: string | null;
  tipo_documental: TipoDocumental;
  fecha_emision?: string | null;
  vence?: string | null;
  numero?: string | null;
  datos?: Record<string, string>;
  cargado_en: string;
  titulo?: string;
  descripcion?: string | null;
  nombre_original?: string;
  mime?: string;
  tamano?: number;
  cargado_por?: UsuarioBreve | null;
  advertencias?: string[];
  texto_estado?: "pendiente" | "listo" | "sin_texto" | "error";
}

export interface Ingreso {
  id: string;
  numero: string;
  fecha_ingreso: string;
  remitente: string | null;
  tipo_documental: { id: number; nombre: string } | null;
  asunto: string;
  folios: number | null;
  persona_mencionada: string | null;
  documento_mencionado: string | null;
  numero_expediente_externo: string | null;
  observaciones: string | null;
  persona_id: string | null;
  persona: PersonaResumen | null;
  caso_id: string | null;
  expediente_id: string | null;
  vinculado_en: string | null;
  creado_en: string;
  documentos?: Documento[];
  sugerencias?: PersonaResumen[];
}

export interface Legajo extends PersonaDetalle {
  permisos: {
    modificar: boolean;
    crear_caso: boolean;
    crear_expediente: boolean;
    cargar_documento: boolean;
    unificar: boolean;
  };
  casos: Caso[];
  expedientes: Expediente[];
  vinculados: Vinculado[];
  documentos: Documento[];
  ingresos: Ingreso[];
}

export interface Catalogos {
  areas: { id: number; nombre: string }[];
  tipos_documentales: TipoDocumental[];
  tipos_vinculo: { id: number; nombre: string }[];
  usuarios_asignables: { id: string; nombre_completo: string; area: string | null }[];
}

export interface Coincidencia {
  persona: PersonaResumen;
  nivel: "bloqueante" | "alta" | "media";
  motivos: string[];
}

export interface EventoAuditoria {
  id: number;
  en: string;
  usuario: string;
  accion: string;
  entidad: string;
  entidad_id: string | null;
  persona_id?: string | null;
  detalle: any;
  ip?: string | null;
}

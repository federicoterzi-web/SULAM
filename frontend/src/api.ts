// Cliente de la API de SULAM. La sesión viaja en una cookie HttpOnly;
// las operaciones que modifican datos envían además el token CSRF.

let csrf = "";
let alExpirar: () => void = () => {};

export function configurarSesion(token: string, onExpira?: () => void) {
  csrf = token;
  if (onExpira) alExpirar = onExpira;
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
  contenido_restringido: boolean;
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
  reservado: boolean;
  contenido_restringido: boolean;
  area: { id: number; nombre: string } | null;
  abierto_en: string;
  cerrado_en: string | null;
  ultima_actividad: string | null;
  motivo: string | null;
  caratula: Caratula;
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
  contenido_restringido?: boolean;
  persona?: PersonaResumen;
}

export interface Vinculado {
  id: string;
  tipo_vinculo: { id: number; nombre: string };
  es_institucion: boolean;
  reservado: boolean;
  activo: boolean;
  contenido_restringido: boolean;
  apellidos?: string | null;
  nombres?: string | null;
  nombre_institucion?: string | null;
  numero_documento?: string | null;
  telefono?: string | null;
  domicilio?: string | null;
  observaciones?: string | null;
}

export interface Documento {
  id: string;
  persona_id: string | null;
  caso_id: string | null;
  expediente_id: string | null;
  ingreso_id: string | null;
  registro_demanda_id?: string | null;
  tipo_documental: { id: number; nombre: string };
  reservado: boolean;
  contenido_restringido: boolean;
  cargado_en: string;
  titulo?: string;
  descripcion?: string | null;
  nombre_original?: string;
  mime?: string;
  tamano?: number;
  cargado_por?: UsuarioBreve | null;
  advertencias?: string[];
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
  tipos_documentales: { id: number; nombre: string; reservado: boolean }[];
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

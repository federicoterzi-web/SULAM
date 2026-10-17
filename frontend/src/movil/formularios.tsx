// Formularios de la versión completa, usados también desde el celular.
// Son los mismos (mismas reglas, mismas validaciones); los estilos de .m-app
// los adaptan a una columna con campos y botones grandes.
import type { ReactNode } from "react";
import { api, type Caso, type Demanda, type Legajo, type PersonaDetalle } from "../api";
import { Aviso, Cargando, nombre, useDatos } from "../comun";
import { FormArticulacion } from "../paginas/articulaciones";
import { FormAsignar, FormEditarCaso, FormEstado } from "../paginas/casos";
import { FormContacto, type Contacto } from "../paginas/contactos";
import { FormCaratula, FormDemanda } from "../paginas/formularios";
import { FormExpediente, FormVinculado } from "../paginas/legajo";
import { FormPersona } from "../paginas/legajos";
import { FormIngreso } from "../paginas/mesa";
import { FormRecurso, useCatalogoRecursos, type Recurso } from "../paginas/recursos";
import { avisar } from "./movil";

/** Vuelve a la pantalla anterior con un aviso. */
function listo(texto: string) {
  avisar(texto);
  history.back();
}

function Marco({ contexto, children }: { contexto?: ReactNode; children: ReactNode }) {
  return (
    <div className="m-formulario m-formulario-completo">
      {contexto && <p className="m-contexto">{contexto}</p>}
      {children}
    </div>
  );
}

interface CasoDetalle extends Omit<Caso, "persona"> {
  persona: PersonaDetalle;
  demandas: Demanda[];
  expedientes: { id: string; numero: string }[];
  permisos: { modificar: boolean; derivar: boolean };
}

function useCaso(id: string) {
  return useDatos(() => api.get<CasoDetalle>(`/casos/${id}`), [id]);
}

function contextoCaso(c: CasoDetalle) {
  return `${nombre(c.persona)} · Actuación ${c.caratula.numero_actuacion}/${c.caratula.anio_actuacion}`;
}

// ---------------------------------------------------------------- caso

export function FormularioCasoMovil({ casoId, que, demandaId }: { casoId: string; que: string; demandaId?: string }) {
  const { datos: c, error } = useCaso(casoId);
  if (error) return <Aviso error={error} />;
  if (!c) return <Cargando />;
  const caso = c as unknown as Caso;
  let cuerpo: ReactNode;
  switch (que) {
    case "demanda":
      cuerpo = (
        <FormDemanda
          caso={caso}
          persona={c.persona}
          demanda={c.demandas.find((d) => d.id === demandaId)}
          alGuardar={() => listo(demandaId ? "Registro de demanda actualizado" : "Registro de demanda guardado")}
        />
      );
      break;
    case "estado":
      cuerpo = <FormEstado caso={caso} alGuardar={() => listo("Estado actualizado")} />;
      break;
    case "asignar":
      cuerpo = <FormAsignar caso={caso} alGuardar={() => listo("Equipo actualizado")} />;
      break;
    case "editar":
      cuerpo = <FormEditarCaso caso={caso} alGuardar={() => listo("Caso actualizado")} />;
      break;
    case "caratula":
      cuerpo = <FormCaratula personaId={c.persona.id} caso={caso} alGuardar={() => listo("Carátula guardada")} />;
      break;
    case "articulacion":
      cuerpo = <FormArticulacion casoId={casoId} alGuardar={() => listo("Articulación registrada")} />;
      break;
    default:
      return <Aviso error="Pantalla inexistente." />;
  }
  return <Marco contexto={contextoCaso(c)}>{cuerpo}</Marco>;
}

// ---------------------------------------------------------------- legajo

export function FormularioLegajoMovil({ personaId, que, vinculadoId }: { personaId: string; que: string; vinculadoId?: string }) {
  const { datos: l, error } = useDatos(() => api.get<Legajo>(`/personas/${personaId}`), [personaId]);
  if (error) return <Aviso error={error} />;
  if (!l) return <Cargando />;
  let cuerpo: ReactNode;
  switch (que) {
    case "editar":
      cuerpo = <FormPersona persona={l} alGuardar={() => listo("Datos del legajo actualizados")} alCancelar={() => history.back()} />;
      break;
    case "vinculado":
      cuerpo = (
        <FormVinculado
          personaId={l.id}
          vinculado={l.vinculados.find((v) => v.id === vinculadoId)}
          alGuardar={() => listo(vinculadoId ? "Vínculo actualizado" : "Vínculo agregado")}
        />
      );
      break;
    case "expediente":
      cuerpo = <FormExpediente personaId={l.id} casos={l.casos} alGuardar={() => listo("Expediente registrado")} />;
      break;
    default:
      return <Aviso error="Pantalla inexistente." />;
  }
  return <Marco contexto={`${nombre(l)} · Legajo ${l.numero_legajo}`}>{cuerpo}</Marco>;
}

// ---------------------------------------------------------------- mesa de entrada

export function IngresoMovil() {
  return (
    <Marco contexto="Nuevo ingreso de Mesa de Entrada">
      <FormIngreso alGuardar={(i) => listo(`Ingreso ${i.numero} registrado`)} />
    </Marco>
  );
}

// ---------------------------------------------------------------- red de recursos

export function RecursoFormMovil({ id }: { id?: string }) {
  const cat = useCatalogoRecursos();
  const { datos: r, error } = useDatos(() => (id ? api.get<Recurso>(`/recursos/${id}`) : Promise.resolve(null)), [id]);
  if (cat.error || error) return <Aviso error={cat.error ?? error} />;
  if (!cat.datos || (id && !r)) return <Cargando />;
  return (
    <Marco contexto={r ? `Editar: ${r.nombre}` : "Nuevo lugar en el mapa de recursos"}>
      <FormRecurso cat={cat.datos} recurso={r ?? undefined} alGuardar={() => listo(r ? "Recurso actualizado" : "Recurso agregado")} alCancelar={() => history.back()} />
    </Marco>
  );
}

export function ContactoFormMovil({ id }: { id?: string }) {
  const cat = useCatalogoRecursos();
  const { datos: c, error } = useDatos(() => (id ? api.get<Contacto>(`/contactos/${id}`) : Promise.resolve(null)), [id]);
  if (cat.error || error) return <Aviso error={cat.error ?? error} />;
  if (!cat.datos || (id && !c)) return <Cargando />;
  return (
    <Marco contexto={c ? `Editar: ${c.nombre}` : "Nuevo contacto"}>
      <FormContacto cat={cat.datos} contacto={c ?? undefined} alGuardar={() => listo(c ? "Contacto actualizado" : "Contacto agregado")} />
    </Marco>
  );
}

import { api } from "../api";
import { Aviso, Cargando, Seccion, useDatos } from "../comun";

interface FichaPapel {
  codigo: string;
  titulo: string;
  hojas: number;
  version: number;
  url: string;
}

const USO: Record<string, string> = {
  CAR: "Se completa al ingresar el caso. Lleva el N° de actuación del año.",
  RDD: "Se completa después de la primera verificación del caso. Dos hojas: imprimir doble faz o abrochar.",
  EVO: "Para registrar a mano las intervenciones. Se pueden usar varias hojas por caso.",
};

export function PaginaFichas() {
  const { datos, error } = useDatos(() => api.get<FichaPapel[]>("/formularios/papel"), []);
  if (error) return <Aviso error={error} />;
  if (!datos) return <Cargando />;
  return (
    <>
      <h1>Fichas en papel</h1>
      <p>
        Fichas oficiales con marcas en las esquinas y código QR, preparadas para que SULAM pueda leerlas desde una foto o
        un escaneo. Tienen los mismos campos que los modelos de la Dirección.
      </p>
      <Seccion titulo="Cómo completarlas">
        <ul className="lista-simple">
          <li>Imprimir en A4, al 100 % (sin «ajustar a la página»), en blanco y negro.</li>
          <li>No tapar ni recortar las marcas negras de las esquinas ni el código QR.</li>
          <li>Marcar las opciones con una X dentro del cuadro. Para corregir, rellenar el cuadro entero y aclarar al lado.</li>
          <li>En las cuadrículas, un número por casilla. El resto, en imprenta mayúscula, dentro del recuadro.</li>
          <li>Completar siempre el N° de actuación y el año en todas las hojas: así se asocian solas al caso.</li>
        </ul>
      </Seccion>
      <div className="tarjetas">
        {datos.map((f) => (
          <article key={f.codigo} className="tarjeta">
            <h3>{f.titulo.charAt(0) + f.titulo.slice(1).toLowerCase()}</h3>
            <p className="tenue">
              {f.hojas} {f.hojas === 1 ? "hoja" : "hojas"} · versión {f.version}
            </p>
            <p>{USO[f.codigo]}</p>
            <a className="boton boton-primario" href={f.url} target="_blank" rel="noreferrer">
              Abrir para imprimir
            </a>
          </article>
        ))}
      </div>
    </>
  );
}

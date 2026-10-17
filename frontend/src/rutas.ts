// Orden sugerido para una salida de visitas: vecino más cercano y mejora 2-opt.
// Distancias en línea recta: es una ayuda para ordenar, no un cálculo de calles.

export interface Lugar {
  lat: number;
  lng: number;
}

function distancia(a: Lugar, b: Lugar): number {
  const r = 6371;
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

function largo(partida: Lugar, orden: Lugar[]): number {
  let total = 0;
  let previo = partida;
  for (const p of orden) {
    total += distancia(previo, p);
    previo = p;
  }
  return total;
}

export function ordenarRecorrido<T extends Lugar>(partida: Lugar, paradas: T[]): T[] {
  const pendientes = [...paradas];
  const orden: T[] = [];
  let actual: Lugar = partida;
  while (pendientes.length) {
    let mejor = 0;
    for (let i = 1; i < pendientes.length; i++) {
      if (distancia(actual, pendientes[i]) < distancia(actual, pendientes[mejor])) mejor = i;
    }
    actual = pendientes.splice(mejor, 1)[0];
    orden.push(actual as T);
  }
  // 2-opt: invierte tramos mientras acorte el recorrido.
  let mejoro = true;
  while (mejoro) {
    mejoro = false;
    for (let i = 0; i < orden.length - 1; i++) {
      for (let j = i + 1; j < orden.length; j++) {
        const candidato = [...orden.slice(0, i), ...orden.slice(i, j + 1).reverse(), ...orden.slice(j + 1)];
        if (largo(partida, candidato) + 1e-9 < largo(partida, orden)) {
          orden.splice(0, orden.length, ...candidato);
          mejoro = true;
        }
      }
    }
  }
  return orden;
}

export function kilometros(partida: Lugar, orden: Lugar[]): number {
  return Math.round(largo(partida, orden) * 10) / 10;
}

/**
 * Enlaces de Google Maps con el recorrido. Sin «partida», el teléfono usa la
 * ubicación actual. Google admite pocas paradas intermedias, así que los
 * recorridos largos se parten en tramos de hasta 9 paradas intermedias.
 */
export function enlacesRecorrido(paradas: Lugar[], partida?: Lugar | null): string[] {
  const enlaces: string[] = [];
  const POR_TRAMO = 10;
  const punto = (p: Lugar) => `${p.lat},${p.lng}`;
  let origen = partida ?? null;
  for (let i = 0; i < paradas.length; i += POR_TRAMO) {
    const tramo = paradas.slice(i, i + POR_TRAMO);
    const destino = tramo[tramo.length - 1];
    const intermedias = tramo.slice(0, -1);
    const q = new URLSearchParams({ api: "1", destination: punto(destino), travelmode: "driving" });
    if (origen) q.set("origin", punto(origen));
    if (intermedias.length) q.set("waypoints", intermedias.map(punto).join("|"));
    enlaces.push(`https://www.google.com/maps/dir/?${q.toString()}`);
    origen = destino;
  }
  return enlaces;
}

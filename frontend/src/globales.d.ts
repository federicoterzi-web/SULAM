declare module "*.css";

declare module "*.jpg" {
  const url: string;
  export default url;
}

declare module "*.png" {
  const url: string;
  export default url;
}

// Leaflet 1.9.4 copiado en vendor/leaflet (sin tipos: se usa lo mínimo).
declare module "*leaflet-src.esm.js" {
  export const map: any;
  export const tileLayer: any;
  export const marker: any;
  export const divIcon: any;
  export const layerGroup: any;
  export const latLngBounds: any;
  export const control: any;
}

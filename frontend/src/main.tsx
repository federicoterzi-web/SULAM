import { createRoot } from "react-dom/client";
import { App } from "./app";
import "./estilos.css";

createRoot(document.getElementById("raiz")!).render(<App />);

// App instalable en el celular (el service worker no guarda datos; ver public/sw.js).
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* sin service worker SULAM funciona igual */
  });
}

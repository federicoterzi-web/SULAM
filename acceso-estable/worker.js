// Cloudflare Worker: redirige a la dirección actual de SULAM.
// La variable DESTINO (Settings > Variables and Secrets) es la dirección completa, con https:// y sin barra al final,
// por ejemplo https://algo-raro.trycloudflare.com . Se cambia desde el panel, sin tocar este código.
// El navegador conserva el final «#/c/<caso>» del QR al seguir la redirección.
export default {
  fetch(request, env) {
    if (!env.DESTINO) {
      return new Response("Este acceso todavía no está configurado.", { status: 503 });
    }
    const url = new URL(request.url);
    const destino = env.DESTINO.replace(/\/+$/, "") + url.pathname + url.search;
    return Response.redirect(destino, 302);
  },
};

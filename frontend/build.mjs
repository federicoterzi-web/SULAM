// Compilación del frontend con esbuild.
//   node build.mjs        -> genera dist/ para producción
//   node build.mjs --dev  -> servidor de desarrollo en http://localhost:5173
//                            (recompila al guardar y reenvía /api al backend en :8000)
import * as esbuild from "esbuild";
import { copyFileSync, cpSync, mkdirSync, rmSync } from "node:fs";
import http from "node:http";

const dev = process.argv.includes("--dev");
const BACKEND = process.env.SULAM_BACKEND ?? "http://127.0.0.1:8000";

rmSync("dist", { recursive: true, force: true });
mkdirSync("dist/assets", { recursive: true });
copyFileSync("index.html", "dist/index.html");
// Archivos de la app instalable (manifiesto, service worker, íconos).
cpSync("public", "dist", { recursive: true });

const opciones = {
  entryPoints: { app: "src/main.tsx" },
  bundle: true,
  outdir: "dist/assets",
  format: "esm",
  target: ["es2020"],
  sourcemap: dev,
  minify: !dev,
  loader: { ".svg": "file" },
  define: { "process.env.NODE_ENV": JSON.stringify(dev ? "development" : "production") },
  logLevel: "info",
};

if (!dev) {
  await esbuild.build(opciones);
} else {
  const ctx = await esbuild.context(opciones);
  await ctx.watch();
  const { port } = await ctx.serve({ servedir: "dist", port: 5174 });
  const destinoApi = new URL(BACKEND);
  http
    .createServer((req, res) => {
      const esApi = req.url.startsWith("/api/");
      const destino = esApi
        ? { hostname: destinoApi.hostname, port: destinoApi.port || 80 }
        : { hostname: "127.0.0.1", port };
      const estatico = /^\/(assets|iconos)\/|^\/(sw\.js|manifest\.webmanifest)$/.test(req.url);
      const ruta = !esApi && !estatico ? "/" : req.url;
      const proxy = http.request(
        { ...destino, path: ruta, method: req.method, headers: req.headers },
        (r) => {
          res.writeHead(r.statusCode, r.headers);
          r.pipe(res, { end: true });
        },
      );
      proxy.on("error", () => {
        res.writeHead(502);
        res.end("Backend no disponible");
      });
      req.pipe(proxy, { end: true });
    })
    .listen(5173, () => console.log("SULAM (desarrollo): http://localhost:5173"));
}

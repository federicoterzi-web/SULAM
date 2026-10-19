# Dirección estable para los QR (redirección)

Mientras SULAM se muestra con una dirección temporal (túnel rápido de Cloudflare), esa dirección cambia cada vez.
Los QR de las carátulas llevan la dirección que SULAM tenga como base (`SULAM_URL_PUBLICA`), así que un QR impreso
con una dirección temporal deja de servir.

**Solución:** los QR llevan una dirección **fija** (una página de redirección) y esa página manda a la dirección
actual de SULAM, conservando el caso. Cuando cambia la dirección real, se cambia **una línea** en la página y los QR ya
impresos siguen funcionando. Más adelante, cuando haya un dominio definitivo, esa misma página apunta a él.

La página no contiene ningún dato personal ni de casos: solo la dirección de destino. El QR tampoco: solo el número
interno del caso.

## Opción A: con Cloudflare (sin repositorio público)
Una cuenta gratuita de Cloudflare alcanza; no hace falta dominio. Un «Worker» te da una dirección fija tipo
`https://sulam.TU-CUENTA.workers.dev` que redirige a la dirección actual del túnel.
1. En el panel de Cloudflare: **Workers & Pages › Create › Create Worker**, nombre `sulam`, **Deploy**.
2. **Edit code**, pegar el contenido de `worker.js` de esta carpeta y **Deploy**.
3. **Settings › Variables and Secrets › Add**: tipo *Text*, nombre `DESTINO`, valor = la dirección del túnel actual
   (`https://algo-raro.trycloudflare.com`). **Deploy**.
4. En SULAM, `.env`: `SULAM_URL_PUBLICA=https://sulam.TU-CUENTA.workers.dev` y `docker compose up -d`.
5. Cada túnel nuevo: cambiar el valor de `DESTINO` en ese mismo lugar. Los QR no cambian.
(Los nombres de los menús de Cloudflare pueden variar un poco con el tiempo.)

## Opción B: con GitHub Pages (una sola vez, gratis)
1. En GitHub: **New repository**, nombre `sulam-acceso`, **Public** (no hay datos sensibles; GitHub Pages gratis lo pide público).
2. **Add file › Upload files** y subí `index.html` de esta carpeta. **Commit**.
3. **Settings › Pages**: *Source* = *Deploy from a branch*, rama `main`, carpeta `/ (root)`. **Save**. En un minuto aparece la dirección,
   algo como `https://federicoterzi-web.github.io/sulam-acceso/`.
4. En SULAM, archivo `.env`: `SULAM_URL_PUBLICA=https://federicoterzi-web.github.io/sulam-acceso` (sin barra al final) y reiniciar
   (`docker compose up -d`). Desde ahí los QR nuevos llevan esa dirección.

## Cada vez que cambia la dirección real (túnel nuevo)
1. Abrir `index.html` en GitHub (lápiz de editar), cambiar la línea `var DESTINO = "https://…"` por la dirección nueva y **Commit**.
2. Esperar un minuto y probar escaneando un QR. (Si no cambia, refrescar sin caché: Ctrl+F5.)

## Que se actualice sola (opcional)
`tunel-rapido.bat` puede escribir la dirección nueva en la página de redirección apenas aparece, sin que entres a GitHub.
Hace falta un permiso de GitHub **limitado a ese único repositorio**:
1. GitHub › tu foto › **Settings › Developer settings › Personal access tokens › Fine-grained tokens › Generate new token**.
2. Nombre `sulam-tunel`, vencimiento a elección, **Only select repositories › `sulam-acceso`**.
3. En *Repository permissions* poné **Contents: Read and write** (nada más). **Generate token** y copialo (se ve una sola vez).
4. En el `.env` de SULAM agregá (sin comillas):
   `SULAM_GITHUB_TOKEN=el-token-copiado`
   `SULAM_GITHUB_REPO=federicoterzi-web/sulam-acceso`
5. Listo: al correr `tunel-rapido.bat` se ve «Redireccion actualizada…»; en un minuto los QR abren la dirección nueva.
El token queda guardado en texto en el `.env` de esa computadora (no se sube al repositorio). Con ese permiso, quien lo tenga
solo podría cambiar archivos de `sulam-acceso`: nada de SULAM. Si se pierde la computadora, borrá el token en GitHub.
Sin esas dos líneas el túnel funciona igual y la dirección se cambia a mano, como arriba.

## Para tener en cuenta
- Si la dirección real está caída o es vieja, quien escanee verá el error de esa dirección: la página no puede saberlo.
- Cualquiera que escanee el QR llega a la pantalla de ingreso de SULAM: sin usuario y contraseña no ve nada.
- Esta solución es transitoria. Con un servidor y dominio propios del Ministerio, `SULAM_URL_PUBLICA` pasa a ser ese dominio.

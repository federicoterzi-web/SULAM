# Dirección estable para los QR (redirección)

Mientras SULAM se muestra con una dirección temporal (túnel rápido de Cloudflare), esa dirección cambia cada vez.
Los QR de las carátulas llevan la dirección que SULAM tenga como base (`SULAM_URL_PUBLICA`), así que un QR impreso
con una dirección temporal deja de servir.

**Solución:** los QR llevan una dirección **fija** (una página de redirección) y esa página manda a la dirección
actual de SULAM, conservando el caso. Cuando cambia la dirección real, se cambia **una línea** en la página y los QR ya
impresos siguen funcionando. Más adelante, cuando haya un dominio definitivo, esa misma página apunta a él.

La página no contiene ningún dato personal ni de casos: solo la dirección de destino. El QR tampoco: solo el número
interno del caso.

## Armarla (una sola vez, gratis, con GitHub Pages)
1. En GitHub: **New repository**, nombre `sulam-acceso`, **Public** (no hay datos sensibles; GitHub Pages gratis lo pide público).
2. **Add file › Upload files** y subí `index.html` de esta carpeta. **Commit**.
3. **Settings › Pages**: *Source* = *Deploy from a branch*, rama `main`, carpeta `/ (root)`. **Save**. En un minuto aparece la dirección,
   algo como `https://federicoterzi-web.github.io/sulam-acceso/`.
4. En SULAM, archivo `.env`: `SULAM_URL_PUBLICA=https://federicoterzi-web.github.io/sulam-acceso` (sin barra al final) y reiniciar
   (`docker compose up -d`). Desde ahí los QR nuevos llevan esa dirección.

## Cada vez que cambia la dirección real (túnel nuevo)
1. Abrir `index.html` en GitHub (lápiz de editar), cambiar la línea `var DESTINO = "https://…"` por la dirección nueva y **Commit**.
2. Esperar un minuto y probar escaneando un QR. (Si no cambia, refrescar sin caché: Ctrl+F5.)

## Para tener en cuenta
- Si la dirección real está caída o es vieja, quien escanee verá el error de esa dirección: la página no puede saberlo.
- Cualquiera que escanee el QR llega a la pantalla de ingreso de SULAM: sin usuario y contraseña no ve nada.
- Esta solución es transitoria. Con un servidor y dominio propios del Ministerio, `SULAM_URL_PUBLICA` pasa a ser ese dominio.

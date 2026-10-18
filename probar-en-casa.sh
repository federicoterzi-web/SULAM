#!/bin/sh
# SULAM - prueba en esta computadora (solo datos ficticios). macOS o Linux con Docker.
set -e
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Falta Docker Desktop: https://www.docker.com/products/docker-desktop/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Abrí Docker Desktop, esperá a que arranque y volvé a ejecutar este archivo."; exit 1; }
[ -f .env ] || { cp .env.example .env; printf "\nSULAM_ESCUCHA=0.0.0.0\n" >> .env; echo "Se creó .env con la configuración de prueba."; }
echo "Preparando SULAM. La primera vez tarda entre 5 y 15 minutos..."
docker compose up -d --build
printf "Esperando que SULAM arranque"
for i in $(seq 1 90); do
  if curl -s -o /dev/null http://localhost:8000/api/salud; then
    echo; echo "Listo: http://localhost:8000  (usuarios de prueba, contraseña demo-sulam-2026)"
    (command -v open >/dev/null && open http://localhost:8000) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8000) || true
    exit 0
  fi
  printf "."; sleep 2
done
echo; echo "Tarda más de lo normal: probá abrir http://localhost:8000 en un rato."

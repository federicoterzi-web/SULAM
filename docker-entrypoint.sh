#!/bin/sh
set -e
cd /app/backend
python -m sulam.cli migrar
python -m sulam.cli inicializar --admin-usuario "${SULAM_ADMIN_USUARIO:-admin}"
if [ "${SULAM_DATOS_DEMO:-0}" = "1" ]; then
  python -m sulam.cli datos-demo || true
fi
exec python -m sulam.cli servidor --host 0.0.0.0 --puerto 8000

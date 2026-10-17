# --- 1. Interfaz web -------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Aplicación ---------------------------------------------------------
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SULAM_DATA_DIR=/datos \
    SULAM_FRONTEND_DIST=/app/frontend/dist

# Cliente de PostgreSQL 16 (pg_dump / pg_restore, misma versión que el servidor) para respaldos;
# Liberation Sans (mismas medidas que Arial) para los informes en PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSo /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 fonts-liberation \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/sulam ./sulam
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN pip install --no-cache-dir -e ".[lectura]"

COPY --from=frontend /app/frontend/dist /app/frontend/dist
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --system --uid 1000 sulam \
    && mkdir -p /datos && chown sulam /datos
USER sulam

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]

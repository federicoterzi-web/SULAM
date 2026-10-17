@echo off
chcp 65001 >nul
title SULAM - prueba con datos ficticios
cd /d "%~dp0"

echo.
echo  SULAM - prueba en esta computadora (solo datos ficticios)
echo  ---------------------------------------------------------
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo  Falta Docker Desktop. Instalalo desde https://www.docker.com/products/docker-desktop/
  echo  y volve a abrir este archivo.
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo  Docker Desktop no esta abierto. Abrilo, espera a que diga "Engine running"
  echo  y volve a abrir este archivo.
  pause
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
  echo  Se creo el archivo .env con la configuracion de prueba.
)

echo  Preparando SULAM. La primera vez tarda entre 5 y 15 minutos...
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo  Algo fallo. Copia el mensaje de arriba y mandaselo a Federico.
  pause
  exit /b 1
)

echo.
echo  Esperando que SULAM termine de arrancar...
for /l %%i in (1,1,90) do (
  curl -s -o nul http://localhost:8000/api/salud && goto listo
  timeout /t 2 >nul
)
echo  SULAM tarda mas de lo normal. Proba abrir http://localhost:8000 en un rato.
pause
exit /b 0

:listo
echo.
echo  Listo. Se abre http://localhost:8000
echo  Usuarios: direccion, directora, jefa_admision, tecnica1, carga, mesa, registro, personal...
echo  Contrasena de todos: demo-sulam-2026
echo.
echo  Para apagarlo: abrir esta carpeta en PowerShell y escribir  docker compose down
start http://localhost:8000
pause

@echo off
chcp 65001 >nul
title SULAM - direccion temporal para el celular
cd /d "%~dp0"

echo.
echo  SULAM - direccion temporal con HTTPS (SOLO PARA LA DEMOSTRACION)
echo  ----------------------------------------------------------------
echo  Usar unicamente con datos ficticios. Cualquiera que tenga la
echo  direccion que aparece abajo puede ver la pantalla de ingreso.
echo.

docker info >nul 2>nul
if errorlevel 1 (
  echo  Docker Desktop no esta abierto. Abrilo y volve a ejecutar este archivo.
  pause
  exit /b 1
)

docker compose ps --status running 2>nul | findstr /i "app" >nul
if errorlevel 1 (
  echo  SULAM no esta funcionando. Primero abri probar-en-casa.bat y espera a que cargue.
  pause
  exit /b 1
)

echo  Buscando la direccion... Aparece abajo, una linea que termina en .trycloudflare.com
echo  Copiala y abrila en el celular. Para cortarla, cerra esta ventana (o Ctrl+C).
echo.
docker run --rm cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://host.docker.internal:8000
pause

# Lo usa tunel-rapido.bat: abre el túnel de Cloudflare y, cuando aparece la dirección nueva,
# la escribe sola en la página de redirección de GitHub (repositorio sulam-acceso).
# Variables en el archivo .env (opcionales; sin ellas solo se abre el túnel):
#   SULAM_GITHUB_TOKEN=...                       (permiso solo para ese repositorio, ver acceso-estable\LEEME.md)
#   SULAM_GITHUB_REPO=federicoterzi-web/sulam-acceso
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Leer-Env($nombre) {
    if (-not (Test-Path ".env")) { return $null }
    $linea = Get-Content ".env" | Where-Object { $_ -match "^\s*$nombre\s*=" } | Select-Object -Last 1
    if (-not $linea) { return $null }
    return ($linea -replace "^\s*$nombre\s*=\s*", "").Trim().Trim('"').Trim("'")
}

$token = Leer-Env "SULAM_GITHUB_TOKEN"
$repo = Leer-Env "SULAM_GITHUB_REPO"
$automatico = [bool]($token -and $repo)
$hecho = $false

function Actualizar-Redireccion($direccion) {
    try {
        $cab = @{ Authorization = "Bearer $token"; "User-Agent" = "sulam-tunel"; Accept = "application/vnd.github+json" }
        $api = "https://api.github.com/repos/$repo/contents/index.html"
        $actual = Invoke-RestMethod -Uri $api -Headers $cab -Method Get
        $texto = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($actual.content -replace "\s", "")))
        $nuevo = [regex]::Replace($texto, 'var DESTINO = "[^"]*";', ('var DESTINO = "' + $direccion + '";'))
        if ($nuevo -eq $texto) {
            Write-Host ""
            Write-Host "  La redireccion ya apuntaba a esta direccion (o no encontre la linea DESTINO en index.html)."
            return
        }
        $cuerpo = @{
            message = "Nueva direccion de SULAM"
            content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($nuevo))
            sha     = $actual.sha
        } | ConvertTo-Json
        Invoke-RestMethod -Uri $api -Headers $cab -Method Put -Body $cuerpo -ContentType "application/json" | Out-Null
        Write-Host ""
        Write-Host "  ============================================================"
        Write-Host "  Redireccion actualizada. En un minuto los QR abren: $direccion"
        Write-Host "  ============================================================"
    } catch {
        Write-Host ""
        Write-Host "  No pude actualizar la redireccion en GitHub: $($_.Exception.Message)"
        Write-Host "  Cambiala a mano (ver acceso-estable\LEEME.md). La direccion nueva es: $direccion"
    }
}

if (-not $automatico) {
    Write-Host "  (Sin SULAM_GITHUB_TOKEN y SULAM_GITHUB_REPO en .env: la redireccion se cambia a mano.)"
}

$red = $env:RED
docker run --rm --network $red --dns 1.1.1.1 --dns 8.8.8.8 cloudflare/cloudflared:latest tunnel --no-autoupdate --protocol http2 --url http://app:8000 2>&1 | ForEach-Object {
    $linea = "$_"
    Write-Host $linea
    if ($automatico -and -not $hecho -and $linea -match 'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com') {
        $hecho = $true
        Actualizar-Redireccion $Matches[0]
    }
}

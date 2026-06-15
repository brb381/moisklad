@echo off
setlocal
cd /d "%~dp0"

set /p MOYSKLAD_TOKEN_VALUE=Paste MoySklad token:

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$path = Join-Path (Get-Location) '.env';" ^
  "$token = $env:MOYSKLAD_TOKEN_VALUE;" ^
  "if (-not (Test-Path $path)) { Copy-Item '.env.example' $path }" ^
  "$lines = Get-Content -LiteralPath $path -ErrorAction SilentlyContinue;" ^
  "$updated = $false;" ^
  "$lines = $lines | ForEach-Object { if ($_ -match '^MOYSKLAD_TOKEN=') { $updated = $true; 'MOYSKLAD_TOKEN=' + $token } else { $_ } };" ^
  "if (-not $updated) { $lines += 'MOYSKLAD_TOKEN=' + $token }" ^
  "Set-Content -LiteralPath $path -Value $lines -Encoding UTF8;" ^
  "Write-Host 'MOYSKLAD_TOKEN saved to local .env'"

set MOYSKLAD_TOKEN_VALUE=

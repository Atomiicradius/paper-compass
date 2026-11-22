# Starts the API against the pilot database with the settings from db\.env.
# Run from anywhere:  powershell -File api\run-api.ps1 [-Port 8000] [-Db pc_pilot]
param([int]$Port = 8000, [string]$Db = "pc_pilot")
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
Get-Content db\.env | Where-Object { $_ -match '^\s*([A-Z0-9_]+)=(.*)$' } | ForEach-Object { Set-Item "env:$($Matches[1])" $Matches[2] }
$pg = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
$env:PC_PG_DSN = "postgresql://$($env:POSTGRES_USER):$($env:POSTGRES_PASSWORD)@127.0.0.1:$pg/$Db"
$env:PC_NEO4J_URI = "bolt://127.0.0.1:7687"; $env:PC_NEO4J_USER = $env:NEO4J_USER; $env:PC_NEO4J_PASSWORD = $env:NEO4J_PASSWORD
& .venv\Scripts\python.exe -m uvicorn api.main:app --port $Port

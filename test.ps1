# test.ps1
# Loads GATEWAY_API_KEYS from .env automatically -- no hardcoded keys.

param(
    [string]$Prompt = "Give me a haiku about oceans.",
    [string]$Model = "nemotron-3-super:cloud"
)

# --- Load .env into this PowerShell session ---
$envPath = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "No .env file found at $envPath" -ForegroundColor Red
    exit 1
}

Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim("'").Trim('"')
        Set-Item -Path "env:$key" -Value $value
    }
}

if (-not $env:GATEWAY_API_KEYS) {
    Write-Host "GATEWAY_API_KEYS not found in .env" -ForegroundColor Red
    exit 1
}

$apiKey = ($env:GATEWAY_API_KEYS -split ',')[0].Trim()
Write-Host "Using key ending in ...$($apiKey.Substring($apiKey.Length - 6))" -ForegroundColor Cyan

$headers = @{ "Authorization" = "Bearer $apiKey" }
$body = @{
    model    = $Model
    messages = @(@{ role = "user"; content = $Prompt })
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/v1/chat" -Method Post -Headers $headers -Body $body -ContentType "application/json"

Write-Host "`nResponse:" -ForegroundColor Green
$response.message.content
# test.ps1
# Loads keys from .env automatically. Tests:
#   1. Each key individually works against the gateway
#   2. An invalid key is correctly rejected
#   3. Ollama Cloud key rotation is configured in the gateway
#
# Usage:
#   .\test.ps1
#   .\test.ps1 -Model "llama3.2" -Prompt "Say hi"

param(
    [string]$Prompt = "Give me a haiku about oceans.",
    [string]$Model = "nemotron-3-super:cloud",
    [string]$BaseUrl = "http://localhost:8000"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Pass($msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }

# --- Load .env into this PowerShell session ---
$envPath = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Fail "No .env file found at $envPath"
    exit 1
}

Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2]
        # Strip inline comments (anything after an unquoted #), then trim quotes/whitespace
        $value = ($value -split '#')[0].Trim().Trim("'").Trim('"')
        Set-Item -Path "env:$key" -Value $value
    }
}

if (-not $env:GATEWAY_API_KEYS) {
    Write-Fail "GATEWAY_API_KEYS not found in .env"
    exit 1
}

$keys = $env:GATEWAY_API_KEYS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
Write-Info "Testing gateway at $BaseUrl"
Write-Info "Keys under test: $($keys.Count) key(s) loaded from .env"
Write-Host ""

$allPassed = $true

# --- Reachability check ---
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/v1/health" -Method Get -UseBasicParsing -ErrorAction Stop
    Write-Pass "gateway is reachable ($BaseUrl/v1/health -> $($resp.StatusCode))"
}
catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 503) {
        Write-Pass "gateway is reachable ($BaseUrl/v1/health -> 503, Ollama unreachable but gateway is up)"
    }
    else {
        Write-Fail "Could not reach gateway at $BaseUrl. Make sure uvicorn is running."
        exit 1
    }
}

# --- Test 1: each key works individually ---
Write-Host "`n== Test 1: each key can independently call the gateway ==" -ForegroundColor Yellow
foreach ($k in $keys) {
    $suffix = $k.Substring([Math]::Max(0, $k.Length - 6))
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/v1/usage" -Method Get -Headers @{ "Authorization" = "Bearer $k" } -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Pass "key ...$suffix -> /v1/usage returned 200"
        } else {
            Write-Fail "key ...$suffix -> unexpected status $($r.StatusCode)"
            $allPassed = $false
        }
    }
    catch {
        Write-Fail "key ...$suffix -> request failed ($($_.Exception.Message))"
        $allPassed = $false
    }
}

# --- Test 2: invalid key rejected ---
Write-Host "`n== Test 2: an invalid key is rejected ==" -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri "$BaseUrl/v1/usage" -Method Get -Headers @{ "Authorization" = "Bearer not-a-real-key" } -UseBasicParsing -ErrorAction Stop
    Write-Fail "invalid key was NOT rejected"
    $allPassed = $false
}
catch {
    $statusCode = $null
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
    }
    if ($statusCode -eq 403) {
        Write-Pass "invalid key -> got 403 (expected)"
    } else {
        Write-Fail "invalid key -> got $statusCode (expected 403)"
        $allPassed = $false
    }
}

# --- Test 3: upstream rotation configuration ---
Write-Host "`n== Test 3: Ollama Cloud key rotation is configured ==" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/v1/usage" -Method Get -Headers @{ "Authorization" = "Bearer $($keys[0])" } -UseBasicParsing -ErrorAction Stop
    $usage = $r.Content | ConvertFrom-Json
    if ($usage.ollama_keys_configured -ge 1) {
        Write-Pass "$($usage.ollama_keys_configured) Ollama key(s) configured; rotation_on_429=$($usage.rotation_on_429)"
    }
    else {
        Write-Fail "No OLLAMA_API_KEYS configured in the gateway"
        $allPassed = $false
    }
}
catch {
    Write-Fail "Could not read upstream rotation configuration ($($_.Exception.Message))"
    $allPassed = $false
}

# --- Summary ---
Write-Host "`n==================================================" -ForegroundColor Yellow
if ($allPassed) {
    Write-Host "All tests passed." -ForegroundColor Green
}
else {
    Write-Host "Some tests failed -- see above." -ForegroundColor Red
}

# --- Optional: run an actual chat call with the first key, for a sanity check ---
Write-Host "`n== Bonus: live chat call using key #1 ==" -ForegroundColor Yellow
$apiKey = $keys[0]
$body = @{
    model    = $Model
    messages = @(@{ role = "user"; content = $Prompt })
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/v1/chat" -Method Post -Headers @{ "Authorization" = "Bearer $apiKey" } -Body $body -ContentType "application/json" -ErrorAction Stop
    Write-Host $response.message.content
}
catch {
    Write-Info "Skipped or failed (key #1 may still be rate-limited from Test 3 above -- that's expected)."
}

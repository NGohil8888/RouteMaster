# test.ps1
# Loads keys from .env automatically. Tests:
#   1. Each key individually works against the gateway
#   2. An invalid key is correctly rejected
#   3. Rate limiting trips into 429 once a key's quota is used up
#   4. Rotation: once key #1 is exhausted, key #2 still works
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
        $value = $matches[2].Trim().Trim("'").Trim('"')
        Set-Item -Path "env:$key" -Value $value
    }
}

if (-not $env:GATEWAY_API_KEYS) {
    Write-Fail "GATEWAY_API_KEYS not found in .env"
    exit 1
}

$keys = $env:GATEWAY_API_KEYS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$rateLimit = if ($env:RATE_LIMIT_PER_MINUTE) { [int]$env:RATE_LIMIT_PER_MINUTE } else { 60 }

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
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 403) {
        Write-Pass "invalid key -> got 403 (expected)"
    } else {
        Write-Fail "invalid key -> got $statusCode (expected 403)"
        $allPassed = $false
    }
}

# --- Test 3 & 4: rate limit trips, then rotation to next key works ---
Write-Host "`n== Test 3: rate limit trips for the first key ==" -ForegroundColor Yellow

if ($rateLimit -le 0) {
    Write-Info "Rate limiting is disabled (RATE_LIMIT_PER_MINUTE=0) -- skipping rate limit + rotation tests."
}
else {
    $firstKey = $keys[0]
    Write-Info "Configured limit: $rateLimit/min. Sending $($rateLimit + 1) requests with key #1..."

    $hit429 = $false
    for ($i = 1; $i -le ($rateLimit + 1); $i++) {
        $body = @{ model = "does-not-matter-for-this-test"; prompt = "x" } | ConvertTo-Json
        try {
            $r = Invoke-WebRequest -Uri "$BaseUrl/v1/generate" -Method Post -Headers @{ "Authorization" = "Bearer $firstKey" } -Body $body -ContentType "application/json" -UseBasicParsing -ErrorAction Stop
            Write-Host "  request $i`: $($r.StatusCode)"
        }
        catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            Write-Host "  request $i`: $statusCode"
            if ($statusCode -eq 429) {
                $hit429 = $true
                Write-Pass "rate limit correctly triggered a 429 on request $i"
                break
            }
        }
    }
    if (-not $hit429) {
        Write-Fail "never received a 429 after $($rateLimit + 1) requests"
        $allPassed = $false
    }

    Write-Host "`n== Test 4: rotating to key #2 after key #1 is exhausted ==" -ForegroundColor Yellow
    if ($keys.Count -lt 2) {
        Write-Info "Only one key configured -- add a second key to .env to test rotation. Skipping."
    }
    else {
        $secondKey = $keys[1]
        $suffix = $secondKey.Substring([Math]::Max(0, $secondKey.Length - 6))
        $body = @{ model = "does-not-matter-for-this-test"; prompt = "x" } | ConvertTo-Json
        try {
            $r = Invoke-WebRequest -Uri "$BaseUrl/v1/generate" -Method Post -Headers @{ "Authorization" = "Bearer $secondKey" } -Body $body -ContentType "application/json" -UseBasicParsing -ErrorAction Stop
            Write-Pass "key #2 (...$suffix) still works while key #1 is rate-limited (status $($r.StatusCode))"
        }
        catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            if ($statusCode -eq 429) {
                Write-Fail "key #2 (...$suffix) was ALSO rate-limited -- rotation would not have helped here"
                $allPassed = $false
            }
            else {
                # Any non-429 (e.g. 500 because the fake model name doesn't exist)
                # means it got PAST the rate limiter on key #2, which is what we're testing.
                Write-Pass "key #2 (...$suffix) got past the rate limiter (status $statusCode, unrelated to rotation)"
            }
        }
    }
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

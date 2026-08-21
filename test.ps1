$headers = @{ "Authorization" = "Bearer AOsXIX-pzcHUyOnP8lRXl9qiIKIw1vlwTtsEgrrGJ9A" }
$body = @{
    model = "nemotron-3-super:cloud"
    messages = @(@{ role = "user"; content = "Give me a haiku about oceans." })
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/v1/chat" -Method Post -Headers $headers -Body $body -ContentType "application/json"

param(
    [string]$PythonExe = '',
    [string]$Manifest = 'artifacts/manifest.json'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) {
    if ($env:CONDA_PREFIX) { $PythonExe = Join-Path $env:CONDA_PREFIX 'python.exe' }
    else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
if (-not [System.IO.Path]::IsPathRooted($Manifest)) { $Manifest = Join-Path $projectRoot $Manifest }
if (-not (Test-Path -LiteralPath $Manifest)) { throw "Manifest missing: $Manifest" }
$logRoot = Join-Path $projectRoot 'artifacts/local-app'
New-Item -ItemType Directory -Force $logRoot | Out-Null
$env:MODEL_MANIFEST = $Manifest
$env:WEB_ORIGINS = 'http://127.0.0.1:8080,http://localhost:8080'
$env:PYTHONIOENCODING = 'utf-8'

function Get-HttpResponse([string]$Url) {
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 }
    catch { return $null }
}

if (-not (Get-HttpResponse 'http://127.0.0.1:18001/health/live')) {
    $apiProcess = Start-Process -FilePath $PythonExe -ArgumentList @(
        '-m', 'uvicorn', 'fraud_detection.api:app', '--host', '127.0.0.1',
        '--port', '18001', '--no-access-log'
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $logRoot 'api.stdout.log') `
      -RedirectStandardError (Join-Path $logRoot 'api.stderr.log')
    $apiProcess.Id | Set-Content (Join-Path $logRoot 'api.pid')
}
$modelInfo = $null
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $response = Get-HttpResponse 'http://127.0.0.1:18001/model-info'
    if ($response) { $modelInfo = $response.Content | ConvertFrom-Json; break }
    Start-Sleep -Seconds 1
}
if (-not $modelInfo) { throw "API/model not ready. Check $logRoot/api.stderr.log and MODEL_MANIFEST. Existing API processes are not restarted automatically." }
$expectedModel = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ($modelInfo.model_version -ne $expectedModel.model_version -or $modelInfo.threshold -ne $expectedModel.threshold) {
    throw 'Existing API serves another model version/threshold. Stop that API and start again with the chosen manifest.'
}
$existingWeb = Get-HttpResponse 'http://127.0.0.1:8080/config.js'
if ($existingWeb -and $existingWeb.Content -notmatch '18001') {
    throw 'Port8080 serves another web/API configuration. Stop that server before starting local web.'
}
if (-not $existingWeb) {
    $webProcess = Start-Process -FilePath $PythonExe -ArgumentList @(
        '-m', 'http.server', '8080', '--bind', '127.0.0.1', '--directory', 'src/web'
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $logRoot 'web.stdout.log') `
      -RedirectStandardError (Join-Path $logRoot 'web.stderr.log')
    $webProcess.Id | Set-Content (Join-Path $logRoot 'web.pid')
}
$webReady = $false
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    $response = Get-HttpResponse 'http://127.0.0.1:8080/app.js'
    if ($response -and $response.Content -match 'randomBatch') { $webReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $webReady) { throw "Web not ready. Check $logRoot/web.stderr.log" }
$cors = Invoke-WebRequest 'http://127.0.0.1:18001/model-info' -UseBasicParsing `
    -Headers @{ Origin = 'http://127.0.0.1:8080' } -TimeoutSec 3
if ($cors.Headers['Access-Control-Allow-Origin'] -ne 'http://127.0.0.1:8080') {
    throw 'API is running without the web CORS origin. Restart the existing API with WEB_ORIGINS configured.'
}
Write-Output "Ready: http://127.0.0.1:8080/ -> API18001, model version $($modelInfo.model_version)"
Write-Output "Logs and process IDs: $logRoot"

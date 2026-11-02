$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ''
Write-Host 'RaidRelic secure Twitch setup' -ForegroundColor Cyan
Write-Host 'Credentials are entered locally and kept in process memory only.'
Write-Host 'The client secret prompt is hidden. Nothing is written to .env or source files.'
Write-Host ''

$listener = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if ($owner.Name -ne 'python.exe' -or $owner.CommandLine -notmatch 'app\.server') {
        throw "Port 3000 is already used by $($owner.Name) (PID $($owner.ProcessId)); leaving it untouched."
    }
    Write-Host 'Restarting the existing RaidRelic local server...'
    Stop-Process -Id $owner.ProcessId -Force
    Start-Sleep -Seconds 1
}

$clientId = Read-Host 'Twitch Client ID'
if ([string]::IsNullOrWhiteSpace($clientId)) { throw 'Client ID is required.' }

$secretSecure = Read-Host 'Twitch Client Secret (input hidden)' -AsSecureString
if ($secretSecure.Length -eq 0) { throw 'Client Secret is required.' }

$bstr = [IntPtr]::Zero
$plainSecret = $null
$server = $null
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretSecure)
    $plainSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)

    $env:TWITCH_CLIENT_ID = $clientId.Trim()
    $env:TWITCH_CLIENT_SECRET = $plainSecret
    $env:TWITCH_REDIRECT_URI = 'http://localhost:3000/auth/callback'
    $env:RAIDRELIC_SIMULATION = '0'
    $env:PORT = '3000'

    Write-Host 'Validating Twitch app credentials...' -ForegroundColor DarkGray
    try {
        $credentialProbe = Invoke-RestMethod -Method Post -Uri 'https://id.twitch.tv/oauth2/token' -Body @{
            client_id = $env:TWITCH_CLIENT_ID
            client_secret = $env:TWITCH_CLIENT_SECRET
            grant_type = 'client_credentials'
        } -ErrorAction Stop
        $credentialProbe = $null
        Write-Host 'Twitch app credentials are valid.' -ForegroundColor Green
    }
    catch {
        throw "Twitch rejected this Client ID / Client Secret pair. Copy the Client ID from the Twitch Developer Console (not the secret), use its current secret, and try again. Original error: $($_.Exception.Message)"
    }

    $python = (Get-Command python -ErrorAction Stop).Source
    $logDir = Join-Path $root 'runtime'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdout = Join-Path $logDir "server-$stamp.stdout.log"
    $stderr = Join-Path $logDir "server-$stamp.stderr.log"

    $server = Start-Process -FilePath $python -ArgumentList @('-m', 'app.server') -WorkingDirectory $root -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if ($server.HasExited) { break }
        if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        throw "RaidRelic did not start. Check $stderr. The client secret was not written to disk."
    }

    Write-Host ''
    Write-Host 'RaidRelic is listening on http://localhost:3000' -ForegroundColor Green
    Write-Host 'Opening Twitch authorization. Sign in as the receiving broadcaster and approve user:read:chat.'
    Start-Process 'http://localhost:3000/auth/twitch'
    Write-Host 'Keep this window open while testing. Press Ctrl+C here to stop the server.'
    Wait-Process -Id $server.Id
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
    $env:TWITCH_CLIENT_ID = $null
    $env:TWITCH_CLIENT_SECRET = $null
    $env:TWITCH_REDIRECT_URI = $null
    $env:RAIDRELIC_SIMULATION = $null
    $env:PORT = $null
    $plainSecret = $null
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($secretSecure) { $secretSecure.Dispose() }
}
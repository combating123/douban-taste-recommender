param(
    [ValidateRange(1, 65535)]
    [int]$Port = 7861,
    [switch]$NoBrowser,
    [switch]$Stop,
    [string]$RuntimeDirectory = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = if ($RuntimeDirectory) {
    [System.IO.Path]::GetFullPath($RuntimeDirectory)
} else {
    Join-Path $here "output\runtime"
}
$pidFile = Join-Path $runtime "server-$Port.pid"
$legacyPidFile = if ($Port -eq 7861 -and -not $RuntimeDirectory) { Join-Path $runtime "server.pid" } else { $null }
$stdoutLog = Join-Path $runtime "server-$Port.stdout.log"
$stderrLog = Join-Path $runtime "server-$Port.stderr.log"

function Get-ListeningProcessId {
    param([int]$TargetPort)
    try {
        $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $TargetPort -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
        return 0
    } catch {
        return 0
    }
}

function Test-CineScopeProcess {
    param([int]$ProcessId, [int]$TargetPort)
    if ($ProcessId -le 0) { return $false }
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        $commandLine = [string]$process.CommandLine
        if (-not $commandLine.Contains("douban_recommender.web")) { return $false }
        if ($commandLine.Contains("--port $TargetPort")) { return $true }
        return $TargetPort -eq 7861 -and -not $commandLine.Contains("--port")
    } catch {
        return $false
    }
}

function Test-PortOpen {
    param([int]$TargetPort, [int]$TimeoutMilliseconds = 250)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $TargetPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-PortClosed {
    param([int]$TargetPort, [int]$TimeoutSeconds = 15)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not (Test-PortOpen -TargetPort $TargetPort)) { return $true }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

function Remove-PidFiles {
    foreach ($path in @($pidFile, $legacyPidFile)) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Stop-ManagedServer {
    $candidateIds = [System.Collections.Generic.List[int]]::new()
    foreach ($path in @($pidFile, $legacyPidFile)) {
        if (-not $path -or -not (Test-Path -LiteralPath $path)) { continue }
        $raw = (Get-Content -LiteralPath $path -Raw).Trim()
        $parsed = 0
        if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -gt 0 -and -not $candidateIds.Contains($parsed)) {
            $candidateIds.Add($parsed)
        }
    }
    $listenerId = Get-ListeningProcessId -TargetPort $Port
    if ($listenerId -gt 0 -and -not $candidateIds.Contains($listenerId)) { $candidateIds.Add($listenerId) }

    foreach ($candidateId in $candidateIds) {
        $process = Get-Process -Id $candidateId -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        if (-not (Test-CineScopeProcess -ProcessId $candidateId -TargetPort $Port)) {
            if ($candidateId -eq $listenerId) {
                throw "Port $Port is owned by a non-CineScope process (PID $candidateId)."
            }
            continue
        }
        Stop-Process -Id $candidateId -Force -ErrorAction Stop
        $process.WaitForExit(10000) | Out-Null
    }
    Remove-PidFiles
    if (-not (Wait-PortClosed -TargetPort $Port)) {
        throw "The previous CineScope process did not release port $Port."
    }
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
Stop-ManagedServer
if ($Stop) {
    Write-Output "CineScope stopped on port $Port."
    exit 0
}

$pythonProbe = & python -c "import sys; print(sys.executable)"
if ($LASTEXITCODE -ne 0) { throw "Unable to locate a usable Python interpreter." }
$pythonExe = [string]($pythonProbe | Select-Object -Last 1)
$pythonExe = $pythonExe.Trim()
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw "Invalid Python interpreter path: $pythonExe"
}

# The online feeds can return Traditional Chinese. Keep the one-click launcher
# self-contained by installing the declared pure-Python converter when absent.
& $pythonExe -c "from opencc import OpenCC" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install --disable-pip-version-check --quiet "opencc-python-reimplemented>=0.1.7"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to install the Simplified Chinese localization dependency."
    }
}

$srcPath = Join-Path $here "src"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$srcPath;$env:PYTHONPATH" } else { $srcPath }
if (-not $env:CINESCOPE_OUTBOUND_PROXY -and -not $env:DOUBAN_RECOMMENDER_HTTP_PROXY) {
    if (Test-PortOpen -TargetPort 10808 -TimeoutMilliseconds 180) {
        $env:CINESCOPE_OUTBOUND_PROXY = "socks5h://127.0.0.1:10808"
        if (-not $env:CINESCOPE_PROXY_MODE) { $env:CINESCOPE_PROXY_MODE = "fallback" }
    }
}
function ConvertTo-PowerShellLiteral {
    param([string]$Value)
    return "'" + ([string]$Value).Replace("'", "''") + "'"
}

$childLines = [System.Collections.Generic.List[string]]::new()
$environmentNames = @(
    "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP", "SYSTEMROOT", "WINDIR",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "PYTHONUTF8", "PYTHONIOENCODING"
)
$environmentNames += Get-ChildItem Env: | Where-Object { $_.Name -like "CINESCOPE_*" } | Select-Object -ExpandProperty Name
$environmentNames = $environmentNames | Sort-Object -Unique
foreach ($name in $environmentNames) {
    $value = [System.Environment]::GetEnvironmentVariable($name, "Process")
    if ($null -ne $value) {
        $childLines.Add("`$env:$name = $(ConvertTo-PowerShellLiteral -Value $value)")
    }
}
$childLines.Add("`$env:PYTHONPATH = $(ConvertTo-PowerShellLiteral -Value $env:PYTHONPATH)")
$childLines.Add("Set-Location -LiteralPath $(ConvertTo-PowerShellLiteral -Value $here)")
$childLines.Add(
    "& $(ConvertTo-PowerShellLiteral -Value $pythonExe) -m douban_recommender.web --host 127.0.0.1 --port $Port --no-browser " +
    "1>> $(ConvertTo-PowerShellLiteral -Value $stdoutLog) 2>> $(ConvertTo-PowerShellLiteral -Value $stderrLog)"
)
$encodedCommand = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes(($childLines -join [Environment]::NewLine))
)
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$launch = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "`"$powershellExe`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $encodedCommand"
    CurrentDirectory = $here
}
if ([int]$launch.ReturnValue -ne 0 -or [int]$launch.ProcessId -le 0) {
    throw "Unable to create the CineScope server process (code $($launch.ReturnValue))."
}
$launcherPid = [int]$launch.ProcessId

$url = "http://127.0.0.1:$Port/"
$deadline = [DateTime]::UtcNow.AddSeconds(45)
$ready = $false
$serverPid = 0
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $response = if (Test-PortOpen -TargetPort $Port) { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 } else { $null }
        if ($null -ne $response -and [int]$response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
    Start-Sleep -Milliseconds 150
}

if ($ready) {
    $pidDeadline = [DateTime]::UtcNow.AddSeconds(5)
    while ($serverPid -le 0 -and [DateTime]::UtcNow -lt $pidDeadline) {
        $serverPid = Get-ListeningProcessId -TargetPort $Port
        if ($serverPid -le 0) { Start-Sleep -Milliseconds 100 }
    }
    if ($serverPid -le 0) { $ready = $false }
}

if (-not $ready) {
    if ($serverPid -gt 0 -and (Test-CineScopeProcess -ProcessId $serverPid -TargetPort $Port)) {
        Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $launcherPid -Force -ErrorAction SilentlyContinue
    Remove-PidFiles
    $details = if (Test-Path -LiteralPath $stderrLog) { (Get-Content -LiteralPath $stderrLog -Tail 30) -join [Environment]::NewLine } else { "" }
    throw "CineScope did not start on port $Port.$([Environment]::NewLine)$details"
}

Set-Content -LiteralPath $pidFile -Value ([string]$serverPid) -Encoding Ascii
if ($legacyPidFile) { Set-Content -LiteralPath $legacyPidFile -Value ([string]$serverPid) -Encoding Ascii }

if (-not $NoBrowser) { Start-Process $url | Out-Null }
Write-Output "CineScope started: $url"
Write-Output "PID: $serverPid"
Write-Output "Stop: powershell -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`" -Port $Port -Stop"

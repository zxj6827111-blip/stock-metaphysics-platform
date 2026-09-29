Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:W8Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:W8RuntimeDir = Join-Path $script:W8Root 'data\w8-local-runtime'
$script:W8StateFile = Join-Path $script:W8RuntimeDir 'processes.json'
$script:W8Python = Join-Path $script:W8Root '.venv\Scripts\python.exe'
$script:W8WebDir = Join-Path $script:W8Root 'apps\web'
$script:W8ZiweiDir = Join-Path $script:W8Root 'services\ziwei-service'

function Set-W8RuntimeEnvironment {
  param([string]$DatabaseUrl)

  $env:PYTHONUTF8 = '1'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  $env:SMP_MARKET_PROVIDER = 'vendor_parquet'
  $env:SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK = 'false'
  $env:SMP_ZIWEI_SERVICE_URL = 'http://127.0.0.1:8100'
  $env:ZIWEI_HOST = '127.0.0.1'
  $env:ZIWEI_PORT = '8100'
  $env:SMP_API_BASE = 'http://127.0.0.1:8000'
  $env:NEXT_DIST_DIR = '.next-w8'
  if ([string]::IsNullOrWhiteSpace($env:NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID)) {
    $env:NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID = 'w4-engineering-002561-20120223-asof-v2'
  }
  if (-not [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $env:SMP_DATABASE_URL = $DatabaseUrl
  }
}

function Get-W8NodeExecutable {
  $command = Get-Command node -ErrorAction Stop
  if (-not (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
    throw "Node executable is unavailable: $($command.Source)"
  }
  return $command.Source
}

function Test-W8PortAvailable {
  param([int]$Port)

  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
  try {
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    $listener.Stop()
  }
}

function Invoke-W8Preflight {
  param(
    [string[]]$Services = @('ziwei', 'api', 'web'),
    [string]$DatabaseUrl
  )

  $validServices = @('ziwei', 'api', 'web')
  foreach ($service in $Services) {
    if ($service -notin $validServices) { throw "Unknown service: $service" }
  }
  Set-W8RuntimeEnvironment -DatabaseUrl $DatabaseUrl

  if (-not (Test-Path -LiteralPath $script:W8Python -PathType Leaf)) {
    throw "Project virtual-environment Python is missing: $script:W8Python"
  }

  $nodeExe = Get-W8NodeExecutable
  $nodeVersion = (& $nodeExe --version).Trim()
  $nodeMatch = [regex]::Match($nodeVersion, '^v(?<major>\d+)\.')
  if (-not $nodeMatch.Success -or [int]$nodeMatch.Groups['major'].Value -lt 20) {
    throw "Node.js 20 or newer is required; detected $nodeVersion"
  }
  Write-Output "NODE_VERSION=$nodeVersion"
  if ([int]$nodeMatch.Groups['major'].Value -ne 20) {
    Write-Warning "CI uses Node 20; this local runtime uses $nodeVersion. Dependencies are not upgraded by W8."
  }

  $ports = @{ ziwei = 8100; api = 8000; web = 3000 }
  foreach ($service in $Services) {
    if (-not (Test-W8PortAvailable -Port $ports[$service])) {
      throw "Port $($ports[$service]) is already occupied; no process was started or stopped."
    }
  }

  if ($Services -contains 'ziwei' -and -not (Test-Path -LiteralPath (Join-Path $script:W8ZiweiDir 'dist\server.js') -PathType Leaf)) {
    throw '紫微服务构建产物缺失；先在 services/ziwei-service 执行 npm run build。'
  }
  if ($Services -contains 'web') {
    $buildId = Join-Path $script:W8WebDir '.next-w8\BUILD_ID'
    if (-not (Test-Path -LiteralPath $buildId -PathType Leaf)) {
      throw 'Next.js W8 生产构建缺失；先设置 SMP_API_BASE 并以 NEXT_DIST_DIR=.next-w8 执行 npm run build。'
    }
  }

  Push-Location $script:W8Root
  try {
    & $script:W8Python (Join-Path $PSScriptRoot 'w8_preflight.py')
    if ($LASTEXITCODE -ne 0) { throw "只读 Python 预检失败，exit=$LASTEXITCODE" }
  } finally {
    Pop-Location
  }
}

function Get-W8ProcessState {
  if (-not (Test-Path -LiteralPath $script:W8StateFile -PathType Leaf)) {
    return @()
  }
  $document = Get-Content -LiteralPath $script:W8StateFile -Raw | ConvertFrom-Json
  if ($document.schema_version -ne 'w8-local-runtime-processes-v1' -or $document.root -ne $script:W8Root) {
    throw "Refusing to use unrelated or unsupported process state: $script:W8StateFile"
  }
  return @($document.processes)
}

function Write-W8ProcessState {
  param([object[]]$Processes)

  if (-not (Test-Path -LiteralPath $script:W8RuntimeDir -PathType Container)) {
    New-Item -ItemType Directory -Path $script:W8RuntimeDir -Force | Out-Null
  }
  if ($Processes.Count -eq 0) {
    if (Test-Path -LiteralPath $script:W8StateFile -PathType Leaf) {
      Remove-Item -LiteralPath $script:W8StateFile
    }
    return
  }
  $document = [ordered]@{
    schema_version = 'w8-local-runtime-processes-v1'
    root = $script:W8Root
    updated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    processes = @($Processes)
  }
  [System.IO.File]::WriteAllText(
    $script:W8StateFile,
    (ConvertTo-Json -InputObject $document -Depth 8),
    [System.Text.UTF8Encoding]::new($false)
  )
}

function Test-W8ProcessIdentity {
  param([object]$Record)

  try {
    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction Stop
    $actualPath = [System.IO.Path]::GetFullPath($process.Path)
    $expectedPath = [System.IO.Path]::GetFullPath([string]$Record.executable)
    $actualStartTicks = $process.StartTime.ToUniversalTime().Ticks
    $ticksProperty = $Record.PSObject.Properties['started_at_utc_ticks']
    if ($ticksProperty -and $null -ne $ticksProperty.Value) {
      $expectedStartTicks = [long]$ticksProperty.Value
    } elseif ($Record.started_at_utc -is [DateTime]) {
      $recordedStart = [DateTime]$Record.started_at_utc
      if ($recordedStart.Kind -eq [DateTimeKind]::Utc) {
        $expectedStartTicks = $recordedStart.Ticks
      } else {
        $expectedStartTicks = $recordedStart.ToUniversalTime().Ticks
      }
    } else {
      $expectedStartTicks = [DateTimeOffset]::Parse(
        [string]$Record.started_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
      ).UtcDateTime.Ticks
    }
    $startDeltaSeconds = [Math]::Abs(($actualStartTicks - $expectedStartTicks) / [double][TimeSpan]::TicksPerSecond)
    return ($actualPath -ieq $expectedPath) -and ($startDeltaSeconds -le 2)
  } catch {
    return $false
  }
}

function Stop-W8ProcessRecord {
  param([object]$Record)

  $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
  if (-not $process) { return $true }
  if (-not (Test-W8ProcessIdentity -Record $Record)) {
    Write-Warning "未停止 PID $($Record.pid)：进程路径或启动时间与 W8 记录不符。"
    return $false
  }

  Stop-Process -Id ([int]$Record.pid) -Force -ErrorAction Stop
  try {
    Wait-Process -Id ([int]$Record.pid) -Timeout 10 -ErrorAction Stop
  } catch {
    # Wait-Process raises on timeout; inspect below and retain the record if still alive.
  }
  if (Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue) {
    Write-Warning "PID $($Record.pid) 仍在运行，保留其所有权记录。"
    return $false
  }
  Write-Output "STOPPED_$($Record.service)_PID=$($Record.pid)"
  return $true
}

function Get-W8ServiceSpec {
  param([string]$Service, [string]$NodeExecutable)

  switch ($Service) {
    'ziwei' {
      return [ordered]@{
        service = 'ziwei'; port = 8100; executable = $NodeExecutable
        working_directory = $script:W8ZiweiDir; arguments = @('dist/server.js')
        health_url = 'http://127.0.0.1:8100/health'
      }
    }
    'api' {
      return [ordered]@{
        service = 'api'; port = 8000; executable = $script:W8Python
        working_directory = $script:W8Root; arguments = @('-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8000')
        health_url = 'http://127.0.0.1:8000/api/v2/system/readiness'
      }
    }
    'web' {
      return [ordered]@{
        service = 'web'; port = 3000; executable = $NodeExecutable
        working_directory = $script:W8WebDir; arguments = @('node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '-p', '3000')
        health_url = 'http://127.0.0.1:3000/'
      }
    }
    default { throw "Unknown W8 service: $Service" }
  }
}

function Wait-W8Service {
  param([object]$Spec, [object]$Record, [int]$TimeoutSeconds = 40)

  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  $lastError = 'no response'
  while ([DateTimeOffset]::UtcNow -lt $deadline) {
    if (-not (Test-W8ProcessIdentity -Record $Record)) {
      throw "$($Spec.service) process exited or changed identity; see $($Record.stderr)"
    }
    try {
      if ($Spec.service -eq 'web') {
        $response = Invoke-WebRequest -Uri $Spec.health_url -TimeoutSec 3 -UseBasicParsing
        if ([int]$response.StatusCode -eq 200) { return }
      } else {
        $response = Invoke-RestMethod -Uri $Spec.health_url -TimeoutSec 3
        if ($Spec.service -eq 'ziwei' -and $response.status -eq 'ok') { return }
        if ($Spec.service -eq 'api' -and $response.ready -eq $true) {
          Write-Output "API_READINESS_STATUS=$($response.status)"
          Write-Output "API_RESEARCH_ELIGIBLE=$($response.components.research_data.research_eligible)"
          return
        }
        $lastError = "readiness status=$($response.status), ready=$($response.ready)"
      }
    } catch {
      $lastError = $_.Exception.Message
    }
    Start-Sleep -Milliseconds 500
  }
  throw "$($Spec.service) did not become available within ${TimeoutSeconds}s: $lastError"
}

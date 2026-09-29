param(
  [ValidateSet('ziwei', 'api', 'web')]
  [string[]]$Services = @('ziwei', 'api', 'web'),
  [string]$DatabaseUrl
)

. (Join-Path $PSScriptRoot 'w8-common.ps1')
Set-W8RuntimeEnvironment -DatabaseUrl $DatabaseUrl
Invoke-W8Preflight -Services $Services -DatabaseUrl $DatabaseUrl

$existing = @(Get-W8ProcessState)
foreach ($record in $existing) {
  if (-not (Test-W8ProcessIdentity -Record $record)) {
    throw "Recorded process $($record.service) PID $($record.pid) is missing or has changed identity; run stop-w8.ps1 to reconcile before starting."
  }
}
foreach ($service in $Services) {
  if (@($existing | Where-Object { $_.service -eq $service }).Count -gt 0) {
    throw "$service is already recorded as running; stop it through stop-w8.ps1 before starting it again."
  }
}

$orderedServices = @('ziwei', 'api', 'web') | Where-Object { $_ -in $Services }
$nodeExe = Get-W8NodeExecutable
$runId = [DateTimeOffset]::Now.ToString('yyyyMMdd-HHmmss-fff')
$logDir = Join-Path $script:W8RuntimeDir "logs\$runId"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$state = [System.Collections.Generic.List[object]]::new()
foreach ($record in $existing) { $state.Add($record) }
$startedHere = [System.Collections.Generic.List[object]]::new()

try {
  foreach ($service in $orderedServices) {
    $spec = Get-W8ServiceSpec -Service $service -NodeExecutable $nodeExe
    $stdout = Join-Path $logDir "$service.stdout.log"
    $stderr = Join-Path $logDir "$service.stderr.log"
    $stdin = Join-Path $logDir "$service.stdin"
    New-Item -ItemType File -Path $stdin -Force | Out-Null
    $process = Start-Process -FilePath $spec.executable -WorkingDirectory $spec.working_directory `
      -ArgumentList $spec.arguments -RedirectStandardInput $stdin -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
      -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 150
    $process.Refresh()
    if ($process.HasExited) { throw "$service exited during startup; see $stderr" }
    $actual = Get-Process -Id $process.Id -ErrorAction Stop
    $record = [ordered]@{
      service = $service
      pid = $process.Id
      executable = [System.IO.Path]::GetFullPath($spec.executable)
      started_at_utc = $actual.StartTime.ToUniversalTime().ToString('o')
      started_at_utc_ticks = [long]$actual.StartTime.ToUniversalTime().Ticks
      stdout = $stdout
      stderr = $stderr
    }
    $state.Add($record)
    $startedHere.Add($record)
    Write-W8ProcessState -Processes @($state.ToArray())
    Wait-W8Service -Spec $spec -Record $record
    Write-Output "STARTED_$service`_PID=$($process.Id) PORT=$($spec.port) HOST=127.0.0.1"
  }
  Write-Output "W8_PROCESS_STATE=$script:W8StateFile"
  Write-Output "W8_LOG_DIR=$logDir"
} catch {
  for ($index = $startedHere.Count - 1; $index -ge 0; $index--) {
    [void](Stop-W8ProcessRecord -Record $startedHere[$index])
  }
  $newIds = @($startedHere | ForEach-Object { [int]$_.pid })
  $remaining = @($state | Where-Object { [int]$_.pid -notin $newIds })
  Write-W8ProcessState -Processes $remaining
  throw
}

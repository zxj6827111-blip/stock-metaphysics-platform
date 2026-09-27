param(
  [ValidateSet('all', 'ziwei', 'api', 'web')]
  [string]$Service = 'all'
)

. (Join-Path $PSScriptRoot 'w8-common.ps1')
$records = @(Get-W8ProcessState)
if ($records.Count -eq 0) {
  Write-Output 'No W8-owned processes are recorded.'
  return
}

$selected = if ($Service -eq 'all') { @('web', 'api', 'ziwei') } else { @($Service) }
$removePids = [System.Collections.Generic.List[int]]::new()
$blockedPids = [System.Collections.Generic.List[int]]::new()
foreach ($name in $selected) {
  foreach ($record in @($records | Where-Object { $_.service -eq $name })) {
    if (Stop-W8ProcessRecord -Record $record) {
      $removePids.Add([int]$record.pid)
    } else {
      $blockedPids.Add([int]$record.pid)
    }
  }
}

$remaining = @($records | Where-Object { [int]$_.pid -notin @($removePids.ToArray()) })
Write-W8ProcessState -Processes $remaining
if ($blockedPids.Count -gt 0) {
  throw "Some recorded processes were not stopped safely; retained PID records: $($blockedPids -join ', ')"
}
if ($remaining.Count -gt 0) {
  Write-Output "W8_PROCESSES_REMAINING=$($remaining.service -join ',')"
}

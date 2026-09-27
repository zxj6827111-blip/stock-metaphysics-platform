param(
  [ValidateSet('ziwei', 'api', 'web')]
  [string[]]$Services = @('ziwei', 'api', 'web'),
  [string]$DatabaseUrl
)

. (Join-Path $PSScriptRoot 'w8-common.ps1')
Invoke-W8Preflight -Services $Services -DatabaseUrl $DatabaseUrl

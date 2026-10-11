# Portable thin launcher. No state logic. Prefer explicit verified host Python.
param([Parameter(ValueFromRemainingArguments = $true)] $args)
$ErrorActionPreference = 'Stop'
function Emit-Blocked {
  param([string]$Code, [string]$Detail)
  @{result_schema_version='1.0';operation='launcher';status='BLOCKED';task_id=$null;generation=$null;changed=$false;diagnostics=@(@{code=$Code;severity='ERROR';summary=$Detail});data=@{}} | ConvertTo-Json -Depth 6 -Compress
  exit 3
}
$entry = Join-Path $PSScriptRoot 'dev_state.py'
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { Emit-Blocked 'CORE_ABSENT' 'dev_state.py not found next to launcher' }
$py = $null
if ($env:DEV_STATE_PYTHON) {
  if (-not (Test-Path -LiteralPath $env:DEV_STATE_PYTHON -PathType Leaf)) { Emit-Blocked 'PYTHON_ABSENT' 'explicit DEV_STATE_PYTHON path does not exist' }
  $py = $env:DEV_STATE_PYTHON
} else {
  $candidate = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($candidate) { $py = $candidate.Source }
}
if (-not $py) { Emit-Blocked 'PYTHON_ABSENT' 'no verified host Python configured or available on PATH' }
$previousEncoding = $env:PYTHONIOENCODING
$resultCode = 3
try {
  $env:PYTHONIOENCODING = 'utf-8'
  & $py -X utf8 $entry @args
  $resultCode = $LASTEXITCODE
} catch {
  Emit-Blocked 'PYTHON_START_FAILED' 'host Python could not be started'
} finally {
  $env:PYTHONIOENCODING = $previousEncoding
}
exit $resultCode

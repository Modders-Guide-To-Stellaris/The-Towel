# PowerShell helper to run the extractor using .env in this folder (if present)
$script = Join-Path $PSScriptRoot 'extract_originals.py'
$envFile = Join-Path $PSScriptRoot '.env'
if (-Not (Test-Path $script)) { Write-Error "extract_originals.py not found in $PSScriptRoot"; exit 1 }

$python = 'python'
# Prefer python in PATH; user can edit to full path if needed

Write-Host "Using .env: $envFile"
& $python $script --env-file $envFile

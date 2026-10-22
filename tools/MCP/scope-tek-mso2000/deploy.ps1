# Prepare the environment beside the repository source; no runtime copy is deployed.
$ErrorActionPreference = 'Stop'
$venvDir = Join-Path $PSScriptRoot '.venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPy)) {
    py -3.11 -m venv $venvDir
    if ($LASTEXITCODE) { throw 'venv creation failed' }
}
& $venvPy -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE) { throw 'dependency installation failed' }
Write-Host "MCP command: $venvPy"
Write-Host "MCP entry: $(Join-Path $PSScriptRoot 'mso_mcp.py')"
Write-Host 'Register these repository paths as mso, then reconnect the MCP server.'

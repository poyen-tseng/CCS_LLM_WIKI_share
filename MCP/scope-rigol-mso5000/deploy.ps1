# Sync this folder (the copy in the repository) to the Claude Code runtime on C:.
# The MCP server registered in Claude Code runs from the runtime copy, so edits here only take
# effect after running this script and reconnecting the server (/mcp in Claude Code, or restart).
$ErrorActionPreference = 'Stop'

$src     = $PSScriptRoot
$runtime = Join-Path $HOME '.claude\mcp\scope'
$venvPy  = Join-Path $runtime '.venv\Scripts\python.exe'
$files   = 'rigol.py', 'scope_mcp.py', 'config.json', 'requirements.txt'

New-Item -ItemType Directory -Force $runtime | Out-Null

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating venv in $runtime\.venv"
    py -3.11 -m venv (Join-Path $runtime '.venv')
    if ($LASTEXITCODE) { throw 'venv creation failed' }
}

$reqDst = Join-Path $runtime 'requirements.txt'
$oldHash = if (Test-Path $reqDst) { (Get-FileHash $reqDst).Hash } else { '' }
$newHash = (Get-FileHash (Join-Path $src 'requirements.txt')).Hash
$needInstall = ($oldHash -ne $newHash) -or -not (Test-Path (Join-Path $runtime '.venv\Lib\site-packages\mcp'))

foreach ($f in $files) { Copy-Item (Join-Path $src $f) $runtime -Force }
Write-Host "Copied: $($files -join ', ') -> $runtime"

if ($needInstall) {
    Write-Host 'Installing pinned requirements...'
    & $venvPy -m pip install --disable-pip-version-check -q -r $reqDst
    if ($LASTEXITCODE) { throw 'pip install failed' }
}

Write-Host 'Done. Reconnect the "scope" MCP server (/mcp in Claude Code, or restart) to load the new code.'

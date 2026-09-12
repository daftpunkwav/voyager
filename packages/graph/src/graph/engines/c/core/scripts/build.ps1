# Voyager: build the migrated C graph engine (graph-engine)
# Prefers WSL; otherwise falls back to a local MinGW make.

param(
    [switch]$WithUi,
    [int]$Jobs = 0,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Help) {
    Write-Host @"
Usage: .\scripts\build.ps1 [-Jobs N]

Build the C engine under packages/graph/src/graph/engines/c/core.
Output: build/c/graph-engine (or .exe)
Note: the UI asset service has been removed; -WithUi is kept only for
backward compatibility and has no effect.
"@
    exit 0
}

if ($WithUi) {
    Write-Host "Warning: -WithUi is deprecated (frontend asset service removed); building the standard target." -ForegroundColor Yellow
}

function Test-Wsl {
    try {
        $null = & wsl.exe -e true 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$j = if ($Jobs -gt 0) { $Jobs } else { [Math]::Max(2, [Environment]::ProcessorCount - 1) }
$target = "graph-engine"

Write-Host "==> Build target: $target  -j$j" -ForegroundColor Cyan

# Normalize shell script line endings before building so /mnt/d CRLF does not break sh
python -c @"
from pathlib import Path
root = Path(r'$($Root -replace '\\','/')')
for p in root.rglob('*.sh'):
    b = p.read_bytes()
    if b'\r' in b:
        p.write_bytes(b.replace(b'\r\n', b'\n').replace(b'\r', b'\n'))
"@

if (Test-Wsl) {
    $wslPath = (& wsl.exe wslpath -a $Root).Trim()
    Write-Host "==> Using WSL: $wslPath" -ForegroundColor Cyan
    & wsl.exe -e bash -lc "set -euo pipefail; cd '$wslPath'; make -f Makefile -j$j $target"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    $make = Get-Command make -ErrorAction SilentlyContinue
    $gcc = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $make -or -not $gcc) {
        Write-Error "WSL not found and local make/gcc missing. Install WSL or MinGW."
    }
    Write-Host "==> Using local MinGW make/gcc" -ForegroundColor Cyan
    & make -f Makefile -j$j $target
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$candidates = @(
    (Join-Path $Root "build\c\graph-engine.exe"),
    (Join-Path $Root "build\c\graph-engine"),
    (Join-Path $Root "build\c\graph-engine.exe"),
    (Join-Path $Root "build\c\graph-engine")
)
$found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($found) {
    Write-Host "==> Success: $found" -ForegroundColor Green
} else {
    Write-Warning "Build command returned, but no expected artifact path was found; check build/c/"
}

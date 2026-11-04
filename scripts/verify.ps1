# Run the local verification suite (PowerShell, Windows).
# This starts the mock API/web servers through Playwright for E2E.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "== Docs links =="
python "$repo/scripts/check_docs.py"
if ($LASTEXITCODE -ne 0) { throw "docs link check failed" }

Write-Host "== API tests =="
python -m pytest "$repo/apps/api" -q
if ($LASTEXITCODE -ne 0) { throw "API tests failed" }

Write-Host "== Indexer tests =="
python -m pytest "$repo/apps/indexer" -q
if ($LASTEXITCODE -ne 0) { throw "indexer tests failed" }

Write-Host "== Web build =="
Push-Location "$repo/apps/web"
try {
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw "web build failed" }
} finally {
  Pop-Location
}

Write-Host "== Web unit tests =="
Push-Location "$repo/apps/web"
try {
  npm.cmd test
  if ($LASTEXITCODE -ne 0) { throw "web unit tests failed" }
} finally {
  Pop-Location
}

Write-Host "== Contracts (optional) =="
$forgePath = $null
$forge = Get-Command forge -ErrorAction SilentlyContinue
if ($forge) {
  $forgePath = $forge.Source
} else {
  $localForge = Join-Path $env:LOCALAPPDATA "veilpool-tools\foundry-v1.9.0\forge.exe"
  if (Test-Path $localForge) { $forgePath = $localForge }
}
if ($forgePath) {
  Push-Location "$repo/contracts"
  try {
    & $forgePath test -q
    if ($LASTEXITCODE -ne 0) { throw "forge test failed" }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "Skipping contracts: forge is not installed." -ForegroundColor Yellow
}

Write-Host "== Circuit negatives (optional) =="
$circuitBuild = Join-Path $repo "circuits/build/verification_key.json"
if ((Test-Path $circuitBuild) -and (Test-Path (Join-Path $repo "circuits/node_modules"))) {
  Push-Location "$repo/circuits"
  try {
    node scripts/verify-negative.mjs
    if ($LASTEXITCODE -ne 0) { throw "circuit negative tests failed" }
    node scripts/witness-negative.mjs
    if ($LASTEXITCODE -ne 0) { throw "circuit witness negative tests failed" }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "Skipping circuits: build artifacts or node_modules are missing." -ForegroundColor Yellow
}

Write-Host "== Browser E2E =="
Push-Location "$repo/tests/e2e"
try {
  npm.cmd test
  if ($LASTEXITCODE -ne 0) { throw "browser E2E failed" }
} finally {
  Pop-Location
}

Write-Host "Verification complete."

#requires -Version 5.1
<#
.SYNOPSIS
    Start local Anvil, deploy the VeilPool MOCK contracts, and run the indexer.

.DESCRIPTION
    LOCAL ANVIL ONLY. MockVerifier performs no cryptography and provides no
    privacy. The deploy uses Anvil's unlocked account #0 via
    eth_sendTransaction; no private key is stored in this script. Never send
    real funds.

    By default this script:
      1. starts anvil --chain-id 31337 on 127.0.0.1:8545,
      2. runs contracts/script/Deploy.s.sol with forge,
      3. exports ANVIL_RPC_URL / VEILPOOL_ADDRESS, and
      4. runs the FastAPI indexer in the foreground.

    Press Ctrl-C to stop the indexer. The script stops the Anvil process it
    started unless -KeepAnvil is set.

.PARAMETER SkipAnvil
    Use an Anvil instance that is already running. The script will not stop it.

.PARAMETER DeployOnly
    Deploy and print addresses, but do not start the indexer.

.PARAMETER NoIndexer
    Start/deploy but do not run the indexer.

.PARAMETER KeepAnvil
    Leave a script-started Anvil process running after exit.

.PARAMETER InstallDeps
    Run `forge install foundry-rs/forge-std --no-commit` and
    `python -m pip install -r apps/indexer/requirements.txt` when dependencies
    are missing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infrastructure/anvil-deploy.ps1 -InstallDeps

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infrastructure/anvil-deploy.ps1 -SkipAnvil -DeployOnly
#>
[CmdletBinding()]
param(
    [int]$Port = 8545,
    [int]$IndexerPort = 8100,
    [switch]$SkipAnvil,
    [switch]$DeployOnly,
    [switch]$NoIndexer,
    [switch]$KeepAnvil,
    [switch]$InstallDeps,
    [string]$FromAddress = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Contracts = Join-Path $RepoRoot "contracts"
$IndexerDir = Join-Path $RepoRoot "apps\indexer"
$RpcUrl = "http://127.0.0.1:$Port"
$AnvilProcess = $null

function Resolve-FoundryTool {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $local = Join-Path $env:LOCALAPPDATA "veilpool-tools\foundry-v1.9.0\$Name.exe"
    if (Test-Path $local) { return $local }
    return $null
}

function Write-WarningBanner {
    Write-Host ""
    Write-Host "  MOCK VERIFIER / NO REAL ZK / LOCAL ANVIL ONLY" -ForegroundColor Yellow
    Write-Host "  MockVerifier accepts a copy of public signals; it proves nothing." -ForegroundColor Yellow
    Write-Host "  No real funds. No anonymity. Never use a mainnet RPC." -ForegroundColor Yellow
    Write-Host ""
}

function Wait-ForAnvil {
    param([string]$Url, [int]$Attempts = 60)
    $body = @{ jsonrpc = "2.0"; id = 1; method = "eth_chainId"; params = @() } | ConvertTo-Json
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $response = Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Body $body -TimeoutSec 2
            if ($response.result) {
                $chainId = [Convert]::ToInt64($response.result, 16)
                if ($chainId -ne 31337) {
                    throw "Anvil reported chain ID $chainId, expected 31337. Refusing to deploy."
                }
                return
            }
        } catch {
            if ($_.Exception.Message -like "*Refusing*") { throw }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Anvil did not become ready at $Url. Check the Anvil log in $env:TEMP."
}

function Get-ContractAddress {
    param([string]$Name, [string]$Text, [string]$BroadcastFile)
    $match = [regex]::Match($Text, "$Name deployed at:\s*(0x[0-9a-fA-F]{40})")
    if ($match.Success) { return $match.Groups[1].Value }

    if (Test-Path $BroadcastFile) {
        $broadcast = Get-Content $BroadcastFile -Raw | ConvertFrom-Json
        foreach ($transaction in $broadcast.transactions) {
            if ($transaction.contractName -eq $Name -and $transaction.contractAddress) {
                return [string]$transaction.contractAddress
            }
        }
    }
    return ""
}

try {
    Write-WarningBanner

    $forgeExe = Resolve-FoundryTool -Name "forge"
    $anvilExe = Resolve-FoundryTool -Name "anvil"
    if (-not $forgeExe) {
        throw "Missing 'forge'. Install Foundry from https://book.getfoundry.sh/ or place the binaries in $env:LOCALAPPDATA\veilpool-tools\foundry-v1.9.0\. No deployment was attempted."
    }
    if (-not $SkipAnvil -and -not $anvilExe) {
        throw "Missing 'anvil'. Install Foundry or place the binaries in $env:LOCALAPPDATA\veilpool-tools\foundry-v1.9.0\, or pass -SkipAnvil. No deployment was attempted."
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Missing 'python' on PATH."
    }

    $forgeStd = Join-Path $Contracts "lib\forge-std\src\Script.sol"
    if (-not (Test-Path $forgeStd)) {
        if ($InstallDeps) {
            Write-Host "Installing forge-std..."
            Push-Location $Contracts
            try {
                & $forgeExe install foundry-rs/forge-std --no-commit
                if ($LASTEXITCODE -ne 0) { throw "forge install failed" }
            } finally {
                Pop-Location
            }
        } else {
            throw "contracts/lib/forge-std is missing. Run: cd contracts; forge install foundry-rs/forge-std --no-commit (or pass -InstallDeps)."
        }
    }

    if (-not $SkipAnvil) {
        Write-Host "Starting Anvil on $RpcUrl (chain ID 31337)..."
        $anvilOut = Join-Path $env:TEMP "veilpool-anvil-$Port.out.log"
        $anvilErr = Join-Path $env:TEMP "veilpool-anvil-$Port.err.log"
        $AnvilProcess = Start-Process -FilePath $anvilExe `
            -ArgumentList @("--host", "127.0.0.1", "--port", "$Port", "--chain-id", "31337") `
            -PassThru `
            -RedirectStandardOutput $anvilOut `
            -RedirectStandardError $anvilErr
        Wait-ForAnvil -Url $RpcUrl
        Write-Host "Anvil ready (PID $($AnvilProcess.Id))."
    } else {
        Wait-ForAnvil -Url $RpcUrl
        Write-Host "Using the existing Anvil at $RpcUrl."
    }

    $deployScript = Join-Path $Contracts "script\Deploy.s.sol"
    if (-not (Test-Path $deployScript)) {
        throw "Missing $deployScript"
    }

    Write-Host "Deploying MockVerifier and VeilPool..."
    Push-Location $Contracts
    try {
        $deployOutput = & $forgeExe script script/Deploy.s.sol:Deploy `
            --rpc-url $RpcUrl `
            --broadcast `
            --unlocked `
            --sender $FromAddress `
            -vv 2>&1
        $deployExit = $LASTEXITCODE
        $deployText = ($deployOutput | Out-String)
        Write-Host $deployText
        if ($deployExit -ne 0) {
            throw "forge script failed with exit code $deployExit"
        }
    } finally {
        Pop-Location
    }

    $broadcastFile = Join-Path $Contracts "broadcast\Deploy.s.sol\31337\run-latest.json"
    $verifierAddress = Get-ContractAddress -Name "MockVerifier" -Text $deployText -BroadcastFile $broadcastFile
    $poolAddress = Get-ContractAddress -Name "VeilPool" -Text $deployText -BroadcastFile $broadcastFile
    if (-not $verifierAddress -or -not $poolAddress) {
        throw "Could not parse deployment addresses. See $broadcastFile."
    }

    $env:ANVIL_RPC_URL = $RpcUrl
    $env:VEILPOOL_ADDRESS = $poolAddress
    $env:INDEXER_DB = Join-Path $IndexerDir "indexer.db"
    $env:INDEXER_PORT = "$IndexerPort"
    $env:INDEXER_START_BLOCK = "0"
    $env:INDEXER_ALLOWED_CHAIN_IDS = "31337"

    Write-Host ""
    Write-Host "Deployment complete (LOCAL ANVIL / MOCK VERIFIER):" -ForegroundColor Green
    Write-Host "  MockVerifier : $verifierAddress"
    Write-Host "  VeilPool     : $poolAddress"
    Write-Host "  Chain ID     : 31337"
    Write-Host "  Pools        : pool_eth_01, pool_eth_1, pool_eth_10"
    Write-Host ""
    Write-Host "Indexer environment:"
    Write-Host "  `$env:ANVIL_RPC_URL = `"$RpcUrl`""
    Write-Host "  `$env:VEILPOOL_ADDRESS = `"$poolAddress`""
    Write-Host "  `$env:INDEXER_DB = `"$env:INDEXER_DB`""
    Write-Host ""

    if ($DeployOnly -or $NoIndexer) {
        Write-Host "Indexer was not started."
        if ($KeepAnvil -and $AnvilProcess) {
            Write-Host "Anvil is still running (PID $($AnvilProcess.Id)). Stop it with: Stop-Process -Id $($AnvilProcess.Id)"
        }
        return
    }

    $depsOk = $true
    & python -c "import fastapi, uvicorn, httpx" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $depsOk = $false }
    if (-not $depsOk) {
        if ($InstallDeps) {
            Write-Host "Installing indexer dependencies..."
            & python -m pip install -r (Join-Path $IndexerDir "requirements.txt")
            if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
        } else {
            throw "Indexer dependencies may be missing. Run: python -m pip install -r apps/indexer/requirements.txt (or pass -InstallDeps)."
        }
    }

    Write-Host "Starting indexer API on http://127.0.0.1:$IndexerPort ..."
    Write-Host "  $RpcUrl -> $poolAddress"
    Write-Host ""
    Push-Location $IndexerDir
    try {
        & python -m veilpool_indexer --host 127.0.0.1 --port $IndexerPort
        if ($LASTEXITCODE -ne 0) {
            throw "indexer exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($AnvilProcess -and -not $KeepAnvil -and -not $AnvilProcess.HasExited) {
        Write-Host "Stopping Anvil PID $($AnvilProcess.Id)..."
        Stop-Process -Id $AnvilProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

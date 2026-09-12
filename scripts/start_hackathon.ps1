param(
    [switch]$DemoMode,
    [string]$Port = "COM3",
    [int]$WebPort = 5000,
    [switch]$DisableAutoRestart,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Test-PythonInterpreter {
    param(
        [string]$PythonPath
    )

    if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
        return $false
    }

    & $PythonPath -c "import sys; print(sys.executable)" *> $null
    return $LASTEXITCODE -eq 0
}

function Resolve-WorkingPython {
    param(
        [string]$RootDir
    )

    $venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (Test-PythonInterpreter -PythonPath $venvPython) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonInterpreter -PythonPath $pythonCmd.Source)) {
        Write-Warning "Local .venv Python is unavailable. Falling back to PATH python: $($pythonCmd.Source)"
        return $pythonCmd.Source
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $resolved = (& $pyCmd.Source -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
        if ($resolved -and (Test-PythonInterpreter -PythonPath $resolved)) {
            Write-Warning "Local .venv Python is unavailable. Falling back to py -3 resolved python: $resolved"
            return $resolved
        }
    }

    return $null
}

$python = Resolve-WorkingPython -RootDir $root

if (-not (Test-PythonInterpreter -PythonPath $python)) {
    Write-Error "No working Python interpreter found. Fix .venv or install Python 3.9+ and ensure 'python' is on PATH."
    exit 103
}

New-Item -ItemType Directory -Force -Path "logs\runtime" | Out-Null

if (-not $SkipPreflight) {
    $preflightArgs = @("scripts/preflight_check.py", "--port", $Port)
    if ($DemoMode) {
        $preflightArgs += "--demo-mode"
        $preflightArgs += "--allow-no-hardware"
    }

    & $python $preflightArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Preflight failed with code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

$dashboardArgs = @(
    "ev_dashboard.py",
    "--port", $Port,
    "--web-port", "$WebPort",
    "--host", "127.0.0.1"
)

if ($DemoMode) {
    $dashboardArgs += "--demo-mode"
}

$autoRestart = -not $DisableAutoRestart

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] Starting EV mission control backend..."
    
    # Run Python with proper output redirection
    $process = Start-Process -FilePath $python -ArgumentList $dashboardArgs `
        -RedirectStandardOutput "logs/runtime/backend.log" `
        -RedirectStandardError "logs/runtime/backend_err.log" `
        -NoNewWindow -PassThru -Wait
    
    $exitCode = $process.ExitCode

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] Backend exited with code $exitCode"

    if (-not $autoRestart -or $exitCode -eq 0) {
        break
    }

    Write-Host "Auto-restart active. Restarting in 2 seconds..."
    Start-Sleep -Seconds 2
}

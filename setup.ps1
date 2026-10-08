$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$venvPython = Join-Path $projectPath '.venv\Scripts\python.exe'

function Test-Python312 {
    param([string] $Executable, [string[]] $Prefix = @())
    try {
        $result = & $Executable @Prefix -c 'import sys; print(sys.version_info[:2] == (3, 12))' 2>$null
        return $LASTEXITCODE -eq 0 -and $result -eq 'True'
    } catch {
        return $false
    }
}

function Find-Python312 {
    $candidates = @(
        @{ Executable = 'py'; Prefix = @('-3.12') },
        @{ Executable = 'python'; Prefix = @() },
        @{ Executable = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'); Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        if (Test-Python312 -Executable $candidate.Executable -Prefix $candidate.Prefix) {
            return $candidate
        }
    }
    return $null
}

function Assert-Success {
    param([string] $Stage)
    if ($LASTEXITCODE -ne 0) {
        throw "$Stage failed with exit code $LASTEXITCODE. Check the message above."
    }
}

try {
    Push-Location -LiteralPath $projectPath
    $runtime = Find-Python312
    if ($null -eq $runtime) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'Python 3.12 is missing and WinGet is unavailable. Install Python 3.12 from python.org, then run setup.bat again.'
        }
        Write-Host '[1/4] Installing Python 3.12 with WinGet...'
        & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements
        Assert-Success 'Python installation'
        $runtime = Find-Python312
        if ($null -eq $runtime) {
            throw 'Python was installed, but this session cannot locate it. Close this window and run setup.bat again.'
        }
    } else {
        Write-Host '[1/4] Python 3.12 is available.'
    }

    if (Test-Path -LiteralPath $venvPython) {
        if (-not (Test-Python312 -Executable $venvPython)) {
            throw 'The existing .venv uses a different Python version. Rename or remove .venv, then run setup.bat again.'
        }
        Write-Host '[2/4] Using the existing project environment.'
    } else {
        Write-Host '[2/4] Creating the project environment...'
        $runtimePrefix = [string[]] $runtime.Prefix
        & $runtime.Executable @runtimePrefix -m venv (Join-Path $projectPath '.venv')
        Assert-Success 'Virtual environment creation'
    }

    Write-Host '[3/4] Installing Python dependencies...'
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectPath 'requirements.txt')
    Assert-Success 'Dependency installation'

    Write-Host '[4/4] Installing the Playwright Chromium browser...'
    & $venvPython -m playwright install chromium
    Assert-Success 'Browser installation'

    & $venvPython -m pip check
    Assert-Success 'Dependency verification'
    & $venvPython -c 'import app.main; from pathlib import Path; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); assert Path(p.chromium.executable_path).is_file(); p.stop()'
    Assert-Success 'Application and browser verification'

    Write-Host ''
    Write-Host 'Installation complete. Double-click start.bat to run the app.'
    exit 0
} catch {
    Write-Host ''
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
